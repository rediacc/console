import type { Command } from 'commander';
import { t } from '../../i18n/index.js';
import {
  listSSHConfigEntries,
  removePersistedKeys,
  removeSSHConfigEntry,
} from '../../remote/vscode/index.js';
import { configService } from '../../services/config/config-resources.js';
import { outputService } from '../../services/core/output.js';
import { setExitCode } from '../../services/core/request-context.js';
import { getExecutor } from '../../services/executor/executor-factory.js';
import { pendingExitCode, runCommandJob } from '../../services/jobs/command-job.js';
import { requireStepOutput } from '../../services/jobs/step-output.js';
import { bindStepHandler, planStep } from '../../services/jobs/steps.js';
import type { PruneReport } from '../../services/repo/prune.js';
import { getOutputFormat, handleError } from '../../utils/errors.js';
import { renderLocalExecutionFailure } from '../../utils/local-execution-failures.js';
import { assertMachineExists } from '../_validate.js';
import {
  buildPrunePreviewRows,
  countPrunedResources,
  parseDatastorePruneOutput,
} from '../datastore-prune-parser.js';

interface PruneOptions {
  dryRun?: boolean;
  orphanedRepos?: boolean;
  pruneUnknown?: boolean;
  forceDeleteMounted?: boolean;
  force?: boolean;
  graceDays?: number;
  debug?: boolean;
}

/** What the phases found, folded into one document for the non-table output formats. */
interface PruneOutcome {
  datastore?: unknown;
  units?: unknown;
  report?: PruneReport;
  failed: boolean;
}

/** Table output renders as each phase runs; any other format is printed once, at the end. */
function isTableOutput(): boolean {
  return getOutputFormat() === 'table';
}

/** The two phase outputs of one `machine_prune` job, split at its `{"prune_phase": ...}` marker lines. */
export function splitPrunePhases(output: string | undefined): { datastore: string; units: string } {
  const phases: Record<string, string[]> = { datastore: [], units: [] };
  let current: string[] | undefined;
  for (const line of (output ?? '').split('\n')) {
    try {
      const marker = (JSON.parse(line) as { prune_phase?: string } | null)?.prune_phase;
      if (marker !== undefined) {
        current = phases[marker];
        continue;
      }
    } catch {
      // Not a marker line.
    }
    current?.push(line);
  }
  return { datastore: phases.datastore.join('\n').trim(), units: phases.units.join('\n').trim() };
}

/** What the last rendered job found, for the orphaned-repos and prune-unknown forms that print one document after their client-side phases. */
let renderedPhases: { datastore?: unknown; units?: unknown } = {};

/** Render both phases of a finished `machine_prune` job: the datastore result (a preview table on dry-run) and the unit report. */
function renderPrunePhases(output: string | undefined, dryRun: boolean): void {
  renderedPhases = {};
  const text = requireStepOutput(output, 'machine prune');
  if (text === undefined) return;
  const phases = splitPrunePhases(text);
  // renet prints the datastore phase as a JSON document even when nothing is prunable, so a blank phase is a lost read.
  // The units phase is text and may legitimately print nothing, so it is not judged.
  if (requireStepOutput(phases.datastore, 'machine prune datastore phase') === undefined) return;
  try {
    const parsed = parseDatastorePruneOutput(phases.datastore);
    renderedPhases.datastore = parsed;
    renderPruneOutcome(parsed, dryRun);
  } catch {
    // Report passthrough, not a parse: an older renet that ignores --output json prints text.
    renderedPhases.datastore = phases.datastore;
    if (phases.datastore && isTableOutput()) outputService.print(phases.datastore);
    outputService.success(t('commands.machine.prune.datastoreCompleted'));
  }
  renderedPhases.units = phases.units;
  if (phases.units && isTableOutput()) outputService.print(phases.units);
  outputService.success(t('commands.machine.prune.unitsCompleted'));
}

/** Render the parsed prune payload: a preview table (dry-run) or a removed-count
 * summary (real run) in table mode; the raw structured object in JSON mode. */
