import {
  listSSHConfigEntries,
  removePersistedKeys,
  removeSSHConfigEntry,
} from '@rediacc/shared-desktop/vscode';
import type { Command } from 'commander';
import { t } from '../../i18n/index.js';
import { configService } from '../../services/config-resources.js';
import { localExecutorService } from '../../services/local-executor.js';
import { outputService } from '../../services/output.js';
import { handleError } from '../../utils/errors.js';
import { renderLocalExecutionFailure } from '../../utils/local-execution-failures.js';

interface PruneOptions {
  dryRun?: boolean;
  orphanedRepos?: boolean;
  pruneUnknown?: boolean;
  forceDeleteMounted?: boolean;
  force?: boolean;
  graceDays?: number;
  debug?: boolean;
}

/** Phase 1: Run datastore prune via renet. */
async function pruneDatastore(machineName: string, options: PruneOptions): Promise<void> {
  const params: Record<string, unknown> = {};
  if (options.dryRun) params.dry_run = true;

  outputService.info(t('commands.machine.prune.startingDatastore', { machine: machineName }));

  const result = await localExecutorService.execute({
    functionName: 'repository_prune',
    machineName,
    params,
    debug: options.debug,
  });

  if (result.success) {
    outputService.success(t('commands.machine.prune.datastoreCompleted'));
  } else {
    renderLocalExecutionFailure(result, t('commands.machine.prune.datastoreFailed'));
  }
}

/**
 * Delete a list of orphaned repo GUIDs from a machine.
 *
 * Each `repository_delete` is its own SSH session today — `localExecutorService`
 * has no sticky connection — but `quietSpinners: true` on calls 2..N hides
 * the visible "Config loaded / Connected / Renet provisioned / Machine
 * verified" ladder so the output is one summary line per GUID instead of
 * five. The actual work is unchanged; only the user-facing repetition goes
 * away. (Real per-call wins would require batching `repository_delete` like
 * we did `backup_delete` — see TODO.)
 */
async function deleteOrphanedItems(
  orphaned: { guid: string }[],
  machineName: string,
  debug: boolean | undefined
): Promise<void> {
  let firstCall = true;
  for (const item of orphaned) {
    outputService.info(`Deleting ${item.guid.slice(0, 8)}…`);
    const deleteResult = await localExecutorService.execute({
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
 * cannot classify — i.e. those that are NOT in the operator's local CLI
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
  const { fetchMachineStatus } = await import('../../services/machine-status.js');
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
async function pruneOrphanedRepos(machineName: string, options: PruneOptions): Promise<void> {
  const { analyzePrune, printPruneAnalysis, purgeExpiredArchives } = await import(
    '../../services/prune.js'
  );
  const { fetchMachineStatus } = await import('../../services/machine-status.js');
  const { getRepositories } = await import('@rediacc/shared/queue-vault/data/list-types.generated');

  outputService.info(t('commands.machine.prune.orphanedReposStarting', { machine: machineName }));

  const listResult = await fetchMachineStatus(machineName, {
    sections: ['repositories'],
    debug: options.debug,
  });
  const deployedGuids = getRepositories(listResult).map((r) => r.name);

  if (deployedGuids.length === 0) {
    outputService.info(t('commands.machine.prune.noReposFound'));
    return;
  }

  const analysis = await analyzePrune(deployedGuids, {
    force: options.force,
    graceDays: options.graceDays,
  });
  printPruneAnalysis(analysis, Boolean(options.dryRun));

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

export function registerPruneCommand(machine: Command): void {
  machine
    .command('prune')
    .summary(t('commands.machine.prune.descriptionShort'))
    .description(t('commands.machine.prune.description'))
    .requiredOption('--name <name>', t('options.name'))
    .option('--dry-run', t('commands.machine.prune.dryRunOption'))
    .option('--orphaned-repos', t('commands.machine.prune.orphanedReposOption'))
    .option('--prune-unknown', t('commands.machine.prune.pruneUnknownOption'))
    .option('--force-delete-mounted', t('commands.machine.prune.forceDeleteMountedOption'))
    .option('--force', t('options.force'))
    .option('--grace-days <days>', t('options.graceDays'), Number.parseInt)
    .option('--debug', t('options.debug'))
    .action(async (options: PruneOptions & { name: string }) => {
      try {
        const machineName = options.name;
        await pruneDatastore(machineName, options);

        if (options.orphanedRepos) {
          await pruneOrphanedRepos(machineName, options);
        }

        if (options.pruneUnknown) {
          await pruneUnknownRepos(machineName, options);
        }

        outputService.success(t('commands.machine.prune.completed'));
      } catch (error) {
        handleError(error);
      }
    });
}
