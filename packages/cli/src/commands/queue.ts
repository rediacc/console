import { Command } from 'commander';
import { parseGetQueueItemTrace } from '@rediacc/shared/api';
import { DEFAULTS } from '@rediacc/shared/config';
import {
  getValidationErrors,
  isBridgeFunction,
  safeValidateFunctionParams,
} from '@rediacc/shared/queue-vault';
import { FUNCTION_DEFINITIONS } from '@rediacc/shared/queue-vault/data/definitions';
import type {
  GetTeamQueueItems_ResultSet1,
  QueueTrace,
  QueueTraceSummary,
} from '@rediacc/shared/types';
import {
  compareValues,
  extractMostRecentProgress,
  parseLogOutput,
  searchInFields,
  unescapeLogOutput,
} from '@rediacc/shared/utils';
import { t } from '../i18n/index.js';
import { getStateProvider } from '../providers/index.js';
import { typedApi } from '../services/api.js';
import { authService } from '../services/auth.js';
import { configService } from '../services/config-resources.js';
import { outputService } from '../services/output.js';
import { queueService } from '../services/queue.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { formatLogOutput, getLogHeader } from '../utils/logFormatters.js';
import {
  formatAge,
  formatBoolean,
  formatError,
  formatPriority,
  formatRetryCount,
  formatStatus,
} from '../utils/queueFormatters.js';
import { startSpinner, stopSpinner, withSpinner } from '../utils/spinner.js';
import type { OutputFormat } from '../types/index.js';

function printTrace(trace: QueueTraceSummary, program: Command): void {
  const format = program.opts().output as OutputFormat;
  if (format === 'table') {
    outputService.print(
      {
        taskId: trace.taskId,
        status: formatStatus(trace.status ?? DEFAULTS.STATUS.UNKNOWN_UPPERCASE),
        age: trace.ageInMinutes == null ? '-' : formatAge(trace.ageInMinutes),
        priority: trace.priority ? formatPriority(trace.priority) : '-',
        retries: trace.retryCount == null ? '-' : formatRetryCount(trace.retryCount),
        progress: trace.progress ?? '-',
      },
      format
    );
    if (trace.consoleOutput) {
      outputService.info('');
      outputService.info(getLogHeader());
      outputService.info(formatLogOutput(parseLogOutput(trace.consoleOutput)));
    }
  } else {
    outputService.print(trace, format);
  }
}

function mapTraceToSummary(trace: QueueTrace): QueueTraceSummary | null {
  const { summary, queueDetails: details } = trace;
  if (!summary && !details) return null;
  const failureRaw = summary?.lastFailureReason ?? details?.lastFailureReason;
  return {
    taskId: summary?.taskId ?? details?.taskId ?? undefined,
    status: summary?.status ?? (details?.status as QueueTraceSummary['status']),
    healthStatus:
      summary?.healthStatus ?? (details?.healthStatus as QueueTraceSummary['healthStatus']),
    progress: summary?.progress,
    consoleOutput: summary?.consoleOutput ? unescapeLogOutput(summary.consoleOutput) : undefined,
    errorMessage: summary?.errorMessage ? unescapeLogOutput(summary.errorMessage) : undefined,
    lastFailureReason: failureRaw ? unescapeLogOutput(failureRaw) : undefined,
    priority: summary?.priority ?? details?.priority ?? undefined,
    retryCount: summary?.retryCount ?? details?.retryCount ?? undefined,
    ageInMinutes: summary?.ageInMinutes ?? details?.ageInMinutes ?? undefined,
    hasResponse: summary?.hasResponse ?? (details?.hasResponse ? true : false),
    teamName: summary?.teamName ?? details?.teamName ?? undefined,
    machineName: summary?.machineName ?? details?.machineName ?? undefined,
    bridgeName: summary?.bridgeName ?? details?.bridgeName ?? undefined,
    createdTime: summary?.createdTime ?? details?.createdTime ?? undefined,
    updatedTime:
      summary?.updatedTime ?? details?.lastAssigned ?? details?.lastResponseAt ?? undefined,
  };
}