function renderPruneOutcome(parsed: Record<string, unknown>, dryRun: boolean): void {
  if (!isTableOutput()) return;
  if (dryRun) {
    const rows = buildPrunePreviewRows(parsed);
    if (rows.length === 0) {
      outputService.success(t('commands.machine.prune.previewEmpty'));
      return;
    }
    outputService.print(rows, 'table');
    outputService.info(t('commands.machine.prune.dryRunHint', { count: rows.length }));
    return;
  }
  const pruned = countPrunedResources(parsed);
  outputService.success(
    pruned === 0
      ? t('commands.machine.prune.previewEmpty')
      : t('commands.machine.prune.datastorePrunedSummary', { count: pruned })
  );
}

/**
 * Delete a list of orphaned repo GUIDs from a machine.
 *
 * Each `repository_delete` is its own SSH session today, `localExecutorService`
 * has no sticky connection, but `quietSpinners: true` on calls 2..N hides
 * the visible "Config loaded / Connected / Renet provisioned / Machine
 * verified" ladder so the output is one summary line per GUID instead of
 * five. The actual work is unchanged; only the user-facing repetition goes
 * away. (Real per-call wins would require batching `repository_delete` like
 * we did `backup_delete`, see TODO.)
 */
async function deleteOrphanedItems(
  orphaned: { guid: string }[],
  machineName: string,
  debug: boolean | undefined
): Promise<void> {
  let firstCall = true;
  for (const item of orphaned) {
    outputService.info(`Deleting ${item.guid.slice(0, 8)}…`);
    const deleteResult = await getExecutor().execute({
      functionName: 'repository_delete',
      machineName,
      params: { repository: item.guid },
      debug,
      quietSpinners: !firstCall,
    });
    firstCall = false;
    if (!deleteResult.success) {
      outputService.error(`Failed to delete ${item.guid}: ${deleteResult.error}`);
    }
  }
}

/** Remove stale VS Code SSH config entries for repos no longer in config. */
async function cleanupSshArtifacts(machineName: string): Promise<void> {
  try {
    const teamName = (await configService.applyDefaults({})).team ?? '';
    const prefix = `rediacc-${teamName ? `${teamName}-` : '-'}${machineName}-`;
    const repos = await configService.listRepositories();
    const repoNames = new Set(repos.map((r) => r.name));

    for (const entry of listSSHConfigEntries()) {
      if (!entry.startsWith(prefix)) continue;
      const repoName = entry.slice(prefix.length);
      if (repoName && !repoNames.has(repoName)) {
        removeSSHConfigEntry(entry);
        removePersistedKeys(teamName, machineName, repoName);
      }
    }
  } catch {
    /* non-fatal */
  }
}

interface MountableRepo {
  name: string;
  mounted?: boolean;
  /** The repository's Docker daemon answers its socket, with or without containers. */
  docker_running?: boolean;
}

function filterMountedReposForDeletion<T extends MountableRepo>(
  candidates: T[],
  machineName: string,
  options: PruneOptions
): T[] {
  const mounted = candidates.filter((r) => Boolean(r.mounted) || Boolean(r.docker_running));
  if (mounted.length === 0) return candidates;
  if (options.forceDeleteMounted) {
    outputService.warn(
      `--force-delete-mounted: proceeding with ${mounted.length} mounted/running unknown repo(s)`
    );
    return candidates;
  }
  for (const m of mounted) {
    outputService.warn(
      `Skipping ${m.name.slice(0, 8)}…: currently mounted or running on "${machineName}". Pass --force-delete-mounted to override.`
    );
  }
  const mountedSet = new Set(mounted.map((m) => m.name));
  return candidates.filter((r) => !mountedSet.has(r.name));
}

/**
 * Phase 3 (opt-in): Delete repositories the renet `.interim/state` mirror
 * cannot classify, i.e. those that are NOT in the operator's local CLI
 * config AND have no fork-marked mirror. This is a strictly narrower set
 * than `--orphaned-repos`:
 *
 *   --orphaned-repos    deletes everything not in local config (includes
 *                       forks created by other tools, even when the renet
 *                       mirror correctly identifies them as forks).
 *
 *   --prune-unknown     deletes only repos that *both* surfaces have no
 *                       opinion on. A fork without a config entry but with
 *                       `is_fork: true` in its mirror is preserved.
 *
 * Mount-safety preflight: unconditionally skip any repo that's currently
 * mounted on the machine (or has running Docker containers). The override
 * is `--force-delete-mounted`, distinct from `--force` (which controls the
 * archive grace period).
 */
