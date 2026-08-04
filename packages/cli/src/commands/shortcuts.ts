import { Command } from 'commander';
import { t } from '../i18n/index.js';
import { outputService } from '../services/core/output.js';
import { getExecutor } from '../services/executor/executor-factory.js';
import { assertCommandPolicy, CMD } from '../utils/command-policy.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { renderLocalExecutionFailure } from '../utils/local-execution-failures.js';
import { recordedDatastoreMount } from '../utils/repo-executor.js';
import { assertMachineExists } from './_validate.js';
import { coerceCliParams, parseParamOptions, validateFunctionParams } from './function-params.js';

interface RunLocalOptions {
  machine?: string;
  param?: string[];
  extraMachine?: string[];
  debug?: boolean;
  skipRouterRestart?: boolean;
}

/** Resolve machine name and parse+validate function params (shared by the run-local helpers). */
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

  const result = await getExecutor().execute({
    functionName,
    machineName,
    params,
    // #74: `run` is the escape hatch, so it cannot know which verb it is calling —
    // but if the caller named a repository, that repo's recorded placement is the
    // same answer every real verb would give. A GUID or an unknown name yields
    // undefined, which is the machine default this always used.
    datastore:
      typeof params.repository === 'string'
        ? await recordedDatastoreMount(params.repository)
        : undefined,
    extraMachines,
    debug: options.debug,
    skipRouterRestart: options.skipRouterRestart,
    // `run` exists to show a Rediaccfile function's output; the default handler
    // drops everything that is not a step event, so without this it printed
    // nothing unless --debug was passed.
    passthroughOutput: true,
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
