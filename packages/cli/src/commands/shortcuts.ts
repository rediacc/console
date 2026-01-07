import { Command } from 'commander';
import {
  isBridgeFunction,
  safeValidateFunctionParams,
  getValidationErrors,
} from '@rediacc/shared/queue-vault';
import {
  type CreateActionOptions,
  cancelAction,
  createAction,
  retryAction,
  traceAction,
} from './queue.js';
import { t } from '../i18n/index.js';
import { contextService } from '../services/context.js';
import { localExecutorService } from '../services/local-executor.js';
import { outputService } from '../services/output.js';
import { handleError, ValidationError } from '../utils/errors.js';

/**
 * Run function in local mode (direct renet execution).
 */
async function runLocalMode(
  functionName: string,
  options: { machine?: string; param?: string[]; debug?: boolean }
): Promise<void> {
  // Get default machine from context if not specified
  const machineName = options.machine ?? (await contextService.getMachine());

  if (!machineName) {
    throw new ValidationError(t('errors.machineRequiredLocal'));
  }

  // Parse parameters
  const params: Record<string, unknown> = {};
  for (const param of options.param ?? []) {
    const [key, ...valueParts] = param.split('=');
    params[key] = valueParts.join('=');
  }

  // Validate function parameters before execution (early error detection)
  if (isBridgeFunction(functionName)) {
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

  outputService.info(
    t('commands.shortcuts.run.executingLocal', { function: functionName, machine: machineName })
  );

  const result = await localExecutorService.execute({
    functionName,
    machineName,
    params,
    debug: options.debug,
  });

  if (result.success) {
    outputService.success(
      t('commands.shortcuts.run.completedLocal', { duration: result.durationMs })
    );
  } else {
    outputService.error(t('commands.shortcuts.run.failedLocal', { error: result.error }));
    process.exitCode = result.exitCode;
  }
}

/**
 * Run function in cloud mode (queue-based execution).
 */
async function runCloudMode(
  functionName: string,
  options: {
    team?: string;
    machine?: string;
    bridge?: string;
    priority?: string;
    param?: string[];
    watch?: boolean;
  },
  program: Command
): Promise<void> {
  // Build options for createAction
  const createOptions: CreateActionOptions = {
    ...options,
    function: functionName,
    priority: options.priority ?? '3',
  };

  // Create the queue item
  const result = await createAction(createOptions);

  // Watch if requested and we have a taskId
  if (options.watch && result.taskId) {
    outputService.info(t('commands.shortcuts.run.watching'));
    await traceAction(result.taskId, { watch: true, interval: '2000' }, program);
  }
}

export function registerShortcuts(program: Command): void {
  // run - shortcut for queue create with optional watch
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
    .option('-w, --watch', t('options.watch'))
    .option('--debug', t('options.debug'))
    .action(async (functionName, options) => {
      try {
        // Check if we're in local mode
        const isLocal = await contextService.isLocalMode();

        if (isLocal) {
          // Local mode: Execute directly via renet
          await runLocalMode(functionName, options);
        } else {
          // Cloud mode: Use existing queue-based flow
          await runCloudMode(functionName, options, program);
        }
      } catch (error) {
        handleError(error);
      }
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