async function pruneUnknownRepos(machineName: string, options: PruneOptions): Promise<void> {
  const { fetchMachineStatus } = await import('../../services/machine/machine-status.js');
  const { classifyRepoType } = await import('../../utils/repo-classify.js');

  outputService.info(t('commands.machine.prune.unknownStarting', { machine: machineName }));

  const listResult = await fetchMachineStatus(machineName, {
    sections: ['repositories'],
    debug: options.debug,
  });
  const repos = listResult.repositories;

  if (repos.length === 0) {
    outputService.info(t('commands.machine.prune.noReposFound'));
    return;
  }

  const configRepos = await configService.listRepositories().catch(() => []);
  const configLookup = new Map<string, { grandGuid?: string }>();
  for (const rc of configRepos) {
    configLookup.set(rc.config.repositoryGuid, { grandGuid: rc.config.grandGuid });
  }

  const unknownAll = repos.filter(
    (r) => classifyRepoType({ is_fork: Boolean(r.is_fork) }, configLookup.get(r.name)) === 'unknown'
  );

  if (unknownAll.length === 0) {
    outputService.success(t('commands.machine.prune.noUnknownRepos'));
    return;
  }

  const deletable = filterMountedReposForDeletion(unknownAll, machineName, options);

  outputService.info(
    t('commands.machine.prune.unknownFound', {
      count: unknownAll.length,
      deletable: deletable.length,
    })
  );

  for (const r of deletable) {
    outputService.info(`  ${r.name.slice(0, 8)}… (${r.size_human}, modified ${r.modified_human})`);
  }

  if (options.dryRun) {
    outputService.warn(`Dry run: ${deletable.length} unknown repo(s) would be deleted`);
    return;
  }

  if (deletable.length === 0) {
    return;
  }

  await deleteOrphanedItems(
    deletable.map((r) => ({ guid: r.name })),
    machineName,
    options.debug
  );
  outputService.success(t('commands.machine.prune.unknownCompleted', { count: deletable.length }));
}

/** Phase 2: Prune orphaned repos not in any config. */
async function pruneOrphanedRepos(
  machineName: string,
  options: PruneOptions,
  outcome: PruneOutcome
): Promise<void> {
  const { analyzePrune, buildPruneReport, printPruneAnalysis, purgeExpiredArchives } = await import(
    '../../services/repo/prune.js'
  );
  const { fetchMachineStatus } = await import('../../services/machine/machine-status.js');
  const { getRepositories } = await import(
    '@rediacc/shared/renet-contract/data/list-types.generated'
  );

  outputService.info(t('commands.machine.prune.orphanedReposStarting', { machine: machineName }));

  const listResult = await fetchMachineStatus(machineName, {
    sections: ['repositories'],
    debug: options.debug,
  });
  const deployedGuids = getRepositories(listResult).map((r) => r.name);

  if (deployedGuids.length === 0) {
    outputService.info(t('commands.machine.prune.noReposFound'));
    outcome.report = buildPruneReport({ orphaned: [], protected: [] }, Boolean(options.dryRun));
    return;
  }

  const analysis = await analyzePrune(deployedGuids, {
    force: options.force,
    graceDays: options.graceDays,
  });
  printPruneAnalysis(analysis, Boolean(options.dryRun));
  outcome.report = buildPruneReport(analysis, Boolean(options.dryRun));

  if (!options.dryRun && analysis.orphaned.length > 0) {
    await deleteOrphanedItems(analysis.orphaned, machineName, options.debug);
    await cleanupSshArtifacts(machineName);

    outputService.success(
      t('commands.machine.prune.orphanedReposCompleted', {
        count: analysis.orphaned.length,
      })
    );
  }

  await purgeExpiredArchives(options.graceDays);
}

