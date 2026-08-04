/**
 * Repository live migration command.
 *
 * Two-phase rsync with minimal downtime:
 *   Phase 1: Hot pre-copy (source stays running, bulk transfer)
 *   Phase 2: Cutover (stop source, delta rsync, unmount)
 *   Phase 3: Start on target + DNS switch
 *
 * Optional --checkpoint for CRIU live migration (process memory capture + restore).
 * Optional --provision to auto-create the target machine via cloud provider.
 */

import { randomUUID } from 'node:crypto';
import { DEFAULTS } from '@rediacc/shared/config';
import type { RepoFamily } from '@rediacc/shared/config-schema';
import { type Command, Option } from 'commander';
import { t } from '../i18n/index.js';
import { resolveExecutionTarget } from '../services/cluster/cluster-target.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import { getExecutor } from '../services/executor/executor-factory.js';
import { deployRepoKeyIfNeeded } from '../services/repo/repo-key-deployment.js';
import { assertCommandPolicy, CMD } from '../utils/command-policy.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { formatBytes } from '../utils/format.js';
import { resolveRemoteName } from '../utils/remote-resolve.js';
import { recordedDatastoreMount } from '../utils/repo-executor.js';
import { resolveRepoRef } from '../utils/repo-target.js';
import { withSpinner } from '../utils/spinner.js';
import { formatStepDuration } from '../utils/timeline.js';
import { autoProvisionTarget, buildPushParams } from './repo-backup.js';
import { postRepoUpTasks } from './repo-batch-utils.js';
import { parseRepositoryListOutput } from './repo-list-parser.js';
import { extractPushResult, type PushResultStats } from './repo-push-stats.js';

export function registerRepoMigrateCommand(repoCommand: Command): void {
  repoCommand
    .command('migrate')
    .summary(t('commands.repo.migrate.descriptionShort'))
    .description(t('commands.repo.migrate.description'))
    .argument('<ref>', t('options.repoRef'))
    .requiredOption('--to <place>', t('commands.repo.migrate.optionTo'))
    .option('--provision <provider>', t('commands.repo.migrate.optionProvision'))
    .option('--bwlimit <limit>', t('commands.repo.migrate.optionBwlimit'))
    .option('--checkpoint', t('commands.repo.migrate.optionCheckpoint'))
    .option('--delta-base <guid>', t('commands.repo.migrate.optionDeltaBase'))
    .addOption(
      new Option('--strategy <strategy>', t('commands.repo.migrate.optionStrategy')).choices([
        'auto',
        'physical',
        'shared',
      ])
    )
    .option('--skip-dns', t('commands.repo.migrate.optionSkipDns'))
    .option('--keep-source', t('commands.repo.migrate.optionKeepSource'))
    // --health-window / --health-timeout (spec §5.4) are intentionally NOT
    // registered: the current migrate is a two-phase rsync with no post-cutover
    // health-gate path, so advertising them would render dead console fields and
    // promise behavior that does not run. They return with the gate (as-built §12).
    .option('--debug', t('options.debug'))
    .action(async (ref: string, options: MigrateOptions) => {
      try {
        await migrateRepo(ref, options);
      } catch (error) {
        handleError(error);
      }
    });
}

interface MigrateOptions {
  to: string;
  provision?: string;
  bwlimit?: string;
  checkpoint?: boolean;
  deltaBase?: string;
  strategy?: string;
  skipDns?: boolean;
  keepSource?: boolean;
  debug?: boolean;
}

/**
 * The SOURCE datastore every leg of a migration runs against (#74).
 *
 * renet resolves a repo's datastore from the MACHINE VAULT, never from the params
 * bag, so an execution that declares nothing is dispatched against the machine's
 * default docker datastore. Migrate declared nothing on any of its source-side
 * legs, so a repo living in a NAMED datastore failed at the first one with
 * `stat /mnt/rediacc/repositories/<guid>: no such file or directory` — renet
 * looking for the image where the repo has never been.
 *
 * It is captured ONCE, before finalizeCutover rewrites placement to `{machine: to}`,
 * because after that rewrite the derivation answers for the TARGET and the last
 * source-side leg (deleteSourceImage) would go looking on the wrong machine's
 * default. The target side is deliberately left undefined: `buildExtraMachines`
 * gives a peer with no recorded datastore the default mount, so the pushed image
 * lands in the target's DEFAULT datastore, which is exactly what the rewritten
 * `{machine: to}` placement then describes.
 */
