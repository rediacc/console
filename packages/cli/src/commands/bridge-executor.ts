import { Command } from 'commander';
import { DEFAULTS } from '@rediacc/shared/config';
import {
  type CreateActionOptions,
  createAction,
  traceAction,
  validateFunctionParams,
} from './queue.js';
import { t } from '../i18n/index.js';
import { getStateProvider } from '../providers/index.js';
import { contextService } from '../services/context.js';
import { localExecutorService } from '../services/local-executor.js';
import { outputService } from '../services/output.js';
import { handleError, ValidationError } from '../utils/errors.js';

export interface BridgeExecuteOptions {
  functionName: string;
  machine?: string;
  team?: string;
  bridge?: string;
  params: Record<string, unknown>;
  extraMachine?: string[];
  debug?: boolean;
  watch?: boolean;
  priority?: string;
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

async function runLocalMode(options: BridgeExecuteOptions): Promise<void> {
  const machineName = options.machine ?? (await contextService.getMachine());
  if (!machineName) {
    throw new ValidationError(t('errors.machineRequiredLocal'));
  }
  validateFunctionParams(options.functionName, options.params);

  outputService.info(
    t('commands.shortcuts.run.executingLocal', {
      function: options.functionName,
      machine: machineName,
    })
  );

  let extraMachines: Record<string, { ip: string; user: string }> | undefined;
  if (options.extraMachine?.length) {
    extraMachines = {};
    for (const entry of options.extraMachine) {
      const parts = entry.split(':');
      if (parts.length < 3) {
        throw new ValidationError(
          `Invalid --extra-machine format: '${entry}'. Expected name:ip:user`
        );
      }
      const name = parts[0];
      const user = parts[parts.length - 1];
      const ip = parts.slice(1, -1).join(':');
      if (!ip) {
        throw new ValidationError(
          `Invalid --extra-machine format: '${entry}'. IP address cannot be empty.`
        );
      }
      extraMachines[name] = { ip, user };
    }
  }

  const result = await localExecutorService.execute({
    functionName: options.functionName,
    machineName,
    params: options.params,
    extraMachines,
    debug: options.debug,
  });
  handleExecutionResult(result);
}

/**
 * Run function in S3 mode (local renet execution + S3 state tracking).
 * Creates a queue item in S3 for tracking, executes via renet, then cleans up.
 */
async function runS3Mode(options: BridgeExecuteOptions): Promise<void> {
  const provider = await getStateProvider();
  const machineName = options.machine ?? (await contextService.getMachine());
  if (!machineName) {
    throw new ValidationError(t('errors.machineRequiredLocal'));
  }
  validateFunctionParams(options.functionName, options.params);

  const taskId = (
    await provider.queue.create({
      functionName: options.functionName,
      machineName,
      teamName: 's3',
      vaultContent: '',
      priority: 3,
      params: options.params,
    })
  ).taskId;

  outputService.info(
    t('commands.shortcuts.run.executingLocal', {
      function: options.functionName,
      machine: machineName,
    })
  );
  if (taskId) outputService.info(`Task ID: ${taskId}`);

  const result = await localExecutorService.execute({
    functionName: options.functionName,
    machineName,
    params: options.params,
    debug: options.debug,
  });

  if (taskId) {
    try {
      await provider.queue.delete(taskId);
    } catch {
      /* best-effort cleanup */
    }
  }
  handleExecutionResult(result);
}

/** Convert pre-typed params to key=value strings for createAction compatibility. */
function paramsToStrings(params: Record<string, unknown>): string[] {
  const result: string[] = [];
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null) continue;
    if (Array.isArray(value)) {
      for (const item of value) {
        result.push(`${key}=${item}`);
      }
    } else {
      result.push(`${key}=${value}`);
    }
  }
  return result;
}

async function runCloudMode(options: BridgeExecuteOptions, program: Command): Promise<void> {
  const createOptions: CreateActionOptions = {
    function: options.functionName,
    team: options.team,
    machine: options.machine,
    bridge: options.bridge,
    param: paramsToStrings(options.params),
    priority: options.priority ?? String(DEFAULTS.PRIORITY.QUEUE_PRIORITY),
  };

  const result = await createAction(createOptions);

  if (options.watch && result.taskId) {
    outputService.info(t('commands.shortcuts.run.watching'));
    await traceAction(result.taskId, { watch: true, interval: '2000' }, program);
  }
}

export async function executeBridgeFunction(
  options: BridgeExecuteOptions,
  program: Command
): Promise<void> {
  try {
    const provider = await getStateProvider();

    switch (provider.mode) {
      case 'local':
        await runLocalMode(options);
        break;
      case 's3':
        await runS3Mode(options);
        break;
      case 'cloud':
      default:
        await runCloudMode(options, program);
        break;
    }
  } catch (error) {
    handleError(error);
  }
}
