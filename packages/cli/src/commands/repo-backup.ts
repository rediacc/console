import { type Command, Option } from 'commander';
import { t } from '../i18n/index.js';
import { getSubscriptionTokenState } from '../services/account/subscription-auth.js';
import { resolveControlNode } from '../services/config/config-cluster-ops.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import { type ExecuteResult, getExecutor } from '../services/executor/executor-factory.js';
import { deployRepoKeyIfNeeded } from '../services/repo/repo-key-deployment.js';
import { probeRepoMounted } from '../services/repo/repo-mount-check.js';
import { assertCommandPolicy, CMD } from '../utils/command-policy.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { renderLocalExecutionFailure } from '../utils/local-execution-failures.js';
import { type ResolvedRemote, resolveRemoteName } from '../utils/remote-resolve.js';
import { recordedDatastoreMount } from '../utils/repo-executor.js';
import { resolveRepoRef } from '../utils/repo-target.js';
import { coerceCliParams, validateFunctionParams } from './function-params.js';
import { applyPullDeltaParams, applyPushDeltaParams, finalizePush } from './repo-delta.js';
import { reportPushStats } from './repo-push-stats.js';

interface BackupRunOptions {
  machine?: string;
  /**
   * #74: the datastore mount the repo is RECORDED on, threaded into the transfer
   * itself. renet reads it from the machine vault, so a push whose source repo
   * lives on a named datastore has to declare it or `backup_push` looks for the
   * image under the machine's default and dies on `stat`.
   */
  datastore?: string;
  cluster?: string;
  kubeCluster?: string;
  debug?: boolean;
  watch?: boolean;
  skipRouterRestart?: boolean;
}

type RepoConfig = import('@rediacc/shared/config-schema').RepositoryConfig;