type SourceDatastore = string | undefined;

/** Execute backup_push with extraMachines resolution (needed for cross-machine rsync).
 * Returns the parsed transfer stats from renet's push_result stdout line, when present. */
async function executePush(
  repoName: string,
  machineName: string,
  params: Record<string, unknown>,
  datastore: SourceDatastore,
  debug?: boolean
): Promise<PushResultStats | undefined> {
  await configService.ensureRepositoryNetworkId(repoName);
  const result = await getExecutor().execute({
    functionName: 'backup_push',
    machineName,
    datastore,
    params: { repository: repoName, ...params },
    debug,
    quietSpinners: true,
  });
  if (!result.success) {
    throw new Error(`backup_push failed: ${result.error ?? DEFAULTS.CLOUD.UNKNOWN_ERROR}`);
  }
  return extractPushResult(result.stdout);
}

/** Execute a repo bridge function quietly (spinner managed by caller). */
async function executeQuiet(
  functionName: string,
  repoName: string,
  machineName: string,
  params: Record<string, unknown>,
  datastore: SourceDatastore,
  debug?: boolean
): Promise<void> {
  await configService.ensureRepositoryNetworkId(repoName);
  const result = await getExecutor().execute({
    functionName,
    machineName,
    datastore,
    params: { repository: repoName, ...params },
    debug,
    quietSpinners: true,
  });
  if (!result.success) {
    throw new Error(`${functionName} failed: ${result.error ?? DEFAULTS.CLOUD.UNKNOWN_ERROR}`);
  }
}

/** Check that the repo is not already mounted on the target machine. */
async function assertNotMountedOnTarget(
  repoName: string,
  repoGuid: string,
  targetMachine: string
): Promise<void> {
  const targetCheck = await getExecutor().execute({
    functionName: 'repository_list',
    machineName: targetMachine,
    params: {},
    captureOutput: true,
  });
  if (!targetCheck.success || !targetCheck.stdout) return;
  try {
    // renet's `list repositories --json` keys repos by GUID under `name` and has no `guid` field.
    // parseRepositoryListOutput tolerates log-prefixed / non-array stdout.
    const repos = parseRepositoryListOutput(targetCheck.stdout) as {
      name: string;
      mounted: boolean;
    }[];
    const mounted = repos.find((r) => r.name === repoGuid && r.mounted);
    if (mounted) {
      throw new ValidationError(
        t('errors.repositoryAlreadyMounted', { name: repoName, machine: targetMachine })
      );
    }
  } catch (e) {
    if (e instanceof ValidationError) throw e;
  }
}

/** Execute Phase 1: hot pre-copy (bulk transfer while source stays running). */
async function executePhase1(
  name: string,
  repoConfig: Awaited<ReturnType<typeof configService.getRepository>> & object,
  from: string,
  to: string,
  bwlimit: string | undefined,
  strategy: string | undefined,
  retainBase: string,
  datastore: SourceDatastore,
  debug: boolean | undefined
): Promise<void> {
  outputService.info(`\n${t('commands.repo.migrate.phase1')}`);

  const pushParams = buildPushParams(name, repoConfig.repositoryGuid, 'machine', to, {
    force: true,
  });
  const seeds = [repoConfig.repositoryGuid, repoConfig.parentGuid, repoConfig.grandGuid].filter(
    (g): g is string => !!g
  );
  const uniqueSeeds = [...new Set(seeds)];
  if (uniqueSeeds.length > 0) pushParams.params.seed = uniqueSeeds.join(',');
  if (bwlimit) pushParams.params.bwlimit = bwlimit;
  if (strategy) pushParams.params.strategy = strategy;
  // Retain the hot pre-copy as an immutable base so the Phase-2 cutover ships
  // only the bytes that changed during Phase 1 (FIEMAP delta, not a full scan).
  pushParams.params.retainBase = retainBase;

  await deployRepoKeyIfNeeded(name, to);
  const stats = await withSpinner(
    t('commands.repo.migrate.phase1'),
    () => executePush(name, from, pushParams.params, datastore, debug),
    t('commands.repo.migrate.phase1Done')
  );
  renderPhaseStats('commands.repo.migrate.phase1Stats', stats);
}

