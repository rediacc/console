import { Command } from 'commander';
import { outputService } from '../services/output.js';
import { handleError } from '../utils/errors.js';
import {
  createAction,
  traceAction,
  cancelAction,
  retryAction,
  type CreateActionOptions,
} from './queue.js';

export function registerShortcuts(program: Command): void {
  // run - shortcut for queue create with optional watch
  program
    .command('run <function>')
    .description('Run a function (shortcut for: queue create)')
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
    .option('-w, --watch', 'Watch for completion')
    .action(async (functionName, options) => {
      try {
        // Build options for createAction
        const createOptions: CreateActionOptions = {
          ...options,
          function: functionName,
        };

        // Create the queue item
        const result = await createAction(createOptions);

        // Watch if requested and we have a taskId
        if (options.watch && result.taskId) {
          outputService.info('Watching for completion...');
          await traceAction(result.taskId, { watch: true, interval: '2000' }, program);
        }
      } catch (error) {
        handleError(error);
      }
    });

  // trace - shortcut for queue trace
  program
    .command('trace <taskId>')
    .description('Trace a task (shortcut for: queue trace)')
    .option('-w, --watch', 'Watch for updates')
    .option('--interval <ms>', 'Poll interval in milliseconds', '2000')
    .action(async (taskId, options) => {
      try {
        await traceAction(taskId, options, program);
      } catch (error) {
        handleError(error);
      }
    });

  // cancel - shortcut for queue cancel
  program
    .command('cancel <taskId>')
    .description('Cancel a task (shortcut for: queue cancel)')
    .action(async (taskId) => {
      try {
        await cancelAction(taskId);
      } catch (error) {
        handleError(error);
      }
    });

  // retry - shortcut for queue retry
  program
    .command('retry <taskId>')
    .description('Retry a failed task (shortcut for: queue retry)')
    .action(async (taskId) => {
      try {
        await retryAction(taskId);
      } catch (error) {
        handleError(error);
      }
    });
}
