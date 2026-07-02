import { Option, type Command } from 'commander';
import { t } from '../i18n/index.js';
import { configService } from '../services/config-resources.js';
import { localExecutorService, type LocalExecuteResult } from '../services/local-executor.js';
import { outputService } from '../services/output.js';
import { deployRepoKeyIfNeeded } from '../services/repo-key-deployment.js';
import { probeRepoMounted } from '../services/repo-mount-check.js';
import { getSubscriptionTokenState } from '../services/subscription-auth.js';
import { assertCommandPolicy, CMD } from '../utils/command-policy.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { resolveRemoteName } from '../utils/remote-resolve.js';
import { renderLocalExecutionFailure } from '../utils/local-execution-failures.js';
import { coerceCliParams, validateFunctionParams } from './function-params.js';
import {
  type BackupListEntry,
  fetchBackupList,
  renderBackupList,
  type TaggedBackupEntry,
} from './repo-backup-list.js';
import { runBatchOperation } from './repo-batch-utils.js';
import { applyPullDeltaParams, applyPushDeltaParams, finalizePush } from './repo-delta.js';
import { reportPushStats } from './repo-push-stats.js';

interface BackupRunOptions {
  machine?: string;
  debug?: boolean;
  watch?: boolean;
  skipRouterRestart?: boolean;
}

type RepoConfig = import('../schema/schemas.js').RepositoryConfig;

