import { Command } from 'commander';
import { DEFAULTS } from '@rediacc/shared/config';
import {
  type CreateActionOptions,
  coerceCliParams,
  createAction,
  parseParamOptions,
  traceAction,
  validateFunctionParams,
} from './queue.js';
import { t } from '../i18n/index.js';
import { getStateProvider } from '../providers/index.js';
import { contextService } from '../services/context.js';
import { localExecutorService } from '../services/local-executor.js';
import { outputService } from '../services/output.js';
import { handleError, ValidationError } from '../utils/errors.js';

interface RunLocalOptions {
  machine?: string;
  param?: string[];
  extraMachine?: string[];
  debug?: boolean;
}

/** Resolve machine name and parse+validate function params (shared by local and S3 modes). */
async function resolveRunParams(
  functionName: string,
  options: RunLocalOptions
): Promise<{ machineName: string; params: Record<string, unknown> }> {
  const machineName = options.machine ?? (await contextService.getMachine());
  if (!machineName) {
    throw new ValidationError(t('errors.machineRequiredLocal'));
  }
  const rawParams = parseParamOptions(options.param);
  const params = coerceCliParams(functionName, rawParams);
  validateFunctionParams(functionName, params);
  return { machineName, params };
}

function handleExecutionResult(result: {
  success: boolean;
  durationMs?: number;
  error?: string;
  exitCode?: number;
}): void {
  if (result.success) {
    outputService.success(
      t('commands.shortcuts.run.completedLocal', { duration: result.durationMs })
    );
  } else {
    outputService.error(t('commands.shortcuts.run.failedLocal', { error: result.error }));
    process.exitCode = result.exitCode;
  }
}

async function runLocalMode(functionName: string, options: RunLocalOptions): Promise<void> {
  const { machineName, params } = await resolveRunParams(functionName, options);
  outputService.info(
    t('commands.shortcuts.run.executingLocal', { function: functionName, machine: machineName })
  );

  // Parse --extra-machine entries (format: name:ip:user)
  let extraMachines: Record<string, { ip: string; user: string }> | undefined;
  if (options.extraMachine?.length) {
    extraMachines = {};
    for (const entry of options.extraMachine) {
      const firstColon = entry.indexOf(':');
      const lastColon = entry.lastIndexOf(':');
      if (firstColon === -1 || firstColon === lastColon) {
        throw new ValidationError(
          `Invalid --extra-machine format: '${entry}'. Expected name:ip:user`
        );
      }
      const name = entry.slice(0, firstColon);
      const ip = entry.slice(firstColon + 1, lastColon);
      const user = entry.slice(lastColon + 1);
      extraMachines[name] = { ip, user };
    }
  }

  const result = await localExecutorService.execute({
    functionName,
    machineName,
    params,
    extraMachines,
    debug: options.debug,
  });
  handleExecutionResult(result);
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
    priority: options.priority ?? String(DEFAULTS.PRIORITY.QUEUE_PRIORITY),
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
      try {
        const provider = await getStateProvider();

        switch (provider.mode) {
          case 'cloud':
            await runCloudMode(functionName, options, program);
            break;
          default:
            await runLocalMode(functionName, options);
            break;
        }
      } catch (error) {
        handleError(error);
      }
    });

}
