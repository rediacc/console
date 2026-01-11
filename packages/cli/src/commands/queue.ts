import { Command } from 'commander';
import {
  parseGetTeamQueueItems,
  parseGetQueueItemTrace,
  parseCreateQueueItem,
} from '@rediacc/shared/api';
import { DEFAULTS } from '@rediacc/shared/config';
import {
  isBridgeFunction,
  safeValidateFunctionParams,
  getValidationErrors,
} from '@rediacc/shared/queue-vault';
import type {
  QueueTrace,
  QueueTraceSummary,
  GetTeamQueueItems_ResultSet1,
} from '@rediacc/shared/types';
import {
  searchInFields,
  compareValues,
  extractMostRecentProgress,
  unescapeLogOutput,
  parseLogOutput,
} from '@rediacc/shared/utils';
import { t } from '../i18n/index.js';
import { typedApi } from '../services/api.js';
import { authService } from '../services/auth.js';
import { contextService } from '../services/context.js';
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

// Exported action handlers for reuse in shortcuts

/**
 * Helper function to format and print trace output
 * Reduces duplication between watch mode and single-fetch mode
 */
function printTrace(trace: QueueTraceSummary, program: Command): void {
  const format = program.opts().output as OutputFormat;

  if (format === 'table') {
    // Print task summary
    const formattedTrace = {
      taskId: trace.taskId,
      status: formatStatus(trace.status ?? DEFAULTS.STATUS.UNKNOWN_UPPERCASE),
      age: trace.ageInMinutes == null ? '-' : formatAge(trace.ageInMinutes),
      priority: trace.priority ? formatPriority(trace.priority) : '-',
      retries: trace.retryCount == null ? '-' : formatRetryCount(trace.retryCount),
      progress: trace.progress ?? '-',
    };
    outputService.print(formattedTrace, format);

    // Print structured console output if available
    if (trace.consoleOutput) {
      outputService.info(''); // Empty line
      outputService.info(getLogHeader());
      const parsedLogs = parseLogOutput(trace.consoleOutput);
      outputService.info(formatLogOutput(parsedLogs));
    }
  } else {
    outputService.print(trace, format);
  }
}

