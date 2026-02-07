import { Command } from 'commander';
import { DEFAULTS } from '@rediacc/shared/config';
import { type CreateActionOptions, createAction, traceAction, validateFunctionParams } from './queue.js';
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
    functionName: options.functionName,
    machineName,
    params: options.params,
    extraMachines,
    debug: options.debug,
  });
  handleExecutionResult(result);
}

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

async function runCloudMode(options: BridgeExecuteOptions, program: Command): Promise<void> {
  // Convert pre-typed params to key=value strings for createAction compatibility
  const paramStrings: string[] = [];
  for (const [key, value] of Object.entries(options.params)) {
    if (value !== undefined && value !== null) {
      if (Array.isArray(value)) {
        for (const item of value) {
          paramStrings.push(`${key}=${item}`);
        }
      } else {
        paramStrings.push(`${key}=${value}`);
      }
    }
  }

  const createOptions: CreateActionOptions = {
    function: options.functionName,
    team: options.team,
    machine: options.machine,
    bridge: options.bridge,
    param: paramStrings,
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
