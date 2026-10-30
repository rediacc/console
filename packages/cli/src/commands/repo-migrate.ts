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
import { reconcileBackupSchedules } from '../services/backup/repo-change-hook.js';
import { resolveExecutionTarget } from '../services/cluster/cluster-target.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import { setExitCode } from '../services/core/request-context.js';
import { getExecutor } from '../services/executor/executor-factory.js';
import { pendingExitCode, runCommandJob } from '../services/jobs/command-job.js';
import { outstandingSteps } from '../services/jobs/run-job.js';
import { bindStepHandler, planStep } from '../services/jobs/steps.js';
import { deployRepoKeyIfNeeded } from '../services/repo/repo-key-deployment.js';
import { ensureTargetRepoLicense } from '../services/repo-migrate-license.js';
import { assertCommandPolicy, CMD } from '../utils/command-policy.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { formatBytes } from '../utils/format.js';
import { resolveRemoteName } from '../utils/remote-resolve.js';
import { recordedDatastoreMount } from '../utils/repo-executor.js';
import { resolveRepoRef } from '../utils/repo-target.js';
import { withSpinner } from '../utils/spinner.js';
import { formatStepDuration } from '../utils/timeline.js';
import { assertBwlimit, bwlimitParam } from './bwlimit-param.js';
import { autoProvisionTarget } from './repo-backup.js';
import { postRepoUpTasks } from './repo-batch-utils.js';
import { parseRepositoryListOutput } from './repo-list-parser.js';

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
    // --health-window / --health-timeout (spec §5.4) are intentionally NOT registered: the current migrate is a two-phase rsync with no post-cutover health-gate path, so advertising them would render dead console fields and promise behavior that does not run. They return with the gate (as-built §12).
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
 * `stat /mnt/rediacc/repositories/<guid>: no such file or directory`, renet
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
    // A probe: the listing decides whether the migrate may go on, so `--background` must not hand back a ticket here.
    probe: true,
  });
  if (!targetCheck.success || !targetCheck.stdout) return;
  try {
    // renet's `list repositories --json` keys repos by GUID under `name` and has no `guid` field. parseRepositoryListOutput tolerates log-prefixed / non-array stdout.
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

/**
 * The params of the `repository_migrate` source job: the hot push retains `retainBase` on both machines, the cutover
 * push deltas against `deltaBase` (an explicit `--delta-base`, never pruned) or that base, and prunes it. The seeds
 * pre-seed the destination with the closest relatives first.
 */
function migrateParams(
  repoKey: string,
  repoConfig: { repositoryGuid: string; parentGuid?: string; grandGuid?: string },
  to: string,
  retainBase: string,
  options: MigrateOptions
): Record<string, unknown> {
  const seeds = [
    ...new Set(
      [repoConfig.repositoryGuid, repoConfig.parentGuid, repoConfig.grandGuid].filter(
        (g): g is string => !!g
      )
    ),
  ];
  return {
    repository: repoKey,
    to,
    retainBase,
    ...(options.deltaBase ? { deltaBase: options.deltaBase } : {}),
    ...(seeds.length > 0 ? { seed: seeds.join(',') } : {}),
    ...(options.strategy ? { strategy: options.strategy } : {}),
    ...(options.checkpoint ? { checkpoint: true } : {}),
    ...(options.bwlimit === undefined ? {} : { bwlimit: bwlimitParam(options.bwlimit) }),
  };
}

/** Phase 3: start on the target and switch DNS. Throws when the target does not come up. */
async function startOnTarget(
  repoKey: string,
  to: string,
  skipDns: boolean,
  debug: boolean
): Promise<void> {
  outputService.info(`  ${t('commands.repo.migrate.startingTarget')}`);
  await deployRepoKeyIfNeeded(repoKey, to);
  // The target's licence store holds nothing for this GUID (a licence is bound to its machine, and the push carries none), and renet licenses every `repository_up`. See ensureTargetRepoLicense.
  await ensureTargetRepoLicense(repoKey, to);
  // Target side: the push landed the image in the TARGET's default datastore (buildExtraMachines gives a peer with no recorded datastore the default
  // mount), and placement has already been rewritten to `{machine: to}` to
  // match. So this leg declares no datastore ON PURPOSE, the source's named mount does not exist here.
  const result = await getExecutor().execute({
    functionName: 'repository_up',
    machineName: to,
    params: { repository: repoKey },
    debug,
    quietSpinners: true,
  });
  if (!result.success) {
    throw new Error(`repository_up failed: ${result.error ?? DEFAULTS.CLOUD.UNKNOWN_ERROR}`);
  }
  outputService.info(`  ${t('commands.repo.migrate.targetStarted')}`);
  if (!skipDns) {
    outputService.info(`  ${t('commands.repo.migrate.switchingDns')}`);
    await postRepoUpTasks(repoKey, to);
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
 * a fully successful phase 3. Fails SAFE, the move already succeeded, so a
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
 * §1.2.1, placement is single-valued per family). Two refusals keep that
 * invariant honest until the family-loop follow-up (grand-first + fork seeds,
 * gated on Open question #1: reflink preservation across backup_push with seeds,
 * a VM check the fleet cannot give this week):
 *   1. a ref naming a non-grand tag is a fork ref, exit 2, teaching push/promote;
 *   2. a family that has forks refuses wholesale, moving only the grand would
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
    .sort((a, b) => Number(a > b) - Number(a < b));
  if (forks.length > 0) {
    throw new ValidationError(
      t('commands.repo.migrate.familyHasForks', { name, forks: forks.join(', ') })
    );
  }
}

/**
 * The successor of the source job, once it succeeded (PLAN-detached-jobs J4): start on the target and switch DNS,
 * then dispose of the source (R3), strictly in that order and in one step, so a target that did not come up never
 * loses the source copy. The placement rewrite (R1) already ran on the `cutover_complete` marker: after the final
 * delta and the source unmount the target holds the single authoritative copy, so the operator's natural recovery
 * (`rdc repo up <name>`) lands there, and a failure here says so and keeps the source images as recovery material.
 *
 * R3: migrate is a MOVE. Only after the target is up is the source image a nameless orphan, so it is deleted here,
 * strictly LAST. `--keep-source` opts out and warns the leftover is a stray reconcile will flag. The delete fails SAFE:
 * a failed cleanup warns and names `machine prune` as the sweep, and never fails the migrate.
 */
async function completeOnTarget(params: {
  name: string;
  repoKey: string;
  from: string;
  to: string;
  skipDns: boolean;
  keepSource: boolean;
  sourceDatastore: SourceDatastore;
  debug: boolean;
}): Promise<void> {
  const { name, repoKey, from, to } = params;
  outputService.info(`\n${t('commands.repo.migrate.phase3')}`);
  try {
    await startOnTarget(repoKey, to, params.skipDns, params.debug);
  } catch (err) {
    outputService.warn(t('commands.repo.migrate.placementRetryHint', { name, machine: to }));
    throw err;
  }
  if (from !== to) {
    if (params.keepSource) {
      outputService.warn(t('commands.repo.migrate.sourceRetained', { name, machine: from }));
    } else {
      await deleteSourceImage(repoKey, from, params.sourceDatastore, params.debug);
    }
    // G4: the repo left `from`, so its backup units re-render (the hook warns, never throws).
    await reconcileBackupSchedules(from);
  }
  // G4: the repo joined `to`, so its backup units re-render.
  await reconcileBackupSchedules(to);
  outputService.success(t('commands.repo.migrate.complete', { name, from, to }));
}

/** One transfer of the migrate as renet recorded it in the job's `migrate_result` line. */
interface MigratePhaseResult {
  name: string;
  transferredBytes: number;
  transferMs: number;
}

interface MigrateJobResult {
  phases: MigratePhaseResult[];
  downtimeMs: number;
}

const MIGRATE_PHASE_NAMES = new Set(['bulk', 'cutover']);

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

/** A phase entry with a known name and finite numbers. Bytes of -1 (renet could not measure) stay; other negatives do not. */
function validPhase(raw: unknown): MigratePhaseResult | undefined {
  if (typeof raw !== 'object' || raw === null) return undefined;
  const { name, transferredBytes, transferMs } = raw as Record<string, unknown>;
  if (typeof name !== 'string' || !MIGRATE_PHASE_NAMES.has(name)) return undefined;
  if (!isFiniteNumber(transferredBytes) || !isFiniteNumber(transferMs)) return undefined;
  if (transferredBytes < -1 || transferMs < 0) return undefined;
  return { name, transferredBytes, transferMs };
}

function parseResultLine(rawLine: string): MigrateJobResult | undefined {
  const start = rawLine.indexOf('{');
  if (start < 0) return undefined;
  try {
    const parsed = JSON.parse(rawLine.slice(start)) as {
      migrate_result?: { phases?: unknown; downtimeMs?: unknown };
    };
    const result = parsed.migrate_result;
    if (!result || !Array.isArray(result.phases)) return undefined;
    if (!isFiniteNumber(result.downtimeMs) || result.downtimeMs < 0) return undefined;
    const phases = result.phases.map(validPhase).filter((p) => p !== undefined);
    return { phases, downtimeMs: result.downtimeMs };
  } catch {
    // Not the result line (log text, a partial line).
    return undefined;
  }
}

/** The `migrate_result` line renet's `repository migrate` prints last: per-phase bytes and time, and the downtime window. Invalid phase entries are dropped. */
export function extractMigrateResult(output: string | undefined): MigrateJobResult | undefined {
  if (!output) return undefined;
  for (const rawLine of output.split('\n')) {
    const result = parseResultLine(rawLine);
    if (result) return result;
  }
  return undefined;
}

/** Renet reports -1 when the push could not tell; 0 is a genuine measurement (a cutover with nothing left to send). */
function phaseStatsLine(key: string, phase: MigratePhaseResult | undefined): string | undefined {
  if (!phase || phase.transferredBytes < 0) return undefined;
  return `  ${t(key, {
    transferred: formatBytes(phase.transferredBytes),
    duration: formatStepDuration(phase.transferMs),
  })}`;
}

/**
 * Print what the migrate job measured: the hot transfer, the cutover transfer and the downtime window, as a summary
 * of finished work. renet prints the result after the cutover marker, so it cannot run earlier than the job's success
 * step. It runs there so the same lines appear when the migrate finished in the foreground and when
 * `rdc job wait <id>` reads the result later. An observer that has no output prints nothing. A rendering failure
 * never aborts the migrate: the report is informational and the steps after it switch DNS and delete the source.
 */
export function renderMigrateResult(output: string | undefined): void {
  try {
    const result = extractMigrateResult(output);
    if (!result) return;
    const lines = [
      phaseStatsLine(
        'commands.repo.migrate.phase1Stats',
        result.phases.find((p) => p.name === 'bulk')
      ),
      phaseStatsLine(
        'commands.repo.migrate.phase2Stats',
        result.phases.find((p) => p.name === 'cutover')
      ),
      `  ${t('commands.repo.migrate.downtime', { duration: formatStepDuration(result.downtimeMs) })}`,
    ];
    for (const line of lines) if (line !== undefined) outputService.info(line);
  } catch {
    // Omit the lines; the migrate continues.
  }
}

bindStepHandler('reportMigrateResult', ({ output }) => {
  renderMigrateResult(output);
  return Promise.resolve();
});

bindStepHandler('migrateComplete', async ({ params }) => {
  const text = (key: string) =>
    typeof params[key] === 'string' && params[key] !== '' ? String(params[key]) : undefined;
  const [name, repoKey, from, to] = ['repo', 'ref', 'source', 'target'].map(text);
  if (!name || !repoKey || !from || !to) {
    throw new Error('step param "repo", "ref", "source" or "target" is missing');
  }
  await completeOnTarget({
    name,
    repoKey,
    from,
    to,
    skipDns: params.skipDns === true,
    keepSource: params.keepSource === true,
    sourceDatastore: text('datastore'),
    debug: params.debug === true,
  });
});

export async function migrateRepo(ref: string, options: MigrateOptions): Promise<void> {
  const { provision, bwlimit, debug } = options;
  // Refused before any provisioning or transfer, not at the first phase that reads it.
  assertBwlimit(bwlimit);

  // Source is DERIVED from the repo's config placement (spec/03 §2.3): `machineName` is the ref's home machine (a cluster repo's home is its control node). Migrate's data plane (CoW images + rsync/FIEMAP) is runtime-agnostic, so it operates machine<->machine and does not thread kubeCluster (see resolveMigrateEndpoint).
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

  // Same-home no-op: migrating to where the repo already lives is a 0-cost win, not a full self-transfer. --provision always targets a fresh, distinct host.
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

  await runMigrateJob({ name, repoKey, repoConfig, from, to, options, migrationStart });
}

/** Run the source job with its steps and settle what it answers: the ticket, a pre-cutover failure, or the summary. */
async function runMigrateJob(args: {
  name: string;
  repoKey: string;
  repoConfig: { repositoryGuid: string; parentGuid?: string; grandGuid?: string };
  from: string;
  to: string;
  options: MigrateOptions;
  migrationStart: number;
}): Promise<void> {
  const { name, repoKey, repoConfig, from, to, options } = args;
  const { skipDns, keepSource, debug } = options;
  // Captured BEFORE the cutover rewrites placement to `{machine: to}`: every source-side leg (both pushes, both downs, the source delete) must dispatch against the datastore the repo actually lives in. See SourceDatastore.
  const sourceDatastore = await recordedDatastoreMount(repoKey);

  // The source job (renet repository_migrate): the hot push retaining a fresh base, the source stop (or the CRIU checkpoint), the delta push against that base, the source unmount, then the `cutover_complete` marker. The placement rewrite fires on the marker; the target up, DNS and the source delete run once the job succeeded.
  await deployRepoKeyIfNeeded(repoKey, to);
  outputService.info(`\n${t('commands.repo.migrate.phase1')}`);
  const outcome = await runCommandJob(
    'repo migrate',
    {
      functionName: 'repository_migrate',
      machineName: from,
      datastore: sourceDatastore,
      params: migrateParams(repoKey, repoConfig, to, randomUUID(), options),
      ...(debug === undefined ? {} : { debug }),
    },
    [
      planStep('migratePlacement', { repo: name, machine: to }),
      planStep('reportMigrateResult'),
      planStep('migrateComplete', {
        repo: name,
        ref: repoKey,
        source: from,
        target: to,
        skipDns: skipDns === true,
        keepSource: keepSource === true,
        ...(sourceDatastore === undefined ? {} : { datastore: sourceDatastore }),
        debug: debug === true,
      }),
    ]
  );
  if (outcome.kind === 'pending') {
    const code = pendingExitCode(outcome);
    if (code !== undefined) setExitCode(code);
    return;
  }
  if (!outcome.result.success) {
    // A pre-cutover failure never reaches the marker, so placement still names the source (spec/03 §5.4 exit-14 row).
    throw new Error(
      `repository_migrate failed: ${outcome.result.error ?? DEFAULTS.CLOUD.UNKNOWN_ERROR}`
    );
  }
  // A step that failed (the target did not come up) already said why and kept the source; the migrate did not complete.
  const unfinished = outstandingSteps(outcome.steps);
  if (unfinished.length > 0) {
    throw new Error(`repo migrate did not complete: ${unfinished.join(', ')} failed`);
  }
  outputService.info(`  Total: ${formatStepDuration(Date.now() - args.migrationStart)}`);
}
