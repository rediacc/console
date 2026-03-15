import { DEFAULTS } from '@rediacc/shared/config';
import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { getStateProvider } from '../providers/index.js';
import { configService } from '../services/config-resources.js';
import { localExecutorService } from '../services/local-executor.js';
import { outputService } from '../services/output.js';
import { deployRepoKeyIfNeeded } from '../services/repo-key-deployment.js';
import { assertCommandPolicy, CMD } from '../utils/command-policy.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { renderLocalExecutionFailure } from '../utils/local-execution-failures.js';
import {
  type CreateActionOptions,
  coerceCliParams,
  createAction,
  traceAction,
  validateFunctionParams,
} from './queue.js';
import { runBatchOperation } from './repo-batch-utils.js';

interface BackupRunOptions {
  machine?: string;
  debug?: boolean;
  watch?: boolean;
  skipRouterRestart?: boolean;
}

/** Resolve extra machines needed for multi-machine operations (e.g., backup push --to-machine). */
async function resolveExtraMachines(
  params: Record<string, unknown>
): Promise<Record<string, { ip: string; port?: number; user: string }> | undefined> {
  if (params.destinationType === 'machine' && typeof params.to === 'string') {
    const machine = await configService.getLocalMachine(params.to);
    return { [params.to]: { ip: machine.ip, port: machine.port, user: machine.user } };
  }
  if (params.sourceType === 'machine' && typeof params.from === 'string') {
    const machine = await configService.getLocalMachine(params.from);
    return { [params.from]: { ip: machine.ip, port: machine.port, user: machine.user } };
  }
  return undefined;
}

