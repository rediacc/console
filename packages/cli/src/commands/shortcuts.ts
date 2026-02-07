import { Command } from 'commander';
import { executeBridgeFunction } from './bridge-executor.js';
import {
  cancelAction,
  coerceCliParams,
  parseParamOptions,
  retryAction,
  traceAction,
} from './queue.js';
import { t } from '../i18n/index.js';
import { handleError } from '../utils/errors.js';

export function registerShortcuts(program: Command): void {
  // run - escape hatch for queue create with optional watch
  // In local mode, executes directly via renet subprocess
  program
    .command('run <function>')
    .description(t('commands.shortcuts.run.description'))
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
    .option(
      '--extra-machine <name:ip:user>',
      t('options.extraMachine'),
      (val: string, acc: string[]) => {
        acc.push(val);
        return acc;
      },
      [] as string[]
    )
    .option('-w, --watch', t('options.watch'))
    .option('--debug', t('options.debug'))
    .action(async (functionName, options) => {
      // Parse --param key=value strings into typed params
      const rawParams = parseParamOptions(options.param);
      const params = coerceCliParams(functionName, rawParams);

      await executeBridgeFunction(
        {
          functionName,
          machine: options.machine,
          team: options.team,
          bridge: options.bridge,
          params,
          extraMachine: options.extraMachine,
          debug: options.debug,
          watch: options.watch,
          priority: options.priority,
        },
        program
      );
    });

  // trace - shortcut for queue trace
  program
    .command('trace <taskId>')
    .description(t('commands.shortcuts.trace.description'))
    .option('-w, --watch', t('options.watchUpdates'))
    .option('--interval <ms>', t('options.pollInterval'), '2000')
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
    .description(t('commands.shortcuts.cancel.description'))
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
    .description(t('commands.shortcuts.retry.description'))
    .action(async (taskId) => {
      try {
        await retryAction(taskId);
      } catch (error) {
        handleError(error);
      }
    });
}