/** Resolve extra machines needed for multi-machine operations (e.g., backup push --to-machine). */
export async function resolveExtraMachines(
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

/**
 * Execute a bridge function in the appropriate mode (local/s3/cloud).
 * Returns whether the execution succeeded so callers can gate follow-up state
 * writes (e.g. recording an auto-delta base only after a successful push),
 * plus the local execution result so callers can parse machine-readable
 * stdout lines (e.g. backup push transfer stats).
 */
async function executeFunction(
  functionName: string,
  params: Record<string, unknown>,
  options: BackupRunOptions
): Promise<{ ok: boolean; local?: LocalExecuteResult }> {
  const machineName = options.machine;

  if (!machineName) {
    throw new ValidationError(t('errors.machineRequiredLocal'));
  }

  const coerced = coerceCliParams(functionName, params as Record<string, string>);
  validateFunctionParams(functionName, coerced);

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
    return { ok: true, local: result };
  }
  renderLocalExecutionFailure(
    result,
    t('commands.shortcuts.run.failedLocal', { error: result.error })
  );
  return { ok: false, local: result };
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
export function buildPushParams(
  repo: string,
  repositoryGuid: string,
  resolvedType: 'machine' | 'storage',
  targetName: string,
  options: { checkpoint?: boolean; force?: boolean; tag?: string },
  storageMode?: 'hot' | 'cold'
): { params: Record<string, unknown>; dest: string } {
  // Storage backups live under the scheduler's hot/cold layout: hot/ for
  // repos that were mounted at push time, cold/ for unmounted ones. The
  // machine target keeps the bare GUID (rsync into the datastore).
  const dest =
    resolvedType === 'storage' && storageMode ? `${storageMode}/${repositoryGuid}` : repositoryGuid;
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
export async function autoProvisionTarget(
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
export async function postPushDeploy(
  repo: string,
  targetName: string,
  options: Record<string, unknown>
): Promise<void> {
  const tokenState = getSubscriptionTokenState();
  if (tokenState.kind !== 'ready') {
    outputService.error(t('errors.license.preflightTokenNotReady', { machine: targetName }));
    process.exitCode = 1;
    return;
  }
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
export function attachSeedLineage(
  params: Record<string, unknown>,
  repoConfig: { parentGuid?: string; grandGuid?: string }
): void {
  const seeds = [repoConfig.parentGuid, repoConfig.grandGuid].filter((g): g is string => !!g);
  const uniqueSeeds = [...new Set(seeds)];
  if (uniqueSeeds.length > 0) {
    params.seed = uniqueSeeds.join(',');
  }
}

/** Build push params (provision, key deploy, seed lineage, bwlimit, delta wiring). */
async function preparePush(
  repo: string,
  options: Record<string, unknown>,
  repoConfig: RepoConfig,
  resolvedType: 'machine' | 'storage',
  targetName: string
): Promise<{ params: Record<string, unknown>; dest: string; retainBase?: string }> {
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

  // Storage layout is mode-scoped (hot = mounted at push time, cold =
  // unmounted). Probe failure defaults to hot — pushes overwhelmingly
  // target live repos.
  let storageMode: 'hot' | 'cold' | undefined;
  if (resolvedType === 'storage') {
    const mounted = await probeRepoMounted(repoConfig.repositoryGuid, options.machine as string, {
      debug: options.debug as boolean | undefined,
    });
    storageMode = mounted === false ? 'cold' : 'hot';
  }

  const { params, dest } = buildPushParams(
    repo,
    repoConfig.repositoryGuid,
    resolvedType,
    targetName,
    options,
    storageMode
  );
  attachSeedLineage(params, repoConfig);
  if (options.bwlimit) params.bwlimit = options.bwlimit;

  // Deterministic CoW-delta push (machine target only; rclone/storage has no
  // FIEMAP base). Resolves a base (explicit or hands-free) and retains a fresh
  // immutable base on both ends; returns the GUID to record on success.
  const retainBase =
    resolvedType === 'machine'
      ? await applyPushDeltaParams(params, options, repoConfig, targetName)
      : undefined;
  return { params, dest, retainBase };
}

/**
 * Push a single repo backup.
 */
async function pushSingleRepo(repo: string, options: Record<string, unknown>): Promise<void> {
  await assertCommandPolicy(CMD.REPO_PUSH, repo);
  const repoConfig = await configService.getRepository(repo);
  if (!repoConfig) {
    throw new ValidationError(t('errors.repositoryNotFound', { name: repo }));
  }

  const { type: resolvedType, name: targetName } = await resolvePushTarget(options);
  const { params, retainBase } = await preparePush(
    repo,
    options,
    repoConfig,
    resolvedType,
    targetName
  );

  // Show the human-readable target name; the dest GUID/path is renet detail.
  outputService.info(t('commands.repo.push.pushing', { repo, dest: targetName }));
  const { ok, local } = await executeFunction('backup_push', params, options);
  if (ok) {
    reportPushStats(repo, targetName, resolvedType, local, !!options.json);
  }
  // retainBase is set only for machine targets; finalizePush also syncs commit
  // metadata to the target when the pushed object is an immutable commit.
  if (ok && resolvedType === 'machine') {
    await finalizePush(repo, repoConfig, targetName, params, retainBase, options.debug as boolean);
  }

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
  const tokenState = getSubscriptionTokenState();
  if (tokenState.kind !== 'ready') {
    outputService.error(t('errors.license.preflightTokenNotReady', { machine: targetMachine }));
    process.exitCode = 1;
    return;
  }
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
async function pullSingleRepo(repo: string, options: Record<string, unknown>): Promise<void> {
  await assertCommandPolicy(CMD.REPO_PULL, repo);
  const params: Record<string, unknown> = { repository: repo };

  const { type: resolvedType, name: sourceName } = await resolvePullSource(options);

  params.sourceType = resolvedType;
  params.from = sourceName;
  if (options.force) params.force = true;
  if (options.bwlimit) params.bwlimit = options.bwlimit;
  // Delta pull is machine-source only (rclone/storage has no FIEMAP base).
  if (resolvedType === 'machine') applyPullDeltaParams(params, options);

  const repoConfig = await configService.getRepository(repo);
  if (repoConfig) {
    attachSeedLineage(params, repoConfig);
  }

  const targetMachine = options.machine as string | undefined;
  if (targetMachine) {
    await deployRepoKeyIfNeeded(repo, targetMachine);
  }

  outputService.info(t('commands.repo.pull.pulling', { repo }));
  await executeFunction('backup_pull', params, options);

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
  // repo push [--name <name>]
  repoCommand
    .command('push')
    .summary(t('commands.repo.push.descriptionShort'))
    .description(t('commands.repo.push.description'))
    .option('--name <name>', t('options.name'))
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
    .option('--bwlimit <limit>', t('commands.repo.push.optionBwlimit'))
    .option('--delta-base <guid>', t('commands.repo.push.optionDeltaBase'))
    .option('--strategy <strategy>', t('commands.repo.push.optionStrategy'))
    .option('--json', t('commands.repo.push.optionJson'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(async (options) => {
      try {
        const repo = options.name;
        if (repo) {
          await pushSingleRepo(repo, options);
        } else {
          await runBatchOperation(
            'Push',
            options.machine,
            !!options.yes,
            (name) => pushSingleRepo(name, options),
            options
          );
        }
      } catch (error) {
        handleError(error);
      }
    });

  // repo pull [--name <name>]
  repoCommand
    .command('pull')
    .summary(t('commands.repo.pull.descriptionShort'))
    .description(t('commands.repo.pull.description'))
    .option('--name <name>', t('options.name'))
    .option('--from <remote>', t('commands.repo.pull.optionFrom'))
    .addOption(new Option('--from-machine <machine>').hideHelp())
    .option('--force', t('commands.repo.pull.optionForce'))
    .option('--up', t('commands.repo.pull.optionUp'))
    .requiredOption('-m, --machine <name>', t('options.machine'))
    .option('-w, --watch', t('options.watch'))
    .option('--parallel', t('commands.repo.upAll.parallelOption'))
    .option('--concurrency <n>', t('commands.repo.upAll.concurrencyOption'), '3')
    .option('-y, --yes', t('commands.repo.yesOption'))
    .option('--bwlimit <limit>', t('commands.repo.pull.optionBwlimit'))
    .option('--delta-base <guid>', t('commands.repo.pull.optionDeltaBase'))
    .option('--strategy <strategy>', t('commands.repo.pull.optionStrategy'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(async (options) => {
      try {
        const repo = options.name;
        if (repo) {
          await pullSingleRepo(repo, options);
        } else {
          await runBatchOperation(
            'Pull',
            options.machine,
            !!options.yes,
            (name) => pullSingleRepo(name, options),
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
    .summary(t('commands.repo.backup.list.descriptionShort'))
    .description(t('commands.repo.backup.list.description'))
    .option('--from <remote>', t('commands.repo.backup.list.optionFrom'))
    .addOption(new Option('--from-machine <machine>').hideHelp())
    .requiredOption('-m, --machine <name>', t('options.machine'))
    .option('--path <subdir>', t('commands.repo.backup.list.optionPath'))
    .option('-w, --watch', t('options.watch'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(async (options) => {
      try {
        const baseParams: Record<string, unknown> = {};

        if (options.fromMachine) {
          baseParams.sourceType = 'machine';
          baseParams.from = options.fromMachine;
        } else if (options.from) {
          const resolved = await resolveRemoteName(options.from as string);
          baseParams.sourceType = resolved.type;
          baseParams.from = resolved.name;
        } else {
          throw new ValidationError(t('commands.repo.backup.list.sourceRequired'));
        }

        outputService.info(t('commands.repo.backup.list.listing'));

        const explicitPath =
          typeof options.path === 'string' && options.path.trim().length > 0
            ? options.path.trim()
            : undefined;

        const tagged: TaggedBackupEntry[] = explicitPath
          ? (await fetchBackupList({ ...baseParams, path: explicitPath }, options)).map((e) => ({
              ...e,
              mode: explicitPath,
            }))
          : (
              await Promise.all(
                ['hot', 'cold'].map(async (mode) => {
                  const entries = await fetchBackupList(
                    { ...baseParams, path: mode },
                    options
                  ).catch(() => [] as BackupListEntry[]);
                  return entries.map((e) => ({ ...e, mode }));
                })
              )
            ).flat();

        await renderBackupList(tagged);
      } catch (error) {
        handleError(error);
      }
    });

  // repo backup schedule -m <machine>
  backup
    .command('schedule')
    .description(t('commands.backup.schedule.description'))
    .requiredOption('-m, --machine <name>', t('options.machine'))
    .option('--dry-run', t('commands.machine.backup.schedule.optionDryRun'))
    .option('--force', t('commands.machine.backup.schedule.optionForce'))
    .option('--reset-failed', t('commands.machine.backup.schedule.optionResetFailed'))
    .option('--debug', t('options.debug'))
    .action(
      async (options: {
        machine: string;
        debug?: boolean;
        dryRun?: boolean;
        force?: boolean;
        resetFailed?: boolean;
      }) => {
        try {
          const machine = options.machine;
          const { pushBackupSchedule } = await import('../services/backup-schedule.js');
          await pushBackupSchedule(machine, {
            debug: options.debug,
            dryRun: options.dryRun,
            force: options.force,
            resetFailed: options.resetFailed,
          });
        } catch (error) {
          handleError(error);
        }
      }
    );
}
