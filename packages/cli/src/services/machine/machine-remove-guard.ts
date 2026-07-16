/**
 * `machine remove` placement guard (P5 R2-F18).
 *
 * A machine that still holds repository placements must not be silently
 * deregistered: the repos would be left pointing at a machine the config no
 * longer knows, and every derived-machine verb on them would then fail deep
 * (exit 12) with no hint of the cause. So `machine remove` refuses up front
 * (exit 12) and TEACHES the three legitimate ways forward — move the repos
 * (`repo migrate`), delete them (`repo delete`), or knowingly accept the
 * damage class with `--force` (R2-F18: `--force` = "leave the placements
 * dangling on purpose").
 *
 * "Placement references that machine" here means a DIRECT `{machine}` placement
 * (`repo create --machine <name>`). The indirect `{datastore}` arm is a runtime
 * attach observation, not a placement, and is already scrubbed on removal by
 * `dropMachineObservations` — blocking on it would fight that design.
 */

import { t } from '../../i18n/index.js';
import { configService } from '../config/config-resources.js';
import { outputService } from '../core/output.js';
import type { RepositoryConfig } from '../../types/index.js';
import { type CliExitError, stateMismatch } from '../../utils/cli-exit-error.js';

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

/**
 * Refuse `machine remove` (exit 12) when repos are still placed on the machine,
 * unless `--force`. With `--force`, proceed but WARN that the surviving
 * placements are now dangling (they are left untouched by the removal — that is
 * the accepted damage class).
 */
export async function guardMachineRemoval(machineName: string, force?: boolean): Promise<void> {
  const placed = reposPlacedOnMachine(machineName, await configService.listRepositories());
  if (placed.length === 0) return;
  if (!force) {
    throw machineRemovePlacementError(machineName, placed);
  }
  outputService.warn(
    t('commands.machine.remove.forceDangling', {
      name: machineName,
      count: placed.length,
      repos: placed.join(', '),
    })
  );
}
