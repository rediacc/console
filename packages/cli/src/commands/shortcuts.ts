import { Command } from 'commander';
import { t } from '../i18n/index.js';
import { localExecutorService } from '../services/local-executor.js';
import { outputService } from '../services/output.js';
import { assertCommandPolicy, CMD } from '../utils/command-policy.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { renderLocalExecutionFailure } from '../utils/local-execution-failures.js';
import { coerceCliParams, parseParamOptions, validateFunctionParams } from './function-params.js';
import { assertMachineExists } from './_validate.js';

interface RunLocalOptions {
  machine?: string;
  param?: string[];
  extraMachine?: string[];
  debug?: boolean;
  skipRouterRestart?: boolean;
}

/** Resolve machine name and parse+validate function params (shared by local and S3 modes). */
function resolveRunParams(
  functionName: string,
  options: RunLocalOptions
): { machineName: string; params: Record<string, unknown> } {
  const machineName = options.machine;
  if (!machineName) {
    throw new ValidationError(t('errors.machineRequiredLocal'));
  }
  const rawParams = parseParamOptions(options.param);
  const params = coerceCliParams(functionName, rawParams);
  validateFunctionParams(functionName, params);
  return { machineName, params };
}

export function handleExecutionResult(result: {
  success: boolean;
  durationMs?: number;
  error?: string;
  errorCode?: string;
  errorGuidance?: string;
  exitCode?: number;
}): void {
  if (result.success) {
    outputService.success(
      t('commands.shortcuts.run.completedLocal', { duration: result.durationMs })
    );
  } else {
    renderLocalExecutionFailure(
      result,
      t('commands.shortcuts.run.failedLocal', { error: result.error })
    );
  }
}

async function runLocalMode(functionName: string, options: RunLocalOptions): Promise<void> {
  const { machineName, params } = resolveRunParams(functionName, options);
  await assertMachineExists(machineName);
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
    skipRouterRestart: options.skipRouterRestart,
  });
  handleExecutionResult(result);
}

export function registerShortcuts(program: Command): void {
  // run - executes directly via renet subprocess
  program
    .command('run', { hidden: true })
    .summary(t('commands.shortcuts.run.descriptionShort'))
    .description(t('commands.shortcuts.run.description'))
    .requiredOption('-f, --function <name>', t('options.function'))
    .requiredOption('-m, --machine <name>', t('options.machine'))
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
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(async (options) => {
      try {
        await assertCommandPolicy(CMD.RUN);

        const functionName = options.function;
        await runLocalMode(functionName, options);
      } catch (error) {
        handleError(error);
      }
    });
}