export interface CreateActionOptions {
  team?: string;
  machine?: string;
  bridge?: string;
  priority: string;
  param?: string[];
  function: string;
  vault?: string;
  [key: string]: unknown;
}

export interface TraceActionOptions {
  watch?: boolean;
  interval: string;
}

export function parseParamOptions(paramOptions: string[] | undefined): Record<string, string> {
  const params: Record<string, string> = {};
  for (const param of paramOptions ?? []) {
    const [key, ...valueParts] = param.split('=');
    params[key] = valueParts.join('=');
  }
  return params;
}

/**
 * Coerce CLI string params to their expected types based on FUNCTION_DEFINITIONS.
 * CLI --param key=value always produces strings, but Zod schemas expect native types
 * (boolean, number). This bridges the gap using the generated type metadata.
 */
export function coerceCliParams(
  functionName: string,
  params: Record<string, string>
): Record<string, unknown> {
  if (!isBridgeFunction(functionName)) return params;
  const def = FUNCTION_DEFINITIONS[functionName];

  const result: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(params)) {
    if (!(key in def.params)) {
      result[key] = value;
      continue;
    }
    const paramDef = def.params[key];
    switch (paramDef.type) {
      case 'bool':
        result[key] = value === 'true' || value === '1' || value === 'yes';
        break;
      case 'int':
        result[key] = Number.parseInt(value, 10);
        break;
      default:
        result[key] = value;
    }
  }
  return result;
}

export function validateFunctionParams(
  functionName: string,
  params: Record<string, unknown>
): void {
  if (!isBridgeFunction(functionName)) return;
  const validationResult = safeValidateFunctionParams(functionName, params);
  if (!validationResult.success) {
    throw new ValidationError(
      t('errors.invalidFunctionParams', {
        function: functionName,
        errors: getValidationErrors(validationResult),
      })
    );
  }
}

async function buildQueueVaultFromParams(
  opts: { team?: string; machine?: string; bridge?: string },
  options: CreateActionOptions
): Promise<string> {
  const params = parseParamOptions(options.param);
  validateFunctionParams(options.function, params);
  const language = await configService.getLanguage();
  return withSpinner(
    t('commands.queue.create.buildingVault'),
    () =>
      queueService.buildQueueVault({
        teamName: opts.team as string,
        machineName: opts.machine,
        bridgeName: opts.bridge,
        functionName: options.function,
        params,
        priority: Number.parseInt(options.priority, 10),
        language,
      }),
    t('commands.queue.create.vaultBuilt')
  );
}

export async function createAction(options: CreateActionOptions): Promise<{ taskId?: string }> {
  const provider = await getStateProvider();
  if (provider.isCloud) {
    await authService.requireAuth();
  }
  const opts = await configService.applyDefaults(options);
  if (!opts.team) {
    throw new ValidationError(t('errors.teamRequired'));
  }
  const queueVault = options.vault ?? (await buildQueueVaultFromParams(opts, options));
  const result = await withSpinner(
    t('commands.queue.create.creating', { function: options.function }),
    () =>
      provider.queue.create({
        teamName: opts.team as string,
        machineName: opts.machine as string,
        bridgeName: opts.bridge as string,
        vaultContent: queueVault,
        priority: Number.parseInt(options.priority, 10),
        functionName: options.function,
      }),
    t('commands.queue.create.success')
  );
  if (result.taskId) {
    outputService.success(t('commands.queue.create.taskId', { taskId: result.taskId }));
  }
  return { taskId: result.taskId };
}
const TERMINAL_STATUSES = ['COMPLETED', 'FAILED', 'CANCELLED'] as const;