/** Resolve extra machines needed for multi-machine operations (e.g., backup push --to-machine). */
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
): Promise<{ ok: boolean; local?: ExecuteResult }> {
  const machineName = options.machine;

  if (!machineName) {
    throw new ValidationError(t('errors.machineRequiredLocal'));
  }

  const coerced = coerceCliParams(functionName, params as Record<string, string>);
  validateFunctionParams(functionName, coerced);

  outputService.info(
    t('commands.shortcuts.run.executingLocal', { function: functionName, machine: machineName })
  );
  const result = await getExecutor().execute({
    functionName,
    machineName,
    kubeCluster: options.kubeCluster,
    datastore: options.datastore,
    params: coerced,
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

/** Apply optional backup push flags (checkpoint, force) to params. */
function applyPushFlags(
  params: Record<string, unknown>,
  options: { checkpoint?: boolean; force?: boolean }
): void {
  if (options.checkpoint) params.checkpoint = true;
  if (options.force) params.override = true;
}

/** Build params for a backup push (unified for machine and storage targets). */
export function buildPushParams(
  repo: string,
  repositoryGuid: string,
  resolvedType: 'machine' | 'storage',
  targetName: string,
  options: { checkpoint?: boolean; force?: boolean },
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

/**
 * Backup targets ride the data plane (CoW images + rsync/FIEMAP), which is
 * runtime-agnostic, so a cluster target resolves to its control-node machine.
 * The `--up` deploy gating (dual-runtime) lands in wave 5; the transfer itself
 * is unchanged.
 */
async function narrowRemoteToDataPlane(
  resolved: ResolvedRemote
): Promise<{ type: 'machine' | 'storage'; name: string }> {
  if (resolved.type === 'cluster') {
    return { type: 'machine', name: await resolveControlNode(resolved.name) };
  }
  return { type: resolved.type, name: resolved.name };
}

/** Resolve backup target from CLI options. */
async function resolvePushTarget(
  options: Record<string, unknown>
): Promise<{ type: 'machine' | 'storage'; name: string }> {
  if (options.toMachine) {
    return { type: 'machine', name: options.toMachine as string };
  }
  if (options.to) {
    return narrowRemoteToDataPlane(await resolveRemoteName(options.to as string));
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
  const upResult = await getExecutor().execute({
    functionName: 'repository_up',
    machineName: targetName,
    // NO datastore on purpose (#74). The push landed the image wherever the
    // TARGET machine's own vault record points — `resolveExtraMachines` builds
    // `--dest-path` from that record, not from the source's placement — and
    // dispatching here without a declaration resolves to exactly the same place.
    // Passing the source's named mount would name a path that need not exist here.
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
      // #74: the probe enumerates ONE datastore, so without the repo's own mount
      // a named-datastore repo reads as absent and every push is filed as `cold`.
      datastore: options.datastore as string | undefined,
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
 * Push a repo backup addressed by its positional `<ref>`.
 *
 * The ref derives the SOURCE (the machine, or cluster control node, the repo
 * currently lives on); `--to` still names the DESTINATION place or storage.
 * The pushed copy is a backup artifact, so there is no post-push deploy here:
 * `backup restore --up` is the verb that boots one.
 */
async function pushRepo(ref: string, options: Record<string, unknown>): Promise<void> {
  const { name, repoKey, machineName, kubeCluster } = await resolveRepoRef(ref);
  await assertCommandPolicy(CMD.REPO_PUSH, repoKey);
  const repoConfig = await configService.getRepository(repoKey);
  if (!repoConfig) {
    throw new ValidationError(t('errors.repositoryNotFound', { name }));
  }

  const execOptions: Record<string, unknown> = {
    ...options,
    machine: machineName,
    ...(kubeCluster !== undefined && { kubeCluster }),
    // The SOURCE side's datastore: the push reads the image from where this repo
    // actually lives. The destination's is a separate question, answered by the
    // target machine's own vault record (see postPushDeploy).
    datastore: await recordedDatastoreMount(repoKey),
  };

  const { type: resolvedType, name: targetName } = await resolvePushTarget(execOptions);
  const { params, retainBase } = await preparePush(
    repoKey,
    execOptions,
    repoConfig,
    resolvedType,
    targetName
  );

  // Show the human-readable target name; the dest GUID/path is renet detail.
  outputService.info(t('commands.repo.push.pushing', { repo: name, dest: targetName }));
  const { ok, local } = await executeFunction('backup_push', params, execOptions);
  if (ok) {
    reportPushStats(name, targetName, resolvedType, local, !!execOptions.json);
  }
  // retainBase is set only for machine targets; finalizePush also syncs commit
  // metadata to the target when the pushed object is an immutable commit.
  if (ok && resolvedType === 'machine') {
    await finalizePush(
      repoKey,
      repoConfig,
      targetName,
      params,
      retainBase,
      execOptions.debug as boolean
    );
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
    return narrowRemoteToDataPlane(await resolveRemoteName(options.from as string));
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
  const upResult = await getExecutor().execute({
    functionName: 'repository_up',
    machineName: targetMachine,
    // The pull landed on the repo's own home, so this is the same mount the pull
    // itself declared (#74).
    datastore: options.datastore as string | undefined,
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
 * Pull a repo backup addressed by its positional `<ref>`.
 *
 * The ref derives the repo's home machine, which is where the pull lands (and,
 * with `--up`, deploys); `--from` names the source place or storage.
 */
async function pullRepo(ref: string, options: Record<string, unknown>): Promise<void> {
  const { name, repoKey, machineName, kubeCluster } = await resolveRepoRef(ref);
  await assertCommandPolicy(CMD.REPO_PULL, repoKey);
  const params: Record<string, unknown> = { repository: repoKey };

  const execOptions: Record<string, unknown> = {
    ...options,
    machine: machineName,
    ...(kubeCluster !== undefined && { kubeCluster }),
    // A pull lands on the repo's OWN home, so the recorded mount is both where
    // renet writes the image and where a following `--up` must look for it.
    datastore: await recordedDatastoreMount(repoKey),
  };

  const { type: resolvedType, name: sourceName } = await resolvePullSource(execOptions);

  params.sourceType = resolvedType;
  params.from = sourceName;
  if (execOptions.force) params.force = true;
  if (execOptions.bwlimit) params.bwlimit = execOptions.bwlimit;
  // Delta pull is machine-source only (rclone/storage has no FIEMAP base).
  if (resolvedType === 'machine') applyPullDeltaParams(params, execOptions);

  const repoConfig = await configService.getRepository(repoKey);
  if (repoConfig) {
    attachSeedLineage(params, repoConfig);
  }

  await deployRepoKeyIfNeeded(repoKey, machineName);

  outputService.info(t('commands.repo.pull.pulling', { repo: name }));
  await executeFunction('backup_pull', params, execOptions);

  if (execOptions.up) {
    await postPullDeploy(repoKey, machineName, execOptions);
  }
}

/**
 * Register backup-related commands directly on the repo command:
 * - repo push <ref>
 * - repo pull <ref>
 */
export function registerRepoBackupCommands(repoCommand: Command): void {
  // repo push <ref> --to <place|storage>
  repoCommand
    .command('push')
    .summary(t('commands.repo.push.descriptionShort'))
    .description(t('commands.repo.push.description'))
    .argument('<ref>', t('options.repoRef'))
    .option('--to <remote>', t('commands.repo.push.optionTo'))
    .addOption(new Option('--to-machine <machine>').hideHelp())
    .option('--provision <provider>', t('commands.repo.push.optionProvision'))
    .option('--checkpoint', t('commands.repo.push.optionCheckpoint'))
    .option('--force', t('commands.repo.push.optionForce'))
    .option('-w, --watch', t('options.watch'))
    .option('--bwlimit <limit>', t('commands.repo.push.optionBwlimit'))
    .option('--delta-base <guid>', t('commands.repo.push.optionDeltaBase'))
    .addOption(
      new Option('--strategy <strategy>', t('commands.repo.push.optionStrategy')).choices([
        'auto',
        'physical',
        'shared',
      ])
    )
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(async (ref: string, options: Record<string, unknown>) => {
      try {
        await pushRepo(ref, options);
      } catch (error) {
        handleError(error);
      }
    });

  // repo pull <ref> --from <place|storage>
  repoCommand
    .command('pull')
    .summary(t('commands.repo.pull.descriptionShort'))
    .description(t('commands.repo.pull.description'))
    .argument('<ref>', t('options.repoRef'))
    .option('--from <remote>', t('commands.repo.pull.optionFrom'))
    .addOption(new Option('--from-machine <machine>').hideHelp())
    .option('--force', t('commands.repo.pull.optionForce'))
    .option('--up', t('commands.repo.pull.optionUp'))
    .option('-w, --watch', t('options.watch'))
    .option('--bwlimit <limit>', t('commands.repo.pull.optionBwlimit'))
    .option('--delta-base <guid>', t('commands.repo.pull.optionDeltaBase'))
    .addOption(
      new Option('--strategy <strategy>', t('commands.repo.pull.optionStrategy')).choices([
        'auto',
        'physical',
        'shared',
      ])
    )
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(async (ref: string, options: Record<string, unknown>) => {
      try {
        await pullRepo(ref, options);
      } catch (error) {
        handleError(error);
      }
    });
}
