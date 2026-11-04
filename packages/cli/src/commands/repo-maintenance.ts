import type { RepositoryConfig } from '@rediacc/shared/config-schema';
import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import { setExitCode } from '../services/core/request-context.js';
import { getExecutor } from '../services/executor/executor-factory.js';
import { pendingExitCode, runCommandJob } from '../services/jobs/command-job.js';
import { bindStepHandler, planStep } from '../services/jobs/steps.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { renderLocalExecutionFailure } from '../utils/local-execution-failures.js';
import { recordedDatastoreMount } from '../utils/repo-executor.js';
import { parseRepositoryListOutput } from './repo-list-parser.js';

/**
 * Repository maintenance commands (issue #75 §12):
 *  - repo gc:   reachability garbage-collection of unreachable immutable commits
 *  - repo fsck: validate config refs (branches/head) against machine objects
 *
 * Both read the machine with repository_list; gc --apply deletes through one
 * repository_gc job. The machine is the object store; the CLI
 * config is the ref store (branches/head/headCommit + commitParent lineage).
 */

interface RepoEntry {
  name: string;
  config: RepositoryConfig;
}

/** All GUIDs directly referenced by a ref (branch tips + HEAD + headCommit). */
function refRoots(repos: RepoEntry[]): Set<string> {
  const roots = new Set<string>();
  for (const { config } of repos) {
    for (const tip of Object.values(config.branches ?? {})) roots.add(tip);
    if (config.head) roots.add(config.head);
    if (config.headCommit) roots.add(config.headCommit);
  }
  return roots;
}

/** Closure over commitParent from the ref roots: every commit still reachable. */
function reachableCommits(repos: RepoEntry[]): Set<string> {
  const byGuid = new Map<string, RepositoryConfig>();
  for (const { config } of repos) byGuid.set(config.repositoryGuid, config);

  const reachable = new Set<string>();
  const queue = [...refRoots(repos)];
  while (queue.length > 0) {
    const guid = queue.pop();
    if (!guid || reachable.has(guid)) continue;
    reachable.add(guid);
    const parent = byGuid.get(guid)?.commitParent;
    if (parent) queue.push(parent);
  }
  return reachable;
}

/**
 * Every datastore these repos are recorded on, plus the machine's default (#74).
 *
 * `repository_list` enumerates ONE datastore, there is no `--all-datastores` on
 * it the way there is on the licence verbs, so a single call sees only the
 * machine's default. gc and fsck compare that listing against the WHOLE config,
 * so a repo family living on a named datastore read as "not present on the
 * machine": fsck reported its refs as dangling, and gc could never collect its
 * unreachable commits. Asking each recorded mount in turn needs no new renet
 * surface. `undefined` is in the set on purpose, it is the default datastore.
 */
async function recordedMounts(repos: RepoEntry[]): Promise<(string | undefined)[]> {
  const mounts = new Set<string | undefined>([undefined]);
  for (const { name } of repos) {
    mounts.add(await recordedDatastoreMount(name));
  }
  return [...mounts];
}

/**
 * GUIDs of objects physically present on the machine, with mount state, across
 * every datastore the config places these repos on.
 *
 * A mount that is not attached here simply contributes nothing: the dispatch
 * fails or returns an empty listing, and both are already tolerated. That
 * matters for gc, which only ever deletes objects it found PRESENT, a datastore
 * it could not read yields no candidates rather than a wrong deletion.
 */
async function machineObjects(
  machine: string,
  repos: RepoEntry[]
): Promise<Map<string, { mounted: boolean }>> {
  const objects = new Map<string, { mounted: boolean }>();
  for (const datastore of await recordedMounts(repos)) {
    const result = await getExecutor().execute({
      functionName: 'repository_list',
      machineName: machine,
      datastore,
      params: {},
      captureOutput: true,
      // The deletion set below is computed from this listing, so `--background` leaves the read attached: a ticket handed back early would read as an empty machine and report every ref dangling.
      probe: true,
    });
    if (!result.success || !result.stdout) continue;
    try {
      const entries = parseRepositoryListOutput(result.stdout) as {
        name?: string;
        mounted?: boolean;
      }[];
      for (const e of entries) {
        if (e.name) objects.set(e.name, { mounted: !!e.mounted });
      }
    } catch {
      /* tolerate non-array stdout: treat as no objects */
    }
  }
  return objects;
}