/** Fold the phases into exactly one document for json/yaml; a failed phase already printed its own error envelope. */
function printPruneOutcome(outcome: PruneOutcome, dryRun: boolean): void {
  const format = getOutputFormat();
  if (format === 'table' || outcome.failed) return;
  outputService.print(buildPruneData(outcome, dryRun), format);
}

/** The `data` payload of the single document: datastore, units and the orphaned-repos report; the report keys are always present (empty when that phase did not run). */
function buildPruneData(outcome: PruneOutcome, dryRun: boolean): Record<string, unknown> {
  return {
    datastore: outcome.datastore ?? null,
    units: outcome.units ?? null,
    ...(outcome.report ?? { dry_run: dryRun, orphaned_repos: [], protected_repos: [] }),
  };
}

bindStepHandler('renderPruneOutcome', ({ output, params }) => {
  renderPrunePhases(output, params.dryRun === true);
  // A plain prune prints its one document here; the orphan forms print theirs after their client-side phases.
  if (!isTableOutput() && params.orphaned !== true) {
    outputService.print(
      buildPruneData({ failed: false, ...renderedPhases }, params.dryRun === true),
      getOutputFormat()
    );
  }
  return Promise.resolve();
});

const hasOrphanForm = (options: PruneOptions): boolean =>
  options.orphanedRepos === true || options.pruneUnknown === true;

/** Run the one `machine_prune` job. False when it did not finish successfully (still running, or failed and reported). */
async function runPruneJob(machineName: string, options: PruneOptions): Promise<boolean> {
  renderedPhases = {};
  outputService.info(t('commands.machine.prune.startingDatastore', { machine: machineName }));
  const job = await runCommandJob(
    'machine prune',
    {
      functionName: 'machine_prune',
      machineName,
      params: options.dryRun ? { dry_run: true } : {},
      debug: options.debug,
      captureOutput: true,
    },
    [
      planStep('renderPruneOutcome', {
        dryRun: Boolean(options.dryRun),
        orphaned: hasOrphanForm(options),
      }),
    ]
  );
  if (job.kind === 'pending') {
    // The deletion sets of the two orphan forms are client-side phases after the job, so they wait for a finished job.
    if (hasOrphanForm(options)) {
      outputService.warn(t('commands.machine.prune.orphanFormsNeedFinishedJob'));
    }
    const code = pendingExitCode(job);
    if (code !== undefined) setExitCode(code);
    return false;
  }
  if (!job.result.success) {
    renderLocalExecutionFailure(job.result, t('commands.machine.prune.datastoreFailed'));
    return false;
  }
  return true;
}

async function handlePrune(machineName: string, options: PruneOptions): Promise<void> {
  if (!(await runPruneJob(machineName, options))) return;
  const outcome: PruneOutcome = {
    failed: false,
    datastore: renderedPhases.datastore,
    units: renderedPhases.units,
  };
  if (options.orphanedRepos) await pruneOrphanedRepos(machineName, options, outcome);
  if (options.pruneUnknown) await pruneUnknownRepos(machineName, options);
  outputService.success(t('commands.machine.prune.completed'));
  if (hasOrphanForm(options)) printPruneOutcome(outcome, Boolean(options.dryRun));
}

export function registerPruneCommand(machine: Command): void {
  machine
    .command('prune')
    .summary(t('commands.machine.prune.descriptionShort'))
    .description(t('commands.machine.prune.description'))
    .argument('<name>', t('options.name'))
    .option('--dry-run', t('commands.machine.prune.dryRunOption'))
    .option('--orphaned-repos', t('commands.machine.prune.orphanedReposOption'))
    .option('--prune-unknown', t('commands.machine.prune.pruneUnknownOption'))
    .option('--force-delete-mounted', t('commands.machine.prune.forceDeleteMountedOption'))
    .option('--force', t('options.force'))
    .option('--grace-days <days>', t('options.graceDays'), Number.parseInt)
    .option('--debug', t('options.debug'))
    .action(async (machineName: string, options: PruneOptions) => {
      try {
        await assertMachineExists(machineName);
        await handlePrune(machineName, options);
      } catch (error) {
        handleError(error);
      }
    });
}
