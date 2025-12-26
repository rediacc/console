import { Command } from 'commander';
import type { QueueTrace, QueueTraceSummary } from '@rediacc/shared/types';
import { api } from '../services/api.js';
import { authService } from '../services/auth.js';
import { contextService } from '../services/context.js';
import { outputService } from '../services/output.js';
import { queueService } from '../services/queue.js';
import { handleError, ValidationError } from '../utils/errors.js';
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
    const formattedTrace = {
      taskId: trace.taskId,
      status: formatStatus(trace.status ?? 'UNKNOWN'),
      age: trace.ageInMinutes != null ? formatAge(trace.ageInMinutes) : '-',
      priority: trace.priority ? formatPriority(trace.priority) : '-',
      retries: trace.retryCount != null ? formatRetryCount(trace.retryCount) : '-',
      progress: trace.progress ?? '-',
      consoleOutput: trace.consoleOutput ?? '-',
    };
    outputService.print(formattedTrace, format);
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
    consoleOutput: summary?.consoleOutput,
    errorMessage: summary?.errorMessage,
    lastFailureReason: summary?.lastFailureReason ?? details?.lastFailureReason ?? undefined,
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
    throw new ValidationError('Team name required. Use --team or set context.');
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

    // Build proper queue vault using the queue service
    queueVault = await withSpinner(
      'Building queue vault...',
      () =>
        queueService.buildQueueVault({
          teamName: opts.team as string,
          machineName: opts.machine,
          bridgeName: opts.bridge,
          functionName: options.function,
          params,
          priority: parseInt(options.priority, 10),
        }),
      'Queue vault built'
    );
  }

  const response = await withSpinner(
    `Creating queue item for function "${options.function}"...`,
    () =>
      api.queue.create({
        teamName: opts.team as string,
        machineName: opts.machine as string,
        bridgeName: opts.bridge as string,
        vaultContent: queueVault,
        priority: parseInt(options.priority, 10),
      }),
    'Queue item created'
  );

  if (response.taskId) {
    outputService.success(`Task ID: ${response.taskId}`);
  }

  return { taskId: response.taskId ?? undefined };
}