/** Execute a bridge function in the appropriate mode (local/s3/cloud). */
async function executeFunction(
  functionName: string,
  params: Record<string, unknown>,
  options: BackupRunOptions,
  program?: Command
): Promise<void> {
  const provider = await getStateProvider();
  const machineName = options.machine;

  if (!machineName) {
    throw new ValidationError(t('errors.machineRequiredLocal'));
  }

  const coerced = coerceCliParams(functionName, params as Record<string, string>);
  validateFunctionParams(functionName, coerced);

  if (provider.isCloud) {
    const createOptions: CreateActionOptions = {
      function: functionName,
      machine: machineName,
      priority: String(DEFAULTS.PRIORITY.QUEUE_PRIORITY),
      param: Object.entries(coerced).map(([k, v]) => `${k}=${v}`),
    };
    const result = await createAction(createOptions);
    if (options.watch && result.taskId && program) {
      outputService.info(t('commands.shortcuts.run.watching'));
      await traceAction(result.taskId, { watch: true, interval: '2000' }, program);
    }
  } else {
    outputService.info(
      t('commands.shortcuts.run.executingLocal', { function: functionName, machine: machineName })
    );
    const extraMachines = await resolveExtraMachines(coerced);
    const result = await localExecutorService.execute({
      functionName,
      machineName,
      params: coerced,
      extraMachines,
      debug: options.debug,
      skipRouterRestart: options.skipRouterRestart,
    });
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
}

/** Apply optional backup push flags (checkpoint, force, tag) to params. */
function applyPushFlags(
  params: Record<string, unknown>,
  options: { checkpoint?: boolean; force?: boolean; tag?: string }
): void {
  if (options.checkpoint) params.checkpoint = true;
  if (options.force) params.override = true;
  if (options.tag) params.tag = options.tag;
}

/** Build params for a storage-targeted backup push. */
function buildStoragePushParams(
  repo: string,
  repositoryGuid: string,
  options: { dest?: string; to: string; checkpoint?: boolean; force?: boolean; tag?: string }
): { params: Record<string, unknown>; dest: string } {
  const dest = repositoryGuid;
  if (options.dest && options.dest !== dest) {
    outputService.warn(
      t('commands.repo.push.destIgnoredForStorage', { dest, provided: options.dest })
    );
  }
  const params: Record<string, unknown> = {
    repository: repo,
    dest,
    destinationType: 'storage',
    to: options.to,
  };
  applyPushFlags(params, options);
  return { params, dest };
}

/** Build params for a machine-targeted backup push. */
function buildMachinePushParams(
  repo: string,
  repositoryGuid: string,
  options: { dest?: string; toMachine: string; checkpoint?: boolean; force?: boolean; tag?: string }
): { params: Record<string, unknown>; dest: string } {
  const dest = options.dest ?? repositoryGuid;
  const params: Record<string, unknown> = {
    repository: repo,
    dest,
    destinationType: 'machine',
    to: options.toMachine,
  };
  applyPushFlags(params, options);
  return { params, dest };
}

/**
 * Auto-provision target machine if it doesn't exist and --provider is given.
 */
async function autoProvisionTarget(options: Record<string, unknown>): Promise<void> {
  if (!options.provider) return;
  const machines = await configService.listMachines();
  const exists = machines.some((m) => m.name === options.toMachine);
  if (exists) return;

  // Inherit infra config from source machine
  const sourceMachineName = options.machine as string | undefined;
  let sourceInfra: import('../types/index.js').InfraConfig | undefined;
  if (sourceMachineName) {
    try {
      const sourceMachine = await configService.getLocalMachine(sourceMachineName);
      sourceInfra = sourceMachine.infra;
    } catch {
      /* non-fatal */
    }
  }

  const { createCloudMachine } = await import('../services/tofu/index.js');
  await createCloudMachine(options.toMachine as string, options.provider as string, {
    inheritInfra: sourceInfra,
    debug: options.debug as boolean,
  });
}

/**
 * Push a single repo backup.
 */
async function pushSingleRepo(
  repo: string,
  options: Record<string, unknown>,
  repoCommand: Command
): Promise<void> {
  await assertCommandPolicy(CMD.REPO_PUSH, repo);
  const repoConfig = await configService.getRepository(repo);
  if (!repoConfig) {
    throw new ValidationError(t('errors.repositoryNotFound', { name: repo }));
  }

  let params: Record<string, unknown>;
  let dest: string;

  if (options.to) {
    ({ params, dest } = buildStoragePushParams(
      repo,
      repoConfig.repositoryGuid,
      options as Parameters<typeof buildStoragePushParams>[2]
    ));
  } else if (options.toMachine) {
    await autoProvisionTarget(options);
    await deployRepoKeyIfNeeded(repo, options.toMachine as string);
    ({ params, dest } = buildMachinePushParams(
      repo,
      repoConfig.repositoryGuid,
      options as Parameters<typeof buildMachinePushParams>[2]
    ));
  } else {
    throw new ValidationError(t('commands.repo.push.destRequired'));
  }

  // Auto-resolve CoW seed from lineage (parent first, then grand)
  const seeds = [repoConfig.parentGuid, repoConfig.grandGuid].filter((g): g is string => !!g);
  const uniqueSeeds = [...new Set(seeds)];
  if (uniqueSeeds.length > 0) {
    params.seed = uniqueSeeds.join(',');
  }

  outputService.info(t('commands.repo.push.pushing', { repo, dest }));
  await executeFunction('backup_push', params, options as BackupRunOptions, repoCommand);

  // Post-push: mount + deploy on target machine
  if (options.up && options.toMachine) {
    outputService.info(t('commands.repo.push.deploying', { repo, machine: options.toMachine as string }));
    await deployRepoKeyIfNeeded(repo, options.toMachine as string);
    const upResult = await localExecutorService.execute({
      functionName: 'repository_up',
      machineName: options.toMachine as string,
      params: { repository: repo, mount: true },
      debug: options.debug as boolean | undefined,
    });
    if (upResult.success) {
      outputService.success(t('commands.repo.push.deployed', { repo, machine: options.toMachine as string }));
    } else {
      renderLocalExecutionFailure(upResult, t('commands.repo.push.deployFailed', { repo }));
    }
  }
}

/**
 * Pull a single repo backup.
 */
async function pullSingleRepo(
  repo: string,
  options: Record<string, unknown>,
  repoCommand: Command
): Promise<void> {
  await assertCommandPolicy(CMD.REPO_PULL, repo);
  const params: Record<string, unknown> = { repository: repo };

  if (options.from) {
    params.sourceType = 'storage';
    params.from = options.from;
  } else if (options.fromMachine) {
    params.sourceType = 'machine';
    params.from = options.fromMachine;
  } else {
    throw new ValidationError(t('commands.repo.pull.sourceRequired'));
  }

  if (options.force) params.force = true;

  // Auto-resolve CoW seed from lineage (parent first, then grand)
  const repoConfig = await configService.getRepository(repo);
  if (repoConfig) {
    const seeds = [repoConfig.parentGuid, repoConfig.grandGuid].filter((g): g is string => !!g);
    const uniqueSeeds = [...new Set(seeds)];
    if (uniqueSeeds.length > 0) {
      params.seed = uniqueSeeds.join(',');
    }
  }

  const targetMachine = options.machine as string | undefined;
  if (targetMachine) {
    await deployRepoKeyIfNeeded(repo, targetMachine);
  }

  outputService.info(t('commands.repo.pull.pulling', { repo }));
  await executeFunction('backup_pull', params, options as BackupRunOptions, repoCommand);
}

/**
 * Register backup-related commands directly on the repo command:
 * - repo push [repo]
 * - repo pull [repo]
 * - repo list-backups
 */
export function registerRepoBackupCommands(repoCommand: Command): void {
  // repo push [repo]
  repoCommand
    .command('push [repo]')
    .summary(t('commands.repo.push.descriptionShort'))
    .description(t('commands.repo.push.description'))
    .option('--dest <filename>', t('commands.repo.push.optionDest'))
    .option('--to <storage>', t('commands.repo.push.optionToStorage'))
    .option('--to-machine <machine>', t('commands.repo.push.optionToMachine'))
    .option('--provider <name>', t('commands.repo.push.optionProvider'))
    .option('--checkpoint', t('commands.repo.push.optionCheckpoint'))
    .option('--force', t('commands.repo.push.optionForce'))
    .option('--up', t('commands.repo.push.optionUp'))
    .option('--tag <tag>', t('commands.repo.push.optionTag'))
    .requiredOption('-m, --machine <name>', t('options.machine'))
    .option('-w, --watch', t('options.watch'))
    .option('--parallel', t('commands.repo.upAll.parallelOption'))
    .option('--concurrency <n>', t('commands.repo.upAll.concurrencyOption'), '3')
    .option('-y, --yes', t('commands.repo.yesOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(async (repo, options) => {
      try {
        if (repo) {
          await pushSingleRepo(repo, options, repoCommand);
        } else {
          await runBatchOperation(
            'Push',
            options.machine,
            !!options.yes,
            (name) => pushSingleRepo(name, options, repoCommand),
            options
          );
        }
      } catch (error) {
        handleError(error);
      }
    });

  // repo pull [repo]
  repoCommand
    .command('pull [repo]')
    .summary(t('commands.repo.pull.descriptionShort'))
    .description(t('commands.repo.pull.description'))
    .option('--from <storage>', t('commands.repo.pull.optionFromStorage'))
    .option('--from-machine <machine>', t('commands.repo.pull.optionFromMachine'))
    .option('--force', t('commands.repo.pull.optionForce'))
    .requiredOption('-m, --machine <name>', t('options.machine'))
    .option('-w, --watch', t('options.watch'))
    .option('--parallel', t('commands.repo.upAll.parallelOption'))
    .option('--concurrency <n>', t('commands.repo.upAll.concurrencyOption'), '3')
    .option('-y, --yes', t('commands.repo.yesOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(async (repo, options) => {
      try {
        if (repo) {
          await pullSingleRepo(repo, options, repoCommand);
        } else {
          await runBatchOperation(
            'Pull',
            options.machine,
            !!options.yes,
            (name) => pullSingleRepo(name, options, repoCommand),
            options
          );
        }
      } catch (error) {
        handleError(error);
      }
    });

  // repo backup (subgroup)
  const backup = repoCommand.command('backup').description(t('commands.repo.backup.description'));

  backup
    .command('list')
    .description(t('commands.repo.backup.list.description'))
    .option('--from <storage>', t('commands.repo.backup.list.optionFromStorage'))
    .option('--from-machine <machine>', t('commands.repo.backup.list.optionFromMachine'))
    .requiredOption('-m, --machine <name>', t('options.machine'))
    .option('-w, --watch', t('options.watch'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(async (options) => {
      try {
        const params: Record<string, unknown> = {};

        if (options.from) {
          params.sourceType = 'storage';
          params.from = options.from;
        } else if (options.fromMachine) {
          params.sourceType = 'machine';
          params.from = options.fromMachine;
        } else {
          throw new ValidationError(t('commands.repo.backup.list.sourceRequired'));
        }

        outputService.info(t('commands.repo.backup.list.listing'));
        await executeFunction(`backup_list`, params, options, repoCommand);
      } catch (error) {
        handleError(error);
      }
    });

  // repo backup schedule <machine>
  backup
    .command('schedule <machine>')
    .description(t('commands.backup.schedule.description'))
    .option('--debug', t('options.debug'))
    .action(async (machine: string, options: { debug?: boolean }) => {
      try {
        const { pushBackupSchedule } = await import('../services/backup-schedule.js');
        await pushBackupSchedule(machine, options);
      } catch (error) {
        handleError(error);
      }
    });
}
