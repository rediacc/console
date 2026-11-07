import { t } from '../i18n/index.js';
import {
  type ReplicationSyncResult,
  registerStrategyReplication,
  removeReplicationRulesFor,
  replicateDestinations,
} from '../services/backup/backup-replication.js';
import { hasAccountToken } from '../services/backup/backup-retention.js';
import { configService } from '../services/config/config-resources.js';
import { machinesBoundToStrategy } from '../services/config/config-strategy-binding.js';
import { outputService } from '../services/core/output.js';
import type { BackupStrategyConfig } from '../types/index.js';

/** Say what a replication-rule sync did. Never throws: the config change it follows has already been written. */
export function reportReplication(
  result: ReplicationSyncResult,
  verb: 'registered' | 'removed'
): void {
  if (result.unsupported) {
    outputService.warn(t('commands.backup.strategy.replication.unsupported'));
    return;
  }
  if (result.done > 0) {
    const count = { count: result.done };
    outputService.info(
      verb === 'registered'
        ? t('commands.backup.strategy.replication.registered', count)
        : t('commands.backup.strategy.replication.removed', count)
    );
  }
  for (const failure of result.failures) {
    outputService.warn(
      t('commands.backup.strategy.replication.failed', {
        lineage: failure.lineageGuid,
        target: failure.target,
        reason: failure.reason,
      })
    );
  }
}

/** Run a rule sync when the strategy has replicate destinations and an account token exists to authenticate it. */
export async function withReplication(
  strategy: Pick<BackupStrategyConfig, 'include' | 'exclude' | 'destinations'> | undefined,
  run: (
    strategy: Pick<BackupStrategyConfig, 'include' | 'exclude' | 'destinations'>
  ) => Promise<void>
): Promise<void> {
  if (!strategy || replicateDestinations(strategy, false).length === 0) return;
  if (!hasAccountToken()) {
    outputService.warn(t('commands.backup.strategy.replication.notPushed'));
    return;
  }
  try {
    await run(strategy);
  } catch (error) {
    outputService.warn(
      t('commands.backup.strategy.replication.syncFailed', {
        reason: error instanceof Error ? error.message : String(error),
      })
    );
  }
}

/**
 * Bring the server's rules in line with one strategy's replicate destinations after a destination changed: a disabled
 * one loses its rules, an enabled one is registered for every machine the strategy is bound to.
 */
export async function syncReplicationRules(name: string): Promise<void> {
  const strategy = await configService.getBackupStrategy(name);
  await withReplication(strategy, async (found) => {
    const disabled = replicateDestinations(found, false).filter((d) => d.enabled === false);
    reportReplication(await removeReplicationRulesFor(found, disabled), 'removed');
    for (const machine of await machinesBoundToStrategy(name)) {
      reportReplication(await registerStrategyReplication(found, machine), 'registered');
    }
  });
}

/** Drop every replicate destination's rules for the lineages a strategy covers on one machine (an unbind). */
export async function dropReplicationForMachine(
  strategy: BackupStrategyConfig | undefined,
  machine: string
): Promise<void> {
  await withReplication(strategy, async (found) => {
    const all = replicateDestinations(found, false);
    reportReplication(await removeReplicationRulesFor(found, all, machine), 'removed');
  });
}
