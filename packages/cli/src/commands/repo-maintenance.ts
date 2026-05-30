import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import type { RepositoryConfig } from '../schema/schemas.js';
import { configService } from '../services/config-resources.js';
import { localExecutorService } from '../services/local-executor.js';
import { outputService } from '../services/output.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { parseRepositoryListOutput } from './repo-list-parser.js';

/**
 * Repository maintenance commands (issue #75 §12):
 *  - repo gc:   reachability garbage-collection of unreachable immutable commits
 *  - repo fsck: validate config refs (branches/head) against machine objects
 *
 * Both reuse existing bridge functions (repository_list, repository_delete), so
 * they add no new bridge surface. The machine is the object store; the CLI
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

/** GUIDs of objects physically present on the machine, with mount state. */
async function machineObjects(machine: string): Promise<Map<string, { mounted: boolean }>> {
  const result = await localExecutorService.execute({
    functionName: 'repository_list',
    machineName: machine,
    params: {},
    captureOutput: true,
  });
  const objects = new Map<string, { mounted: boolean }>();
  if (!result.success || !result.stdout) return objects;
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
  return objects;
}

/** repo gc -m <machine> [--apply] — delete unreachable immutable commits. */
async function handleGc(options: {
  machine: string;
  apply?: boolean;
  debug?: boolean;
}): Promise<void> {
  try {
    const repos = await configService.listRepositories();
    const reachable = reachableCommits(repos);
    const present = await machineObjects(options.machine);

    // Candidates: immutable commits, present on the machine, unreachable from any
    // ref, and not currently mounted (a mounted object is in use). Working forks
    // are never immutable, so they are excluded by construction.
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

    let deleted = 0;
    for (const c of candidates) {
      const guid = c.config.repositoryGuid;
      const result = await localExecutorService.execute({
        functionName: 'repository_delete',
        machineName: options.machine,
        params: { repository: guid },
        debug: options.debug,
      });
      if (result.success) {
        deleted++;
        outputService.success(t('commands.repo.gc.deleted', { commit: guid.slice(0, 12) }));
      } else {
        outputService.error(t('commands.repo.gc.deleteFailed', { commit: guid.slice(0, 12) }));
      }
    }
    outputService.success(t('commands.repo.gc.applied', { deleted, total: candidates.length }));
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

/** repo fsck -m <machine> — report config-ref vs machine-object drift. */
async function handleFsck(options: { machine: string }): Promise<void> {
  try {
    const repos = await configService.listRepositories();
    const present = await machineObjects(options.machine);
    const reachable = reachableCommits(repos);

    const dangling = findDanglingRefs(repos, present);
    // Orphan objects: an immutable commit present on the machine that no ref reaches.
    const orphans = repos
      .filter((r) => r.config.immutable && present.has(r.config.repositoryGuid))
      .filter((r) => !reachable.has(r.config.repositoryGuid))
      .map((r) => r.config.repositoryGuid);

    if (dangling.length === 0 && orphans.length === 0) {
      outputService.success(t('commands.repo.fsck.clean', { machine: options.machine }));
      return;
    }
    if (dangling.length > 0) {
      outputService.error(t('commands.repo.fsck.danglingHeader', { count: dangling.length }));
      for (const d of dangling)
        outputService.info(`  ${d.ref} -> ${d.guid.slice(0, 12)} (missing)`);
    }
    if (orphans.length > 0) {
      outputService.info(t('commands.repo.fsck.orphanHeader', { count: orphans.length }));
      for (const g of orphans) outputService.info(`  ${g.slice(0, 12)}`);
      outputService.info(t('commands.repo.fsck.orphanHint'));
    }
    process.exitCode = 1;
  } catch (error) {
    handleError(error);
  }
}

/** Register repo maintenance commands (issue #75 §12 lifecycle). */
export function registerRepoMaintenanceCommands(repo: Command): void {
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

  repo
    .command('fsck')
    .summary(t('commands.repo.fsck.descriptionShort'))
    .description(t('commands.repo.fsck.description'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .action((options: { machine: string }) => {
      if (!options.machine) throw new ValidationError(t('errors.machineRequiredLocal'));
      return handleFsck(options);
    });
}