function buildSpinnerText(summary: QueueTraceSummary): string {
  const statusText = formatStatus(summary.status ?? DEFAULTS.STATUS.UNKNOWN_UPPERCASE);
  const ageText =
    summary.ageInMinutes == null ? t('common.unknown') : formatAge(summary.ageInMinutes);
  const percentage = extractMostRecentProgress(summary.consoleOutput ?? '');
  const progressText =
    percentage === null ? (summary.progress ?? t('common.inProgress')) : `${percentage}%`;
  return `${statusText} | ${t('commands.queue.trace.age')}: ${ageText} | ${progressText}`;
}

function isTerminalStatus(status: string | undefined): boolean {
  return status ? (TERMINAL_STATUSES as readonly string[]).includes(status.toUpperCase()) : false;
}

function displayFailureReason(summary: QueueTraceSummary): void {
  if (summary.lastFailureReason) {
    outputService.error(t('commands.queue.trace.errorDetails'));
    outputService.error(formatError(summary.lastFailureReason, true));
  }
}
function handleTerminalStatus(summary: QueueTraceSummary, program: Command): void {
  const status = summary.status?.toUpperCase() ?? DEFAULTS.STATUS.UNKNOWN_UPPERCASE;
  const success = status === 'COMPLETED';
  stopSpinner(success, t('commands.queue.trace.finalStatus', { status: formatStatus(status) }));
  if (!success) displayFailureReason(summary);
  printTrace(summary, program);
}
async function fetchTraceSummary(
  provider: import('../providers/types.js').IStateProvider,
  taskId: string
): Promise<QueueTraceSummary | null> {
  if (provider.isCloud) {
    const apiResponse = await typedApi.GetQueueItemTrace({ taskId });
    return mapTraceToSummary(parseGetQueueItemTrace(apiResponse as never));
  }
  const item = await provider.queue.trace(taskId);
  if (!item) return null;
  return {
    taskId: item.taskId as string | undefined,
    status: item.status as QueueTraceSummary['status'],
    healthStatus: undefined,
    progress: undefined,
    consoleOutput: item.consoleOutput ? String(item.consoleOutput) : undefined,
    errorMessage: item.errorMessage ? String(item.errorMessage) : undefined,
    lastFailureReason: item.errorMessage ? String(item.errorMessage) : undefined,
    priority: typeof item.priority === 'number' ? item.priority : undefined,
    retryCount: typeof item.retryCount === 'number' ? item.retryCount : undefined,
    ageInMinutes: item.createdAt
      ? Math.round((Date.now() - new Date(item.createdAt as string).getTime()) / 60000)
      : undefined,
    hasResponse: !!(item.consoleOutput ?? item.exitCode !== undefined),
    teamName: item.teamName as string | undefined,
    machineName: item.machineName as string | undefined,
    bridgeName: item.bridgeName as string | undefined,
    createdTime: item.createdAt as string | undefined,
    updatedTime: item.updatedAt as string | undefined,
  };
}

async function watchTraceLoop(
  provider: import('../providers/types.js').IStateProvider,
  taskId: string,
  interval: number,
  program: Command
): Promise<void> {
  const spinner = startSpinner(t('commands.queue.trace.watching'));
  for (;;) {
    const summary = await fetchTraceSummary(provider, taskId);
    if (!summary) {
      await new Promise((resolve) => setTimeout(resolve, interval));
      continue;
    }
    if (spinner) spinner.text = buildSpinnerText(summary);
    if (isTerminalStatus(summary.status)) {
      handleTerminalStatus(summary, program);
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, interval));
  }
}

async function singleFetchTrace(
  provider: import('../providers/types.js').IStateProvider,
  taskId: string,
  program: Command
): Promise<void> {
  const summary = await withSpinner(
    t('commands.queue.trace.fetching'),
    () => fetchTraceSummary(provider, taskId),
    t('commands.queue.trace.fetched')
  );
  if (!summary) {
    outputService.info(t('commands.queue.trace.noTrace'));
    return;
  }
  if (summary.status === 'FAILED' && summary.lastFailureReason) {
    displayFailureReason(summary);
    outputService.info('');
  }
  printTrace(summary, program);
}