/** Print real transfer numbers for a migration phase, when renet reported them. */
function renderPhaseStats(key: string, stats: PushResultStats | undefined): void {
  if (!stats || stats.transferredBytes < 0) return;
  outputService.info(
    `  ${t(key, {
      transferred: formatBytes(stats.transferredBytes),
      duration: formatStepDuration(stats.transferMs),
    })}`
  );
}

/** Execute Phase 2: cutover (stop source, delta sync, unmount). */
async function executePhase2(
  name: string,
  repoConfig: Awaited<ReturnType<typeof configService.getRepository>> & object,
  from: string,
  to: string,
  bwlimit: string | undefined,
  checkpoint: boolean | undefined,
  delta: { base: string; prune: string; strategy?: string },
  datastore: SourceDatastore,
  debug: boolean | undefined
): Promise<number> {
  outputService.info(`\n${t('commands.repo.migrate.phase2')}`);
  const cutoverStart = Date.now();

  // Cutover ships only the changes since the delta base, then prunes the
  // temporary Phase-1 base from both machines (migration is a move, not an
  // ongoing link). An explicit --delta-base is never pruned.
  const applyDelta = (params: Record<string, unknown>): void => {
    if (bwlimit) params.bwlimit = bwlimit;
    params.deltaBase = delta.base;
    params.retainBasePrune = delta.prune;
    if (delta.strategy) params.strategy = delta.strategy;
  };

  let cutoverStats: PushResultStats | undefined;
  if (checkpoint) {
    cutoverStats = await withSpinner(
      t('commands.repo.migrate.checkpointing'),
      async () => {
        const deltaParams = buildPushParams(name, repoConfig.repositoryGuid, 'machine', to, {
          force: true,
          checkpoint: true,
        });
        applyDelta(deltaParams.params);
        return executePush(name, from, deltaParams.params, datastore, debug);
      },
      t('commands.repo.migrate.deltaDone')
    );
  } else {
    await withSpinner(
      t('commands.repo.migrate.stoppingSource'),
      () => executeQuiet('repository_down', name, from, {}, datastore, debug),
      t('commands.repo.migrate.sourceStopped')
    );

    cutoverStats = await withSpinner(
      t('commands.repo.migrate.deltaSync'),
      async () => {
        const deltaParams = buildPushParams(name, repoConfig.repositoryGuid, 'machine', to, {
          force: true,
        });
        applyDelta(deltaParams.params);
        return executePush(name, from, deltaParams.params, datastore, debug);
      },
      t('commands.repo.migrate.deltaDone')
    );
  }
  renderPhaseStats('commands.repo.migrate.phase2Stats', cutoverStats);

  await withSpinner(
    t('commands.repo.migrate.unmountingSource'),
    () => executeQuiet('repository_down', name, from, { unmount: true }, datastore, debug),
    t('commands.repo.migrate.sourceUnmounted')
  );

  return Date.now() - cutoverStart;
}

/** Execute Phase 3: start on target + DNS switch. */
async function executePhase3(
  name: string,
  to: string,
  skipDns: boolean | undefined,
  debug: boolean | undefined
): Promise<void> {
  outputService.info(`\n${t('commands.repo.migrate.phase3')}`);

  await withSpinner(
    t('commands.repo.migrate.startingTarget'),
    async () => {
      await deployRepoKeyIfNeeded(name, to);
      // Target side: the push landed the image in the TARGET's default datastore
      // (buildExtraMachines gives a peer with no recorded datastore the default
      // mount), and placement has already been rewritten to `{machine: to}` to
      // match. So this leg declares no datastore ON PURPOSE — the source's named
      // mount does not exist here.
      await executeQuiet('repository_up', name, to, {}, undefined, debug);
    },
    t('commands.repo.migrate.targetStarted')
  );

  if (!skipDns) {
    await withSpinner(
      t('commands.repo.migrate.switchingDns'),
      () => postRepoUpTasks(name, to),
      t('commands.repo.migrate.switchingDns')
    );
  }
}

/**
 * Resolve the migrate destination (`--to`) to a machine name. A cluster name
 * resolves to its control-node machine (design D14: the whole repo-verb funnel
 * maps a cluster to its control node), so migrate works machine<->machine,
 * machine<->cluster, and cluster<->cluster (the source side is derived from the
 * ref's placement in migrateRepo). The data plane (CoW images + rsync/FIEMAP) is
 * runtime-agnostic, so no per-endpoint special-casing beyond this name
 * resolution is needed before buildPushParams.
 */
