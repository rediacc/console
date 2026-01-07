import { Command } from 'commander';
import {
  parseGetTeamQueueItems,
  parseGetQueueItemTrace,
  parseCreateQueueItem,
} from '@rediacc/shared/api';
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
      status: formatStatus(trace.status ?? 'UNKNOWN'),
      age: trace.ageInMinutes != null ? formatAge(trace.ageInMinutes) : '-',
      priority: trace.priority ? formatPriority(trace.priority) : '-',
      retries: trace.retryCount != null ? formatRetryCount(trace.retryCount) : '-',
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

export async function createAction(options: CreateActionOptions): Promise<{ taskId?: string }> {
  await authService.requireAuth();
  const opts = await contextService.applyDefaults(options);

  if (!opts.team) {
    throw new ValidationError(t('errors.teamRequired'));
  }

  let queueVault: string;

  if (options.vault) {
    // Use provided vault directly (for scripts/CI that need raw vault control)
    queueVault = options.vault;
  } else {
    // Parse parameters
    const params: Record<string, string> = {};
    for (const param of options.param ?? []) {
      const [key, ...valueParts] = param.split('=');
      params[key] = valueParts.join('=');
    }

    // Validate function parameters before building vault (early error detection)
    if (isBridgeFunction(options.function)) {
      const validationResult = safeValidateFunctionParams(options.function, params);
      if (!validationResult.success) {
        throw new ValidationError(
          t('errors.invalidFunctionParams', {
            function: options.function,
            errors: getValidationErrors(validationResult),
          })
        );
      }
    }

    // Get language from context for task output localization
    const language = await contextService.getLanguage();

    // Build proper queue vault using the queue service
    queueVault = await withSpinner(
      t('commands.queue.create.buildingVault'),
      () =>
        queueService.buildQueueVault({
          teamName: opts.team as string,
          machineName: opts.machine,
          bridgeName: opts.bridge,
          functionName: options.function,
          params,
          priority: parseInt(options.priority, 10),
          language,
        }),
      t('commands.queue.create.vaultBuilt')
    );
  }

  const apiResponse = await withSpinner(
    t('commands.queue.create.creating', { function: options.function }),
    () =>
      typedApi.CreateQueueItem({
        teamName: opts.team as string,
        machineName: opts.machine as string,
        bridgeName: opts.bridge as string,
        vaultContent: queueVault,
        priority: parseInt(options.priority, 10),
      }),
    t('commands.queue.create.success')
  );

  const response = parseCreateQueueItem(apiResponse as never);

  if (response.taskId) {
    outputService.success(t('commands.queue.create.taskId', { taskId: response.taskId }));
  }

  return { taskId: response.taskId ?? undefined };
}