export async function traceAction(
  taskId: string,
  options: TraceActionOptions,
  program: Command
): Promise<void> {
  const provider = await getStateProvider();
  if (provider.isCloud) await authService.requireAuth();
  if (options.watch) {
    await watchTraceLoop(provider, taskId, Number.parseInt(options.interval, 10), program);
  } else {
    await singleFetchTrace(provider, taskId, program);
  }
}

async function cancelAction(taskId: string): Promise<void> {
  const provider = await getStateProvider();
  if (provider.isCloud) await authService.requireAuth();
  await withSpinner(
    t('commands.queue.cancel.cancelling', { taskId }),
    () => provider.queue.cancel(taskId),
    t('commands.queue.cancel.success')
  );
}

async function retryAction(taskId: string): Promise<void> {
  const provider = await getStateProvider();
  if (provider.isCloud) await authService.requireAuth();
  await withSpinner(
    t('commands.queue.retry.retrying', { taskId }),
    () => provider.queue.retry(taskId),
    t('commands.queue.retry.success')
  );
}
function validatePriorityRange(value: string | undefined, errorKey: string): void {
  if (value === undefined) return;
  const num = Number.parseInt(value, 10);
  if (Number.isNaN(num) || num < 1 || num > 5) throw new ValidationError(t(errorKey));
}
interface QueueListOptions {
  priorityMin?: string;
  priorityMax?: string;
  status?: string;
  search?: string;
  sort?: string;
  desc?: boolean;
  limit: string;
  team?: string;
}

function applyQueueFilters(
  items: GetTeamQueueItems_ResultSet1[],
  options: QueueListOptions
): GetTeamQueueItems_ResultSet1[] {
  let filtered = items;
  if (options.status) {
    filtered = filtered.filter(
      (item) => item.status?.toLowerCase() === options.status!.toLowerCase()
    );
  }
  if (options.priorityMin !== undefined) {
    const min = Number.parseInt(options.priorityMin, 10);
    filtered = filtered.filter((item) => item.priority != null && item.priority >= min);
  }
  if (options.priorityMax !== undefined) {
    const max = Number.parseInt(options.priorityMax, 10);
    filtered = filtered.filter((item) => item.priority != null && item.priority <= max);
  }
  if (options.search) {
    filtered = filtered.filter((item) =>
      searchInFields(item, options.search!, ['taskId', 'teamName', 'machineName', 'bridgeName'])
    );
  }
  return filtered;
}

function sortQueueItems(
  items: GetTeamQueueItems_ResultSet1[],
  options: QueueListOptions
): GetTeamQueueItems_ResultSet1[] {
  if (!options.sort) return items;
  const sortField = options.sort as keyof GetTeamQueueItems_ResultSet1;
  return items.sort((a, b) => {
    const result = compareValues(a[sortField], b[sortField]);
    return options.desc ? -result : result;
  });
}

function formatQueueItemForTable(item: GetTeamQueueItems_ResultSet1) {
  return {
    taskId: item.taskId,
    status: formatStatus(item.status ?? item.healthStatus),
    priority: item.priority ? formatPriority(item.priority) : '-',
    age: item.ageInMinutes == null ? '-' : formatAge(item.ageInMinutes),
    team: item.teamName ?? '-',
    machine: item.machineName ?? '-',
    bridge: item.bridgeName ?? '-',
    retries: item.retryCount == null ? '-' : formatRetryCount(item.retryCount),
    hasResponse: formatBoolean(item.hasResponse === true),
    error: item.lastFailureReason ? formatError(item.lastFailureReason) : '-',
  };
}

