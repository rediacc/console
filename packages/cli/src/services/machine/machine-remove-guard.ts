/**
 * `machine remove` placement guard (P5 R2-F18).
 *
 * A machine that still holds repository placements must not be silently
 * deregistered: the repos would be left pointing at a machine the config no
 * longer knows, and every derived-machine verb on them would then fail deep
 * (exit 12) with no hint of the cause. So `machine remove` refuses up front
 * (exit 12) and TEACHES the three legitimate ways forward, move the repos
 * (`repo migrate`), delete them (`repo delete`), or knowingly accept the
 * damage class with `--force` (R2-F18: `--force` = "leave the placements
 * dangling on purpose").
 *
 * "Placement references that machine" here means a DIRECT `{machine}` placement
 * (`repo create --machine <name>`). The indirect `{datastore}` arm is a runtime
 * attach observation, not a placement, and is already scrubbed on removal by
 * `dropMachineObservations`, blocking on it would fight that design.
 */

import { t } from '../../i18n/index.js';
import type { RepositoryConfig } from '../../types/index.js';
import { type CliExitError, stateMismatch } from '../../utils/cli-exit-error.js';
import { configService } from '../config/config-resources.js';
import { outputService } from '../core/output.js';

/** Names of the repositories whose placement DIRECTLY names `machineName`. */
export function reposPlacedOnMachine(
  machineName: string,
  repos: { name: string; config: RepositoryConfig }[]
): string[] {
  return repos
    .filter((r) => {
      const p = r.config.placement;
      return p !== undefined && 'machine' in p && p.machine === machineName;
    })
    .map((r) => r.name);
}

/**
 * Build the exit-12 teaching error naming the offending repos and the three
 * legitimate verbs to resolve it.
 */
export function machineRemovePlacementError(
  machineName: string,
  placedRepos: string[]
): CliExitError {
  const repos = placedRepos.join(', ');
  return stateMismatch(
    t('commands.machine.remove.placementConflict', {
      name: machineName,
      count: placedRepos.length,
      repos,
    }),
    {
      details: placedRepos,
      next: {
        summary: t('commands.machine.remove.placementConflictNext'),
        options: [
          {
            description: t('commands.machine.remove.nextMigrate'),
            run: 'rdc repo migrate <repo> --to <other-machine>',
          },
          {
            description: t('commands.machine.remove.nextDelete'),
            run: 'rdc repo delete <repo>',
          },
          {
            description: t('commands.machine.remove.nextForce'),
            run: `rdc machine remove ${machineName} --force`,
          },
        ],
      },
    }
  );
}

/** Repos whose datastore placement names a datastore currently attached to `machineName`. */
export function reposOnAttachedDatastores(
  machineName: string,
  attachedTo: Record<string, { attachedTo?: string }>,
  repos: { name: string; config: RepositoryConfig }[]
): string[] {
  const stores = new Set(
    Object.entries(attachedTo)
      .filter(([, s]) => s.attachedTo === machineName)
      .map(([ds]) => ds)
  );
  return repos
    .filter((r) => {
      const p = r.config.placement;
      return p !== undefined && 'datastore' in p && stores.has(p.datastore);
    })
    .map((r) => r.name);
}

function clusterMemberError(machineName: string, cluster: string): CliExitError {
  return stateMismatch(t('commands.machine.remove.clusterMember', { name: machineName, cluster }), {
    next: {
      summary: t('commands.machine.remove.clusterMemberNext'),
      options: [
        {
          description: t('commands.machine.remove.nextEvict'),
          run: `rdc cluster evict ${machineName}`,
        },
      ],
    },
  });
}

function strategyBoundError(machineName: string, strategies: string[]): CliExitError {
  return stateMismatch(
    t('commands.machine.remove.strategiesBound', {
      name: machineName,
      count: strategies.length,
      strategies: strategies.join(', '),
    }),
    {
      details: strategies,
      next: {
        summary: t('commands.machine.remove.strategiesBoundNext'),
        options: [
          {
            description: t('commands.machine.remove.nextUnbind'),
            run: `rdc backup strategy unbind <strategy> --machine ${machineName}`,
          },
          {
            description: t('commands.machine.remove.nextForceStrategies'),
            run: `rdc machine remove ${machineName} --force`,
          },
        ],
      },
    }
  );
}

/**
 * Refuse `machine remove` (exit 12) while anything still references the machine: a cluster
 * membership (never forceable, `cluster evict` owns that), repos placed on it directly or on a
 * datastore attached to it, and bound backup strategies. `--force` covers the last two and
 * WARNS once per reference kind, naming each reference (the accepted damage class: they dangle).
 */
export async function guardMachineRemoval(machineName: string, force?: boolean): Promise<void> {
  const cfg = await configService.getCurrent();
  const cluster = cfg?.resources?.machines?.[machineName]?.cluster;
  if (cluster) {
    throw clusterMemberError(machineName, cluster.cluster);
  }
  const repos = await configService.listRepositories();
  const direct = reposPlacedOnMachine(machineName, repos);
  const viaDatastore = reposOnAttachedDatastores(
    machineName,
    cfg?.state?.datastores ?? {},
    repos
  ).filter((r) => !direct.includes(r));
  const placed = [...direct, ...viaDatastore];
  const strategies = cfg?.resources?.machines?.[machineName]?.backupStrategies ?? [];
  if (!force) {
    if (placed.length > 0) throw machineRemovePlacementError(machineName, placed);
    if (strategies.length > 0) throw strategyBoundError(machineName, strategies);
    return;
  }
  if (placed.length > 0) {
    outputService.warn(
      t('commands.machine.remove.forceDangling', {
        name: machineName,
        count: placed.length,
        repos: placed.join(', '),
      })
    );
  }
  if (strategies.length > 0) {
    outputService.warn(
      t('commands.machine.remove.forceStrategies', {
        name: machineName,
        count: strategies.length,
        strategies: strategies.join(', '),
      })
    );
  }
}
