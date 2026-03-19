import { DEFAULTS } from '@rediacc/shared/config';
import { Option, type Command } from 'commander';
import { t } from '../i18n/index.js';
import { getStateProvider } from '../providers/index.js';
import { configService } from '../services/config-resources.js';
import { localExecutorService } from '../services/local-executor.js';
import { outputService } from '../services/output.js';
import { deployRepoKeyIfNeeded } from '../services/repo-key-deployment.js';
import { assertCommandPolicy, CMD } from '../utils/command-policy.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { resolveRemoteName } from '../utils/remote-resolve.js';
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
): Promise<
  Record<string, { ip: string; port?: number; user: string; datastore?: string }> | undefined
> {
  if (params.destinationType === 'machine' && typeof params.to === 'string') {
    const machine = await configService.getLocalMachine(params.to);
    return {
      [params.to]: {
        ip: machine.ip,
        port: machine.port,
        user: machine.user,
        datastore: machine.datastore,
      },
    };
  }
  if (params.sourceType === 'machine' && typeof params.from === 'string') {
    const machine = await configService.getLocalMachine(params.from);
    return {
      [params.from]: {
        ip: machine.ip,
        port: machine.port,
        user: machine.user,
        datastore: machine.datastore,
      },
    };
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

/** Build params for a backup push (unified for machine and storage targets). */
function buildPushParams(
  repo: string,
  repositoryGuid: string,
  resolvedType: 'machine' | 'storage',
  targetName: string,
  options: { checkpoint?: boolean; force?: boolean; tag?: string }
): { params: Record<string, unknown>; dest: string } {
  const dest = repositoryGuid;
  const params: Record<string, unknown> = {
    repository: repo,
    dest,
    destinationType: resolvedType,
    to: targetName,
  };
  applyPushFlags(params, options);
  return { params, dest };
}

/**
 * Auto-provision target machine if it doesn't exist and --provider is given.
 */
async function autoProvisionTarget(
  targetName: string,
  providerName: string,
  sourceMachineName?: string,
  debug?: boolean
): Promise<void> {
  const machines = await configService.listMachines();
  if (machines.some((m) => m.name === targetName)) return;

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
  await createCloudMachine(targetName, providerName, {
    inheritInfra: sourceInfra,
    debug: debug ?? false,
  });
}

/** Resolve backup target from CLI options. */
async function resolvePushTarget(
  options: Record<string, unknown>
): Promise<{ type: 'machine' | 'storage'; name: string }> {
  if (options.toMachine) {
    return { type: 'machine', name: options.toMachine as string };
  }
  if (options.to) {
    return resolveRemoteName(options.to as string);
  }
  throw new ValidationError(t('commands.repo.push.destRequired'));
}

/** Deploy repo on target machine after a backup push. */
async function postPushDeploy(
  repo: string,
  targetName: string,
  options: Record<string, unknown>
): Promise<void> {
  outputService.info(t('commands.repo.push.deploying', { repo, machine: targetName }));
  await deployRepoKeyIfNeeded(repo, targetName);
  const upResult = await localExecutorService.execute({
    functionName: 'repository_up',
    machineName: targetName,
    params: { repository: repo, mount: true },
    debug: options.debug as boolean | undefined,
  });
  if (upResult.success) {
    outputService.success(t('commands.repo.push.deployed', { repo, machine: targetName }));
  } else {
    renderLocalExecutionFailure(upResult, t('commands.repo.push.deployFailed', { repo }));
  }
}

/** Attach CoW seed lineage to params if available. */
function attachSeedLineage(
  params: Record<string, unknown>,
  repoConfig: { parentGuid?: string; grandGuid?: string }
): void {
  const seeds = [repoConfig.parentGuid, repoConfig.grandGuid].filter((g): g is string => !!g);
  const uniqueSeeds = [...new Set(seeds)];
  if (uniqueSeeds.length > 0) {
    params.seed = uniqueSeeds.join(',');
  }
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

  const { type: resolvedType, name: targetName } = await resolvePushTarget(options);

  if (options.provision) {
    await autoProvisionTarget(
      targetName,
      options.provision as string,
      options.machine as string,
      options.debug as boolean
    );
  }

  if (resolvedType === 'machine') {
    await deployRepoKeyIfNeeded(repo, targetName);
  }

  const { params, dest } = buildPushParams(
    repo,
    repoConfig.repositoryGuid,
    resolvedType,
    targetName,
    options as { checkpoint?: boolean; force?: boolean; tag?: string }
  );

  attachSeedLineage(params, repoConfig);

  outputService.info(t('commands.repo.push.pushing', { repo, dest }));
  await executeFunction('backup_push', params, options as BackupRunOptions, repoCommand);

  if (options.up && resolvedType === 'machine') {
    await postPushDeploy(repo, targetName, options);
  }
}

/** Resolve backup source from CLI options. */
async function resolvePullSource(
  options: Record<string, unknown>
): Promise<{ type: 'machine' | 'storage'; name: string }> {
  if (options.fromMachine) {
    return { type: 'machine', name: options.fromMachine as string };
  }
  if (options.from) {
    return resolveRemoteName(options.from as string);
  }
  throw new ValidationError(t('commands.repo.pull.sourceRequired'));
}

/** Deploy repo on target machine after a backup pull. */
async function postPullDeploy(
  repo: string,
  targetMachine: string,
  options: Record<string, unknown>
): Promise<void> {
  outputService.info(t('commands.repo.pull.deploying', { repo, machine: targetMachine }));
  await deployRepoKeyIfNeeded(repo, targetMachine);
  const upResult = await localExecutorService.execute({
    functionName: 'repository_up',
    machineName: targetMachine,
    params: { repository: repo, mount: true },
    debug: options.debug as boolean | undefined,
  });
  if (upResult.success) {
    outputService.success(t('commands.repo.pull.deployed', { repo, machine: targetMachine }));
  } else {
    renderLocalExecutionFailure(upResult, t('commands.repo.pull.deployFailed', { repo }));
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

  const { type: resolvedType, name: sourceName } = await resolvePullSource(options);

  params.sourceType = resolvedType;
  params.from = sourceName;
  if (options.force) params.force = true;

  const repoConfig = await configService.getRepository(repo);
  if (repoConfig) {
    attachSeedLineage(params, repoConfig);
  }

  const targetMachine = options.machine as string | undefined;
  if (targetMachine) {
    await deployRepoKeyIfNeeded(repo, targetMachine);
  }

  outputService.info(t('commands.repo.pull.pulling', { repo }));
  await executeFunction('backup_pull', params, options as BackupRunOptions, repoCommand);

  if (options.up && targetMachine) {
    await postPullDeploy(repo, targetMachine, options);
  }
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
    .option('--to <remote>', t('commands.repo.push.optionTo'))
    .addOption(new Option('--to-machine <machine>').hideHelp())
    .option('--provision <provider>', t('commands.repo.push.optionProvision'))
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
    .option('--from <remote>', t('commands.repo.pull.optionFrom'))
    .addOption(new Option('--from-machine <machine>').hideHelp())
    .option('--force', t('commands.repo.pull.optionForce'))
    .option('--up', t('commands.repo.pull.optionUp'))
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
    .option('--from <remote>', t('commands.repo.backup.list.optionFrom'))
    .addOption(new Option('--from-machine <machine>').hideHelp())
    .requiredOption('-m, --machine <name>', t('options.machine'))
    .option('-w, --watch', t('options.watch'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(async (options) => {
      try {
        const params: Record<string, unknown> = {};

        if (options.fromMachine) {
          params.sourceType = 'machine';
          params.from = options.fromMachine;
        } else if (options.from) {
          const resolved = await resolveRemoteName(options.from as string);
          params.sourceType = resolved.type;
          params.from = resolved.name;
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