async function listAction(options: QueueListOptions, program: Command): Promise<void> {
  const provider = await getStateProvider();
  if (provider.isCloud) {
    await authService.requireAuth();
  }
  validatePriorityRange(options.priorityMin, 'errors.invalidPriorityMin');
  validatePriorityRange(options.priorityMax, 'errors.invalidPriorityMax');
  const opts = await configService.applyDefaults(options);
  if (!opts.team) {
    throw new ValidationError(t('errors.teamRequired'));
  }
  const rawItems = await withSpinner(
    t('commands.queue.list.fetching'),
    () =>
      provider.queue.list({
        teamName: opts.team as string,
        maxRecords: Number.parseInt(options.limit, 10),
      }),
    t('commands.queue.list.success')
  );
  const filteredItems = applyQueueFilters(
    rawItems as unknown as GetTeamQueueItems_ResultSet1[],
    options
  );
  const sortedItems = sortQueueItems(filteredItems, options);
  const format = program.opts().output as OutputFormat;
  if (format === 'table' && sortedItems.length > 0) {
    outputService.print(sortedItems.map(formatQueueItemForTable), format);
  } else {
    outputService.print(sortedItems, format);
  }
}

async function deleteAction(taskId: string, options: { force?: boolean }): Promise<void> {
  const provider = await getStateProvider();
  if (provider.isCloud) {
    await authService.requireAuth();
  }
  if (!options.force) {
    const { askConfirm } = await import('../utils/prompt.js');
    const confirm = await askConfirm(t('commands.queue.delete.confirm', { taskId }));
    if (!confirm) {
      outputService.info(t('prompts.cancelled'));
      return;
    }
  }
  await withSpinner(
    t('commands.queue.delete.deleting', { taskId }),
    () => provider.queue.delete(taskId),
    t('commands.queue.delete.success')
  );
}

const collectParam = (val: string, acc: string[]) => {
  acc.push(val);
  return acc;
};

function safe<T extends unknown[]>(fn: (...args: T) => Promise<void>) {
  return async (...args: T) => {
    try {
      await fn(...args);
    } catch (error) {
      handleError(error);
    }
  };
}

export function registerQueueCommands(program: Command): void {
  const queue = program.command('queue').description(t('commands.queue.description'));

  queue
    .command('list')
    .description(t('commands.queue.list.description'))
    .option('-t, --team <name>', t('options.team'))
    .option('--status <status>', t('options.filterStatus'))
    .option('--priority-min <n>', t('options.priorityMin'))
    .option('--priority-max <n>', t('options.priorityMax'))
    .option('--search <text>', t('options.searchQueue'))
    .option('--sort <field>', t('options.sortField'))
    .option('--desc', t('options.sortDesc'))
    .option('--limit <n>', t('options.limit'), '50')
    .action(safe(async (options: QueueListOptions) => listAction(options, program)));

  queue
    .command('create')
    .description(t('commands.queue.create.description'))
    .requiredOption('-f, --function <name>', t('options.functionName'))
    .option('-t, --team <name>', t('options.team'))
    .option('-m, --machine <name>', t('options.machine'))
    .option('-b, --bridge <name>', t('options.bridge'))
    .option('-p, --priority <1-5>', t('options.priority'), '3')
    .option('--param <key=value>', t('options.param'), collectParam, [])
    .option('--vault <json>', t('options.rawVault'))
    .action(
      safe(async (options) => {
        await createAction(options);
      })
    );

  queue
    .command('trace <taskId>')
    .description(t('commands.queue.trace.description'))
    .option('-w, --watch', t('options.watchUpdates'))
    .option('--interval <ms>', t('options.pollInterval'), '2000')
    .action(safe(async (taskId, options) => traceAction(taskId, options, program)));

  queue
    .command('cancel <taskId>')
    .description(t('commands.queue.cancel.description'))
    .action(safe(async (taskId) => cancelAction(taskId)));

  queue
    .command('retry <taskId>')
    .description(t('commands.queue.retry.description'))
    .action(safe(async (taskId) => retryAction(taskId)));

  queue
    .command('delete <taskId>')
    .description(t('commands.queue.delete.description'))
    .option('-f, --force', t('options.force'))
    .action(safe(async (taskId, options) => deleteAction(taskId, options)));
}