export async function traceAction(
  taskId: string,
  options: TraceActionOptions,
  program: Command
): Promise<void> {
  await authService.requireAuth();

  const fetchTrace = async () => {
    const apiResponse = await typedApi.GetQueueItemTrace({ taskId });
    return parseGetQueueItemTrace(apiResponse as never);
  };

  if (options.watch) {
    // Watch mode - poll until complete
    const interval = parseInt(options.interval, 10);
    let isComplete = false;

    const spinner = startSpinner(t('commands.queue.trace.watching'));

    while (!isComplete) {
      const trace = await fetchTrace();
      const summary = mapTraceToSummary(trace);

      if (summary) {
        const statusText = formatStatus(summary.status ?? 'UNKNOWN');
        const ageText =
          summary.ageInMinutes != null ? formatAge(summary.ageInMinutes) : t('common.unknown');

        // Extract progress percentage from console output if available
        const percentage = extractMostRecentProgress(summary.consoleOutput ?? '');
        const progressText =
          percentage !== null ? `${percentage}%` : (summary.progress ?? t('common.inProgress'));

        if (spinner) {
          spinner.text = `${statusText} | ${t('commands.queue.trace.age')}: ${ageText} | ${progressText}`;
        }

        const terminalStatuses = ['COMPLETED', 'FAILED', 'CANCELLED'];
        const status = summary.status?.toUpperCase();
        if (status && terminalStatuses.includes(status)) {
          isComplete = true;
          const success = status === 'COMPLETED';
          stopSpinner(
            success,
            t('commands.queue.trace.finalStatus', { status: formatStatus(status) })
          );

          if (!success && summary.lastFailureReason) {
            outputService.error(t('commands.queue.trace.errorDetails'));
            outputService.error(formatError(summary.lastFailureReason, true));
          }

          printTrace(summary, program);
        }
      }

      if (!isComplete) {
        await new Promise((resolve) => setTimeout(resolve, interval));
      }
    }
  } else {
    // Single fetch
    const trace = await withSpinner(
      t('commands.queue.trace.fetching'),
      fetchTrace,
      t('commands.queue.trace.fetched')
    );

    const summary = mapTraceToSummary(trace);

    if (summary) {
      // Show formatted error if task failed
      if (summary.status === 'FAILED' && summary.lastFailureReason) {
        outputService.error(t('commands.queue.trace.errorDetails'));
        outputService.error(formatError(summary.lastFailureReason, true));
        outputService.info(''); // Empty line for spacing
      }

      // Output trace using helper function
      printTrace(summary, program);
    } else {
      outputService.info(t('commands.queue.trace.noTrace'));
    }
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
    .action(async (options) => {
      try {
        await authService.requireAuth();

        // Validate priority-min if provided (before checking team to give clearer error)
        if (options.priorityMin !== undefined) {
          const min = parseInt(options.priorityMin, 10);
          if (isNaN(min) || min < 1 || min > 5) {
            throw new ValidationError(t('errors.invalidPriorityMin'));
          }
        }

        // Validate priority-max if provided (before checking team to give clearer error)
        if (options.priorityMax !== undefined) {
          const max = parseInt(options.priorityMax, 10);
          if (isNaN(max) || max < 1 || max > 5) {
            throw new ValidationError(t('errors.invalidPriorityMax'));
          }
        }

        const opts = await contextService.applyDefaults(options);

        if (!opts.team) {
          throw new ValidationError(t('errors.teamRequired'));
        }

        const apiResponse = await withSpinner(
          t('commands.queue.list.fetching'),
          () =>
            typedApi.GetTeamQueueItems({
              teamName: opts.team as string,
              maxRecords: parseInt(options.limit, 10),
            }),
          t('commands.queue.list.success')
        );

        const response = parseGetTeamQueueItems(apiResponse as never);
        let items = response.items;

        // Filter by status if specified
        if (options.status) {
          items = items.filter(
            (item: GetTeamQueueItems_ResultSet1) =>
              item.status?.toLowerCase() === options.status.toLowerCase()
          );
        }

        // Filter by priority-min if specified
        if (options.priorityMin !== undefined) {
          const min = parseInt(options.priorityMin, 10);
          items = items.filter(
            (item: GetTeamQueueItems_ResultSet1) => item.priority != null && item.priority >= min
          );
        }

        // Filter by priority-max if specified
        if (options.priorityMax !== undefined) {
          const max = parseInt(options.priorityMax, 10);
          items = items.filter(
            (item: GetTeamQueueItems_ResultSet1) => item.priority != null && item.priority <= max
          );
        }

        // Search filter
        if (options.search) {
          items = items.filter((item: GetTeamQueueItems_ResultSet1) =>
            searchInFields(item, options.search, [
              'taskId',
              'teamName',
              'machineName',
              'bridgeName',
            ])
          );
        }

        // Sort results
        if (options.sort) {
          const sortField = options.sort as keyof GetTeamQueueItems_ResultSet1;
          items.sort((a: GetTeamQueueItems_ResultSet1, b: GetTeamQueueItems_ResultSet1) => {
            const result = compareValues(a[sortField], b[sortField]);
            return options.desc ? -result : result;
          });
        }

        const format = program.opts().output as OutputFormat;

        // Format items for better CLI display (table format only)
        if (format === 'table' && items.length > 0) {
          const formattedItems = items.map((item: GetTeamQueueItems_ResultSet1) => ({
            taskId: item.taskId,
            status: formatStatus(item.status ?? item.healthStatus),
            priority: item.priority ? formatPriority(item.priority) : '-',
            age: item.ageInMinutes != null ? formatAge(item.ageInMinutes) : '-',
            team: item.teamName ?? '-',
            machine: item.machineName ?? '-',
            bridge: item.bridgeName ?? '-',
            retries: item.retryCount != null ? formatRetryCount(item.retryCount) : '-',
            hasResponse: formatBoolean(item.hasResponse === true),
            error: item.lastFailureReason ? formatError(item.lastFailureReason) : '-',
          }));
          outputService.print(formattedItems, format);
        } else {
          outputService.print(items, format);
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
