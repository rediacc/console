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
import type { Command } from 'commander';
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
    .option('--strategy <strategy>', t('commands.repo.migrate.optionStrategy'))
    .option('--skip-dns', t('commands.repo.migrate.optionSkipDns'))
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
  debug?: boolean;
}

/** Execute backup_push with extraMachines resolution (needed for cross-machine rsync).
 * Returns the parsed transfer stats from renet's push_result stdout line, when present. */
async function executePush(
  repoName: string,
  machineName: string,
  params: Record<string, unknown>,
  debug?: boolean
): Promise<PushResultStats | undefined> {
  await configService.ensureRepositoryNetworkId(repoName);
  const result = await getExecutor().execute({
    functionName: 'backup_push',
    machineName,
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
  debug?: boolean
): Promise<void> {
  await configService.ensureRepositoryNetworkId(repoName);
  const result = await getExecutor().execute({
    functionName,
    machineName,
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
    () => executePush(name, from, pushParams.params, debug),
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
        return executePush(name, from, deltaParams.params, debug);
      },
      t('commands.repo.migrate.deltaDone')
    );
  } else {
    await withSpinner(
      t('commands.repo.migrate.stoppingSource'),
      () => executeQuiet('repository_down', name, from, {}, debug),
      t('commands.repo.migrate.sourceStopped')
    );

    cutoverStats = await withSpinner(
      t('commands.repo.migrate.deltaSync'),
      async () => {
        const deltaParams = buildPushParams(name, repoConfig.repositoryGuid, 'machine', to, {
          force: true,
        });
        applyDelta(deltaParams.params);
        return executePush(name, from, deltaParams.params, debug);
      },
      t('commands.repo.migrate.deltaDone')
    );
  }
  renderPhaseStats('commands.repo.migrate.phase2Stats', cutoverStats);

  await withSpinner(
    t('commands.repo.migrate.unmountingSource'),
    () => executeQuiet('repository_down', name, from, { unmount: true }, debug),
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
      await executeQuiet('repository_up', name, to, {}, debug);
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

async function migrateRepo(ref: string, options: MigrateOptions): Promise<void> {
  const { provision, bwlimit, checkpoint, deltaBase, strategy, skipDns, debug } = options;

  // Source is DERIVED from the repo's config placement (spec/03 §2.3): `machineName`
  // is the ref's home machine (a cluster repo's home is its control node). Migrate's
  // data plane (CoW images + rsync/FIEMAP) is runtime-agnostic, so it operates
  // machine<->machine and does not thread kubeCluster (see resolveMigrateEndpoint).
  // `repoKey` (name or name:tag) drives config + renet; `name` is for messages.
  const { name, repoKey, machineName: from } = await resolveRepoRef(ref);

  // With --provision the target machine is created below, so it is not yet a
  // known machine/cluster name to resolve; use it verbatim.
  const to = provision ? options.to : await resolveMigrateEndpoint(options.to);
  const migrationStart = Date.now();

  await assertCommandPolicy(CMD.REPO_PUSH, repoKey);

  const repoConfig = await configService.getRepository(repoKey);
  if (!repoConfig) {
    throw new ValidationError(t('errors.repositoryNotFound', { name }));
  }

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

  // Phase 1 retains this base; Phase 2 deltas against it (or an explicit
  // --delta-base override) and prunes it.
  const phase1Base = randomUUID();
  await executePhase1(repoKey, repoConfig, from, to, bwlimit, strategy, phase1Base, debug);
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
    debug
  );
  await executePhase3(repoKey, to, skipDns, debug);

  const totalMs = Date.now() - migrationStart;
  outputService.info('');
  outputService.success(t('commands.repo.migrate.complete', { name, from, to }));
  outputService.info(`  Total: ${formatStepDuration(totalMs)}`);
  outputService.info(
    `  ${t('commands.repo.migrate.downtime', { duration: formatStepDuration(downtimeMs) })}`
  );
}
