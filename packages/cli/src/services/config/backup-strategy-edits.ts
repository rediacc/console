/**
 * Pure edits of the `resources.backupStrategies` map. ConfigService hands each one to its synced
 * write path, which applies it to the document being written.
 */

import type { BackupStrategyConfig, BackupStrategyDestination } from '../../types/index.js';

/** Create the strategy or merge `update` into it. */
export function applyStrategyUpdate(
  strategies: Record<string, BackupStrategyConfig>,
  strategyName: string,
  update: Partial<BackupStrategyConfig>
): void {
  const existing = strategies[strategyName] ?? { destinations: [], schedule: '' };
  strategies[strategyName] = { ...existing, ...update };
}

/** Add the destination, or merge it into the one of the same name; destinations stay sorted by name. */
export function applyDestinationUpsert(
  strategies: Record<string, BackupStrategyConfig>,
  strategyName: string,
  dest: BackupStrategyDestination
): void {
  const strategy = strategies[strategyName] as BackupStrategyConfig | undefined;
  if (!strategy) throw new Error(`Backup strategy "${strategyName}" not found`);
  const destinations = [...strategy.destinations];
  const idx = destinations.findIndex((d) => d.name === dest.name);
  if (idx >= 0) destinations[idx] = { ...destinations[idx], ...dest };
  else destinations.push(dest);
  destinations.sort((a, b) => a.name.localeCompare(b.name));
  strategies[strategyName] = { ...strategy, destinations };
}

/** Drop the named destination; an unknown strategy is left alone. */
export function applyDestinationRemoval(
  strategies: Record<string, BackupStrategyConfig>,
  strategyName: string,
  destName: string
): void {
  if (!Object.hasOwn(strategies, strategyName)) return;
  const strategy = strategies[strategyName];
  strategies[strategyName] = {
    ...strategy,
    destinations: strategy.destinations.filter((d) => d.name !== destName),
  };
}