export async function traceAction(
  taskId: string,
  options: TraceActionOptions,
  program: Command
): Promise<void> {
  await authService.requireAuth();

  const fetchTrace = async () => api.queue.getTrace({ taskId });

  if (options.watch) {
    // Watch mode - poll until complete
    const interval = parseInt(options.interval, 10);
    let isComplete = false;

    const spinner = startSpinner('Watching queue item...');

    while (!isComplete) {
      const trace = await fetchTrace();
      const summary = mapTraceToSummary(trace);

      if (summary) {
        const statusText = formatStatus(summary.status ?? 'UNKNOWN');
        const ageText = summary.ageInMinutes != null ? formatAge(summary.ageInMinutes) : 'unknown';
        const progressText = summary.progress ?? 'No progress';
        if (spinner) {
          spinner.text = `${statusText} | Age: ${ageText} | ${progressText}`;
        }

        const terminalStatuses = ['COMPLETED', 'FAILED', 'CANCELLED'];
        const status = summary.status?.toUpperCase();
        if (status && terminalStatuses.includes(status)) {
          isComplete = true;
          const success = status === 'COMPLETED';
          stopSpinner(success, `Final status: ${formatStatus(status)}`);

          if (!success && summary.lastFailureReason) {
            outputService.error('\nError Details:');
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
    const trace = await withSpinner('Fetching queue trace...', fetchTrace, 'Trace fetched');

    const summary = mapTraceToSummary(trace);

    if (summary) {
      // Show formatted error if task failed
      if (summary.status === 'FAILED' && summary.lastFailureReason) {
        outputService.error('\nError Details:');
        outputService.error(formatError(summary.lastFailureReason, true));
        outputService.info(''); // Empty line for spacing
      }

      // Output trace using helper function
      printTrace(summary, program);
    } else {
      outputService.info('No trace found for this task');
    }
  }
}

export async function cancelAction(taskId: string): Promise<void> {
  await authService.requireAuth();

  await withSpinner(
    `Cancelling task ${taskId}...`,
    () => api.queue.cancel({ taskId }),
    'Task cancelled'
  );
}

export async function retryAction(taskId: string): Promise<void> {
  await authService.requireAuth();

  await withSpinner(
    `Retrying task ${taskId}...`,
    () => api.queue.retry({ taskId }),
    'Task retry initiated'
  );
}

export function registerQueueCommands(program: Command): void {
  const queue = program.command('queue').description('Queue management commands');

  // queue list
  queue
    .command('list')
    .description('List queue items')
    .option('-t, --team <name>', 'Team name')
    .option('--status <status>', 'Filter by status')
    .option('--priority-min <n>', 'Minimum priority (1-5)')
    .option('--priority-max <n>', 'Maximum priority (1-5)')
    .option('--limit <n>', 'Limit results', '50')
    .action(async (options) => {
      try {
        await authService.requireAuth();

        // Validate priority-min if provided (before checking team to give clearer error)
        if (options.priorityMin !== undefined) {
          const min = parseInt(options.priorityMin, 10);
          if (isNaN(min) || min < 1 || min > 5) {
            throw new ValidationError('Minimum priority must be between 1 and 5');
          }
        }

        // Validate priority-max if provided (before checking team to give clearer error)
        if (options.priorityMax !== undefined) {
          const max = parseInt(options.priorityMax, 10);
          if (isNaN(max) || max < 1 || max > 5) {
            throw new ValidationError('Maximum priority must be between 1 and 5');
          }
        }

        const opts = await contextService.applyDefaults(options);

        if (!opts.team) {
          throw new ValidationError('Team name required. Use --team or set context.');
        }

        const response = await withSpinner(
          'Fetching queue items...',
          () =>
            api.queue.list(opts.team as string, {
              maxRecords: parseInt(options.limit, 10),
            }),
          'Queue items fetched'
        );

        let items = response.items;

        // Filter by status if specified
        if (options.status) {
          items = items.filter(
            (item) => item.status?.toLowerCase() === options.status.toLowerCase()
          );
        }

        // Filter by priority-min if specified
        if (options.priorityMin !== undefined) {
          const min = parseInt(options.priorityMin, 10);
          items = items.filter((item) => item.priority !== undefined && item.priority >= min);
        }

        // Filter by priority-max if specified
        if (options.priorityMax !== undefined) {
          const max = parseInt(options.priorityMax, 10);
          items = items.filter((item) => item.priority !== undefined && item.priority <= max);
        }

        const format = program.opts().output as OutputFormat;

        // Format items for better CLI display (table format only)
        if (format === 'table' && items.length > 0) {
          const formattedItems = items.map((item) => ({
            taskId: item.taskId,
            status: formatStatus(item.status ?? item.healthStatus),
            priority: item.priority ? formatPriority(item.priority) : '-',
            age: item.ageInMinutes != null ? formatAge(item.ageInMinutes) : '-',
            team: item.teamName ?? '-',
            machine: item.machineName ?? '-',
            bridge: item.bridgeName ?? '-',
            retries: item.retryCount != null ? formatRetryCount(item.retryCount) : '-',
            hasResponse: formatBoolean(item.hasResponse === 1),
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
    .description('Create a new queue item')
    .requiredOption('-f, --function <name>', 'Function name')
    .option('-t, --team <name>', 'Team name')
    .option('-m, --machine <name>', 'Machine name')
    .option('-b, --bridge <name>', 'Bridge name')
    .option('-p, --priority <1-5>', 'Priority (1=highest)', '3')
    .option(
      '--param <key=value>',
      'Function parameters',
      (val, acc: string[]) => {
        acc.push(val);
        return acc;
      },
      []
    )
    .option('--vault <json>', 'Raw vault content (bypasses auto-build)')
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
    .description('Trace a queue item')
    .option('-w, --watch', 'Watch for updates')
    .option('--interval <ms>', 'Poll interval in milliseconds', '2000')
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
    .description('Cancel a queue item')
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
    .description('Retry a failed queue item')
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
    .description('Delete a queue item')
    .option('-f, --force', 'Skip confirmation')
    .action(async (taskId, options) => {
      try {
        await authService.requireAuth();

        if (!options.force) {
          const { askConfirm } = await import('../utils/prompt.js');
          const confirm = await askConfirm(`Delete task ${taskId}? This cannot be undone.`);
          if (!confirm) {
            outputService.info('Cancelled');
            return;
          }
        }

        await withSpinner(
          `Deleting task ${taskId}...`,
          () => api.queue.delete({ taskId }),
          'Task deleted'
        );
      } catch (error) {
        handleError(error);
      }
    });
}