async function resolveMigrateEndpoint(name: string): Promise<string> {
  const resolved = await resolveRemoteName(name);
  if (resolved.type === 'cluster') {
    const { machineName } = await resolveExecutionTarget({ cluster: name });
    return machineName;
  }
  return name;
}

/**
 * R3 source disposition: delete the migrated image on the source machine after
 * a fully successful phase 3. Fails SAFE — the move already succeeded, so a
 * failed cleanup NEVER fails the migrate: it warns, leaves the image in place,
 * and names `machine prune` as the sweep. renet deletes an unmounted repo by
 * `name:tag` on the source (the `.interim` state mirror still resolves it after
 * phase 2's unmount).
 */
async function deleteSourceImage(
  repoKey: string,
  from: string,
  datastore: SourceDatastore,
  debug: boolean | undefined
): Promise<void> {
  outputService.info(`  ${t('commands.repo.migrate.deletingSource', { machine: from })}`);
  let ok = false;
  let error: string = DEFAULTS.CLOUD.UNKNOWN_ERROR;
  try {
    const result = await getExecutor().execute({
      functionName: 'repository_delete',
      machineName: from,
      datastore,
      params: { repository: repoKey },
      debug,
      quietSpinners: true,
    });
    ok = result.success;
    if (!ok) error = result.error ?? DEFAULTS.CLOUD.UNKNOWN_ERROR;
  } catch (err) {
    error = err instanceof Error ? err.message : String(err);
  }
  if (ok) {
    outputService.info(
      `  ${t('commands.repo.migrate.sourceDeleted', { name: repoKey, machine: from })}`
    );
  } else {
    outputService.warn(
      t('commands.repo.migrate.sourceDeleteFailed', { name: repoKey, machine: from, error })
    );
  }
}

/**
 * R2 (fallback scope): migrate moves a whole FAMILY to one home (spec/04
 * §1.2.1 — placement is single-valued per family). Two refusals keep that
 * invariant honest until the family-loop follow-up (grand-first + fork seeds,
 * gated on Open question #1: reflink preservation across backup_push with seeds,
 * a VM check the fleet cannot give this week):
 *   1. a ref naming a non-grand tag is a fork ref — exit 2, teaching push/promote;
 *   2. a family that has forks refuses wholesale — moving only the grand would
 *      split the family across machines, the exact two-places bug being retired.
 * Exit 2 via ValidationError, the same precedent `repo promote` uses.
 */
function assertFamilyMigratable(name: string, tag: string, family: RepoFamily | undefined): void {
  if (!family) return;
  if (tag !== family.grand) {
    throw new ValidationError(t('commands.repo.migrate.forkRefError', { name, tag }));
  }
  const forks = Object.keys(family.tags)
    .filter((tg) => tg !== family.grand)
    .sort();
  if (forks.length > 0) {
    throw new ValidationError(
      t('commands.repo.migrate.familyHasForks', { name, forks: forks.join(', ') })
    );
  }
}

/**
 * The cutover tail, split out of migrateRepo to stay under the complexity
 * budget: rewrite routing to the target (R1), run phase 3, then dispose of the
 * source (R3).
 *
 * R1: the cutover IS the authority transfer. After phase 2's final delta sync
 * and source unmount, the target holds the single authoritative copy, so routing
 * must point there NOW, before phase 3. Rewriting here (not after phase 3) is
 * what makes a post-cutover failure safe: the data's home is the target, so the
 * operator's natural recovery (`rdc repo up <name>`) lands on the target, not on
 * the stale source copy — the exact wrong-host redeploy this closes. A
 * pre-cutover failure never reaches this function, so placement still names the
 * source (spec/03 §5.4 exit-14 row). placementUpdated is emitted before phase 3
 * so it stays on screen even if phase 3 then fails: both failure windows are
 * stated in output.
 */