/** One line of the `repository_gc` job's stdout: `{"gc_result": {...}}` per candidate, then `{"gc_summary": {...}}`. */
interface GcResultLine {
  gc_result?: { guid: string; datastore: string; status: string; reason?: string };
  gc_summary?: { total: number; deleted: number; skipped: number; failed: number };
}

/** The job's stdout as result lines; a line that is not one (a log line) is not a result. */
function parseGcLines(output: string | undefined): GcResultLine[] {
  const lines: GcResultLine[] = [];
  for (const raw of (output ?? '').split('\n')) {
    try {
      const parsed = JSON.parse(raw) as GcResultLine;
      if (parsed.gc_result || parsed.gc_summary) lines.push(parsed);
    } catch {
      // Not a result line.
    }
  }
  return lines;
}

/** Print what the gc job did to each candidate, then the totals. A candidate renet skipped on re-check names the reason it gave. */
function reportGcResults(output: string | undefined): void {
  let summary: GcResultLine['gc_summary'];
  for (const line of parseGcLines(output)) {
    const r = line.gc_result;
    if (r?.status === 'deleted') {
      outputService.success(t('commands.repo.gc.deleted', { commit: r.guid.slice(0, 12) }));
    } else if (r?.status === 'failed') {
      outputService.error(t('commands.repo.gc.deleteFailed', { commit: r.guid.slice(0, 12) }));
    } else if (r) {
      outputService.info(`  ${r.guid.slice(0, 12)}  ${r.status}: ${r.reason ?? ''}`);
    }
    if (line.gc_summary) summary = line.gc_summary;
  }
  if (summary && summary.failed === 0) {
    outputService.success(
      t('commands.repo.gc.applied', { deleted: summary.deleted, total: summary.total })
    );
  }
}

bindStepHandler('reportRepoGc', ({ output }) => {
  reportGcResults(output);
  return Promise.resolve();
});

/** repo gc -m <machine> [--apply], delete unreachable immutable commits. */
async function handleGc(options: {
  machine: string;
  apply?: boolean;
  debug?: boolean;
}): Promise<void> {
  try {
    const repos = await configService.listRepositories();
    const reachable = reachableCommits(repos);
    const present = await machineObjects(options.machine, repos);

    // Candidates: immutable commits, present on the machine, unreachable from any ref, and not currently mounted (a mounted object is in use). Working forks are never immutable, so they are excluded by construction.
    const candidates = repos.filter((r) => {
      const guid = r.config.repositoryGuid;
      const obj = present.get(guid);
      return r.config.immutable && obj && !obj.mounted && !reachable.has(guid);
    });

    if (candidates.length === 0) {
      outputService.success(t('commands.repo.gc.nothing', { machine: options.machine }));
      return;
    }

    if (!options.apply) {
      outputService.info(t('commands.repo.gc.dryRunHeader', { count: candidates.length }));
      for (const c of candidates) outputService.info(`  ${c.config.repositoryGuid}  (${c.name})`);
      outputService.info(t('commands.repo.gc.dryRunHint'));
      return;
    }

    // One `repository_gc` job for the whole set: the client computed the candidates from its config, and renet re-checks each one (present, immutable, unmounted) before it deletes it, so a ref set that moved since is never trusted. Each candidate carries its OWN recorded datastore (#74), not the machine default, because gc found it by enumerating those same mounts above.
    const pairs: string[] = [];
    for (const c of candidates) {
      const datastore = await recordedDatastoreMount(c.name);
      pairs.push(datastore ? `${c.config.repositoryGuid}@${datastore}` : c.config.repositoryGuid);
    }
    const outcome = await runCommandJob(
      'repo gc',
      {
        functionName: 'repository_gc',
        machineName: options.machine,
        params: { candidates: pairs.join(',') },
        debug: options.debug,
        captureOutput: true,
      },
      [planStep('reportRepoGc', { machine: options.machine })]
    );
    if (outcome.kind === 'pending') {
      outputService.info(
        t('commands.repo.gc.started', { started: candidates.length, total: candidates.length })
      );
      const code = pendingExitCode(outcome);
      if (code !== undefined) setExitCode(code);
      return;
    }
    if (!outcome.result.success) {
      // The step runs on success only; a failed delete still owes its per-candidate lines.
      reportGcResults(outcome.result.stdout);
      renderLocalExecutionFailure(
        outcome.result,
        t('commands.repo.gc.deleteFailed', { commit: `${candidates.length} commit(s)` })
      );
    }
  } catch (error) {
    handleError(error);
  }
}

