import type { Command } from 'commander';
import { t } from '../../i18n/index.js';
import { localExecutorService } from '../../services/local-executor.js';
import { outputService } from '../../services/output.js';
import { handleError } from '../../utils/errors.js';
import { renderLocalExecutionFailure } from '../../utils/local-execution-failures.js';

interface PruneOptions {
  dryRun?: boolean;
  orphanedRepos?: boolean;
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
  printPruneAnalysis(analysis, options.dryRun ?? true);

  if (!options.dryRun && analysis.orphaned.length > 0) {
    for (const item of analysis.orphaned) {
      outputService.info(`Deleting ${item.guid.slice(0, 8)}…`);
      const deleteResult = await localExecutorService.execute({
        functionName: 'repository_delete',
        machineName,
        params: { repository: item.guid },
        debug: options.debug,
      });
      if (!deleteResult.success) {
        outputService.error(`Failed to delete ${item.guid}: ${deleteResult.error}`);
      }
    }
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
    .command('prune <name>')
    .summary(t('commands.machine.prune.descriptionShort'))
    .description(t('commands.machine.prune.description'))
    .option('--dry-run', t('commands.machine.prune.dryRunOption'))
    .option('--orphaned-repos', t('commands.machine.prune.orphanedReposOption'))
    .option('--force', t('options.force'))
    .option('--grace-days <days>', t('options.graceDays'), Number.parseInt)
    .option('--debug', t('options.debug'))
    .action(async (machineName: string, options: PruneOptions) => {
      try {
        await pruneDatastore(machineName, options);

        if (options.orphanedRepos) {
          await pruneOrphanedRepos(machineName, options);
        }

        outputService.success(t('commands.machine.prune.completed'));
      } catch (error) {
        handleError(error);
      }
    });
}