async function finalizeCutover(
  name: string,
  repoKey: string,
  from: string,
  to: string,
  skipDns: boolean | undefined,
  keepSource: boolean | undefined,
  sourceDatastore: SourceDatastore,
  debug: boolean | undefined
): Promise<void> {
  await configService.setRepositoryPlacement(name, { machine: to });
  outputService.info(`  ${t('commands.repo.migrate.placementUpdated', { name, machine: to })}`);

  try {
    await executePhase3(repoKey, to, skipDns, debug);
  } catch (err) {
    // Post-cutover failure: routing already points at the destination, so
    // recovery lands there. State it, keep the source images as recovery
    // material (R3 deletion below is skipped by the throw), and rethrow.
    outputService.warn(t('commands.repo.migrate.placementRetryHint', { name, machine: to }));
    throw err;
  }

  // R3: migrate is a MOVE. Only after phase 3 fully succeeds is the source image
  // a nameless orphan (the target is a superset — final delta synced at cutover,
  // source down since), so delete it here, strictly LAST. --keep-source opts out
  // and warns the leftover is a stray reconcile will flag.
  if (from === to) return;
  if (keepSource) {
    outputService.warn(t('commands.repo.migrate.sourceRetained', { name, machine: from }));
    return;
  }
  await deleteSourceImage(repoKey, from, sourceDatastore, debug);
}

export async function migrateRepo(ref: string, options: MigrateOptions): Promise<void> {
  const { provision, bwlimit, checkpoint, deltaBase, strategy, skipDns, keepSource, debug } =
    options;

  // Source is DERIVED from the repo's config placement (spec/03 §2.3): `machineName`
  // is the ref's home machine (a cluster repo's home is its control node). Migrate's
  // data plane (CoW images + rsync/FIEMAP) is runtime-agnostic, so it operates
  // machine<->machine and does not thread kubeCluster (see resolveMigrateEndpoint).
  // `repoKey` (name or name:tag) drives config + renet; `name` is for messages.
  const { name, repoKey, machineName: from, tag } = await resolveRepoRef(ref);

  // With --provision the target machine is created below, so it is not yet a
  // known machine/cluster name to resolve; use it verbatim.
  const to = provision ? options.to : await resolveMigrateEndpoint(options.to);
  const migrationStart = Date.now();

  await assertCommandPolicy(CMD.REPO_PUSH, repoKey);

  const repoConfig = await configService.getRepository(repoKey);
  if (!repoConfig) {
    throw new ValidationError(t('errors.repositoryNotFound', { name }));
  }

  const currentConfig = await configService.getCurrent();
  assertFamilyMigratable(name, tag, currentConfig?.resources?.repositories?.[name]);

  // Same-home no-op: migrating to where the repo already lives is a 0-cost win,
  // not a full self-transfer. --provision always targets a fresh, distinct host.
  if (!provision && to === from) {
    outputService.info(t('commands.repo.migrate.noOpSameHome', { name, machine: from }));
    return;
  }

  if (provision) {
    await withSpinner(
      t('commands.repo.migrate.provisioning', { machine: to, provider: provision }),
      () => autoProvisionTarget(to, provision, from, !!debug),
      t('commands.repo.migrate.provisioning', { machine: to, provider: provision })
    );
  }

  const localConfig = await configService.getLocalConfig();
  if (!localConfig.machines[from]) {
    throw new ValidationError(t('errors.machineNotFound', { name: from }));
  }
  if (!localConfig.machines[to]) {
    throw new ValidationError(t('errors.machineNotFound', { name: to }));
  }

  if (from !== to) {
    await assertNotMountedOnTarget(repoKey, repoConfig.repositoryGuid, to);
  }

  // Captured BEFORE finalizeCutover rewrites placement to `{machine: to}`: every
  // source-side leg (both pushes, both downs, the source delete) must dispatch
  // against the datastore the repo actually lives in. See SourceDatastore.
  const sourceDatastore = await recordedDatastoreMount(repoKey);

  // Phase 1 retains this base; Phase 2 deltas against it (or an explicit
  // --delta-base override) and prunes it.
  const phase1Base = randomUUID();
  await executePhase1(
    repoKey,
    repoConfig,
    from,
    to,
    bwlimit,
    strategy,
    phase1Base,
    sourceDatastore,
    debug
  );
  const downtimeMs = await executePhase2(
    repoKey,
    repoConfig,
    from,
    to,
    bwlimit,
    checkpoint,
    {
      base: deltaBase ?? phase1Base,
      prune: phase1Base,
      strategy,
    },
    sourceDatastore,
    debug
  );
  await finalizeCutover(name, repoKey, from, to, skipDns, keepSource, sourceDatastore, debug);

  const totalMs = Date.now() - migrationStart;
  outputService.info('');
  outputService.success(t('commands.repo.migrate.complete', { name, from, to }));
  outputService.info(`  Total: ${formatStepDuration(totalMs)}`);
  outputService.info(
    `  ${t('commands.repo.migrate.downtime', { duration: formatStepDuration(downtimeMs) })}`
  );
}