/** Dangling refs: branch tips / HEADs pointing at a GUID with no object on the machine. */
function findDanglingRefs(
  repos: RepoEntry[],
  present: Map<string, { mounted: boolean }>
): { ref: string; guid: string }[] {
  const dangling: { ref: string; guid: string }[] = [];
  for (const { name, config } of repos) {
    for (const [branch, tip] of Object.entries(config.branches ?? {})) {
      if (!present.has(tip)) dangling.push({ ref: `${name}#${branch}`, guid: tip });
    }
    if (config.headCommit && !present.has(config.headCommit)) {
      dangling.push({ ref: `${name}@HEAD`, guid: config.headCommit });
    }
  }
  return dangling;
}

/** repo fsck -m <machine>, report config-ref vs machine-object drift. */
async function handleFsck(options: { machine: string }): Promise<void> {
  try {
    const repos = await configService.listRepositories();
    const present = await machineObjects(options.machine, repos);
    const reachable = reachableCommits(repos);

    const dangling = findDanglingRefs(repos, present);
    // Orphan objects: an immutable commit present on the machine that no ref reaches.
    const orphans = repos
      .filter((r) => r.config.immutable && present.has(r.config.repositoryGuid))
      .filter((r) => !reachable.has(r.config.repositoryGuid))
      .map((r) => r.config.repositoryGuid);

    if (dangling.length === 0 && orphans.length === 0) {
      outputService.success(t('commands.repo.admin.fsck.clean', { machine: options.machine }));
      return;
    }
    if (dangling.length > 0) {
      outputService.error(t('commands.repo.admin.fsck.danglingHeader', { count: dangling.length }));
      for (const d of dangling)
        outputService.info(`  ${d.ref} -> ${d.guid.slice(0, 12)} (missing)`);
    }
    if (orphans.length > 0) {
      outputService.info(t('commands.repo.admin.fsck.orphanHeader', { count: orphans.length }));
      for (const g of orphans) outputService.info(`  ${g.slice(0, 12)}`);
      outputService.info(t('commands.repo.admin.fsck.orphanHint'));
    }
    setExitCode(1);
  } catch (error) {
    handleError(error);
  }
}

/** Register repo maintenance commands (issue #75 §12 lifecycle). */
export function registerRepoMaintenanceCommands(repo: Command, admin: Command): void {
  repo
    .command('gc')
    .summary(t('commands.repo.gc.descriptionShort'))
    .description(t('commands.repo.gc.description'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--apply', t('commands.repo.gc.applyOption'))
    .option('--debug', t('options.debug'))
    .action((options: { machine: string; apply?: boolean; debug?: boolean }) => {
      if (!options.machine) throw new ValidationError(t('errors.machineRequiredLocal'));
      return handleGc(options);
    });

  // repo admin fsck --machine <m>: a machine-scoped scan of config refs against the commits actually present. No repo to derive from, so -m stays (§5.4).
  admin
    .command('fsck')
    .summary(t('commands.repo.admin.fsck.descriptionShort'))
    .description(t('commands.repo.admin.fsck.description'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .action((options: { machine: string }) => {
      if (!options.machine) throw new ValidationError(t('errors.machineRequiredLocal'));
      return handleFsck(options);
    });
}