function mapTraceToSummary(trace: QueueTrace): QueueTraceSummary | null {
  const summary = trace.summary;
  const details = trace.queueDetails;
  if (!summary && !details) {
    return null;
  }

  return {
    taskId: summary?.taskId ?? details?.taskId ?? undefined,
    status: summary?.status ?? (details?.status as QueueTraceSummary['status']),
    healthStatus:
      summary?.healthStatus ?? (details?.healthStatus as QueueTraceSummary['healthStatus']),
    progress: summary?.progress,
    consoleOutput: summary?.consoleOutput ? unescapeLogOutput(summary.consoleOutput) : undefined,
    errorMessage: summary?.errorMessage ? unescapeLogOutput(summary.errorMessage) : undefined,
    lastFailureReason:
      (summary?.lastFailureReason ?? details?.lastFailureReason)
        ? unescapeLogOutput(summary?.lastFailureReason ?? details?.lastFailureReason ?? '')
        : undefined,
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

function parseParamOptions(paramOptions: string[] | undefined): Record<string, string> {
  const params: Record<string, string> = {};
  for (const param of paramOptions ?? []) {
    const [key, ...valueParts] = param.split('=');
    params[key] = valueParts.join('=');
  }
  return params;
}

function validateFunctionParams(functionName: string, params: Record<string, string>): void {
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

  const language = await contextService.getLanguage();

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
  await authService.requireAuth();
  const opts = await contextService.applyDefaults(options);

  if (!opts.team) {
    throw new ValidationError(t('errors.teamRequired'));
  }

  const queueVault = options.vault ?? (await buildQueueVaultFromParams(opts, options));

  const apiResponse = await withSpinner(
    t('commands.queue.create.creating', { function: options.function }),
    () =>
      typedApi.CreateQueueItem({
        teamName: opts.team as string,
        machineName: opts.machine as string,
        bridgeName: opts.bridge as string,
        vaultContent: queueVault,
        priority: Number.parseInt(options.priority, 10),
      }),
    t('commands.queue.create.success')
  );

  const response = parseCreateQueueItem(apiResponse as never);

  if (response.taskId) {
    outputService.success(t('commands.queue.create.taskId', { taskId: response.taskId }));
  }

  return { taskId: response.taskId ?? undefined };
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

  if (!success) {
    displayFailureReason(summary);
  }

  printTrace(summary, program);
}

async function watchTraceLoop(taskId: string, interval: number, program: Command): Promise<void> {
  const spinner = startSpinner(t('commands.queue.trace.watching'));

  for (;;) {
    const apiResponse = await typedApi.GetQueueItemTrace({ taskId });
    const trace = parseGetQueueItemTrace(apiResponse as never);
    const summary = mapTraceToSummary(trace);

    if (!summary) {
      await new Promise((resolve) => setTimeout(resolve, interval));
      continue;
    }

    if (spinner) {
      spinner.text = buildSpinnerText(summary);
    }

    if (isTerminalStatus(summary.status)) {
      handleTerminalStatus(summary, program);
      return;
    }

    await new Promise((resolve) => setTimeout(resolve, interval));
  }
}

async function singleFetchTrace(taskId: string, program: Command): Promise<void> {
  const trace = await withSpinner(
    t('commands.queue.trace.fetching'),
    async () => {
      const apiResponse = await typedApi.GetQueueItemTrace({ taskId });
      return parseGetQueueItemTrace(apiResponse as never);
    },
    t('commands.queue.trace.fetched')
  );

  const summary = mapTraceToSummary(trace);

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
  await authService.requireAuth();

  if (options.watch) {
    const interval = Number.parseInt(options.interval, 10);
    await watchTraceLoop(taskId, interval, program);
  } else {
    await singleFetchTrace(taskId, program);
  }
}

export async function cancelAction(taskId: string): Promise<void> {
  await authService.requireAuth();

  await withSpinner(
    t('commands.queue.cancel.cancelling', { taskId }),
    () => typedApi.CancelQueueItem({ taskId }),
    t('commands.queue.cancel.success')
  );
}

export async function retryAction(taskId: string): Promise<void> {
  await authService.requireAuth();

  await withSpinner(
    t('commands.queue.retry.retrying', { taskId }),
    () => typedApi.RetryFailedQueueItem({ taskId }),
    t('commands.queue.retry.success')
  );
}

function validatePriorityRange(value: string | undefined, errorKey: string): void {
  if (value === undefined) return;
  const num = Number.parseInt(value, 10);
  if (Number.isNaN(num) || num < 1 || num > 5) {
    throw new ValidationError(t(errorKey));
  }
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

export function registerQueueCommands(program: Command): void {
  const queue = program.command('queue').description(t('commands.queue.description'));

  // queue list
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
    .action(async (options: QueueListOptions) => {
      try {
        await authService.requireAuth();

        validatePriorityRange(options.priorityMin, 'errors.invalidPriorityMin');
        validatePriorityRange(options.priorityMax, 'errors.invalidPriorityMax');

        const opts = await contextService.applyDefaults(options);

        if (!opts.team) {
          throw new ValidationError(t('errors.teamRequired'));
        }

        const apiResponse = await withSpinner(
          t('commands.queue.list.fetching'),
          () =>
            typedApi.GetTeamQueueItems({
              teamName: opts.team as string,
              maxRecords: Number.parseInt(options.limit, 10),
            }),
          t('commands.queue.list.success')
        );

        const response = parseGetTeamQueueItems(apiResponse as never);
        const filteredItems = applyQueueFilters(response.items, options);
        const sortedItems = sortQueueItems(filteredItems, options);

        const format = program.opts().output as OutputFormat;

        if (format === 'table' && sortedItems.length > 0) {
          const formattedItems = sortedItems.map(formatQueueItemForTable);
          outputService.print(formattedItems, format);
        } else {
          outputService.print(sortedItems, format);
        }
      } catch (error) {
        handleError(error);
      }
    });

  // queue create
  queue
    .command('create')
    .description(t('commands.queue.create.description'))
    .requiredOption('-f, --function <name>', t('options.functionName'))
    .option('-t, --team <name>', t('options.team'))
    .option('-m, --machine <name>', t('options.machine'))
    .option('-b, --bridge <name>', t('options.bridge'))
    .option('-p, --priority <1-5>', t('options.priority'), '3')
    .option(
      '--param <key=value>',
      t('options.param'),
      (val, acc: string[]) => {
        acc.push(val);
        return acc;
      },
      []
    )
    .option('--vault <json>', t('options.rawVault'))
    .action(async (options) => {
      try {
        await createAction(options);
      } catch (error) {
        handleError(error);
      }
    });

  // queue trace
  queue
    .command('trace <taskId>')
    .description(t('commands.queue.trace.description'))
    .option('-w, --watch', t('options.watchUpdates'))
    .option('--interval <ms>', t('options.pollInterval'), '2000')
    .action(async (taskId, options) => {
      try {
        await traceAction(taskId, options, program);
      } catch (error) {
        handleError(error);
      }
    });

  // queue cancel
  queue
    .command('cancel <taskId>')
    .description(t('commands.queue.cancel.description'))
    .action(async (taskId) => {
      try {
        await cancelAction(taskId);
      } catch (error) {
        handleError(error);
      }
    });

  // queue retry
  queue
    .command('retry <taskId>')
    .description(t('commands.queue.retry.description'))
    .action(async (taskId) => {
      try {
        await retryAction(taskId);
      } catch (error) {
        handleError(error);
      }
    });

  // queue delete
  queue
    .command('delete <taskId>')
    .description(t('commands.queue.delete.description'))
    .option('-f, --force', t('options.force'))
    .action(async (taskId, options) => {
      try {
        await authService.requireAuth();

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
          () => typedApi.DeleteQueueItem({ taskId }),
          t('commands.queue.delete.success')
        );
      } catch (error) {
        handleError(error);
      }
    });
}
