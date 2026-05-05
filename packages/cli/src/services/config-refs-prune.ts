/**
 * Cross-reference pruner for the local config file.
 *
 * The schema has a few directed edges between named resource buckets that
 * silently go stale when a target is renamed or removed:
 *
 *   resources.machines.<m>.backupStrategies[]      → backupStrategies keys
 *   resources.backupStrategies.<s>.exclude[]       → repository names
 *   resources.backupStrategies.<s>.include[]       → repository names
 *
 * This module walks each edge and produces a cleaned `RdcConfig` (mutating
 * the input is OK — the caller deep-clones before calling) plus a structured
 * report of what was dropped and what raised a soft warning.
 *
 * Storage destinations (`backupStrategies.<s>.destinations[].storage`) are
 * intentionally NOT auto-pruned: removing a destination changes the meaning
 * of the strategy (a backup that was going to two storages now goes to one).
 * Those are reported as warnings so the operator can fix manually.
 */

import { parseRepoRef } from '../utils/config-schema.js';
import type { RdcConfig } from '../schema/schemas.js';

export interface DroppedRef {
  path: string;
  value: string;
  reason: string;
}

export interface RefsPruneResult {
  cleaned: RdcConfig;
  dropped: DroppedRef[];
  warnings: string[];
}

type Strategy = NonNullable<RdcConfig['resources']>['backupStrategies'] extends infer M | undefined
  ? M extends Record<string, infer V>
    ? V
    : never
  : never;

type Machine = NonNullable<RdcConfig['resources']>['machines'] extends infer M | undefined
  ? M extends Record<string, infer V>
    ? V
    : never
  : never;

function pruneMachineStrategies(
  machineName: string,
  machine: Machine,
  strategyNames: Set<string>,
  dropped: DroppedRef[]
): void {
  if (!machine.backupStrategies) return;
  const kept = machine.backupStrategies.filter((strategy) => {
    if (strategyNames.has(strategy)) return true;
    dropped.push({
      path: `resources.machines.${machineName}.backupStrategies`,
      value: strategy,
      reason: 'strategy not found in resources.backupStrategies',
    });
    return false;
  });
  if (kept.length !== machine.backupStrategies.length) {
    machine.backupStrategies = kept.length > 0 ? kept : undefined;
  }
}

function pruneStrategyRepoList(
  strategyName: string,
  strategy: Strategy,
  field: 'exclude' | 'include',
  repoNames: Set<string>,
  dropped: DroppedRef[]
): void {
  const list = strategy[field];
  if (!list) return;
  const kept = list.filter((name) => {
    if (repoNames.has(parseRepoRef(name).name)) return true;
    dropped.push({
      path: `resources.backupStrategies.${strategyName}.${field}`,
      value: name,
      reason: 'repository not found in resources.repositories',
    });
    return false;
  });
  if (kept.length !== list.length) {
    strategy[field] = kept.length > 0 ? kept : undefined;
  }
}

function warnOrphanDestinations(
  strategyName: string,
  strategy: Strategy,
  storageNames: Set<string>,
  warnings: string[]
): void {
  for (const dest of strategy.destinations) {
    if (storageNames.has(dest.storage)) continue;
    warnings.push(
      `resources.backupStrategies.${strategyName}.destinations[name=${dest.name}].storage points at "${dest.storage}" which is not in resources.storages. Fix manually; auto-removing the destination would change the strategy's intent`
    );
  }
}

export function pruneDanglingRefs(config: RdcConfig): RefsPruneResult {
  const dropped: DroppedRef[] = [];
  const warnings: string[] = [];

  const machines = config.resources?.machines ?? {};
  const strategies = config.resources?.backupStrategies ?? {};
  const storages = config.resources?.storages ?? {};
  const repos = config.resources?.repositories ?? {};

  const strategyNames = new Set(Object.keys(strategies));
  const storageNames = new Set(Object.keys(storages));
  const repoNames = new Set(Object.keys(repos).map((k) => parseRepoRef(k).name));

  for (const [name, machine] of Object.entries(machines)) {
    pruneMachineStrategies(name, machine, strategyNames, dropped);
  }

  for (const [name, strategy] of Object.entries(strategies)) {
    pruneStrategyRepoList(name, strategy, 'exclude', repoNames, dropped);
    pruneStrategyRepoList(name, strategy, 'include', repoNames, dropped);
    warnOrphanDestinations(name, strategy, storageNames, warnings);
  }

  return { cleaned: config, dropped, warnings };
}
