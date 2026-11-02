/**
 * machine <-> backup-strategy binding.
 *
 * `machine.backupStrategies[]` is what `backup schedule` reads to decide which
 * systemd units to deploy, so a strategy bound to no machine is never deployed.
 * Until these existed the only writer in the codebase was config-refs-prune,
 * which only REMOVES entries, completing a strategy rename meant hand-editing
 * the config file.
 *
 * Both helpers mutate the passed machines record and return whether anything
 * changed, so the caller can skip the write and report a no-op.
 */

import { t } from '../../i18n/index.js';
import type { MachineConfig, RdcConfig } from '../../types/index.js';
import { stateMismatch } from '../../utils/cli-exit-error.js';
import { configService } from './config-resources.js';
import { updateSyncedConfig } from './synced-write.js';

/**
 * Add a binding. Idempotent, returns false when it already exists.
 *
 * Duplicates matter: `backup schedule` iterates this list to build unit names,
 * so a repeated entry would deploy the same unit twice.
 */
export function addStrategyBinding(
  machines: Record<string, MachineConfig>,
  machineName: string,
  strategyName: string
): boolean {
  if (!(machineName in machines)) throw new Error(`Machine "${machineName}" not found`);
  const machine = machines[machineName];

  const current = machine.backupStrategies ?? [];
  if (current.includes(strategyName)) return false;
  machines[machineName] = { ...machine, backupStrategies: [...current, strategyName] };
  return true;
}

/**
 * Remove a binding. Returns false when it was not bound.
 *
 * An emptied list collapses to `undefined` rather than `[]`, matching what
 * config-refs-prune writes when it drops the last dangling reference ,
 * otherwise the same logical state gets two on-disk spellings depending on
 * which code path emptied it.
 */
export function removeStrategyBinding(
  machines: Record<string, MachineConfig>,
  machineName: string,
  strategyName: string
): boolean {
  if (!(machineName in machines)) throw new Error(`Machine "${machineName}" not found`);
  const machine = machines[machineName];

  const current = machine.backupStrategies ?? [];
  if (!current.includes(strategyName)) return false;
  const kept = current.filter((name) => name !== strategyName);
  machines[machineName] = {
    ...machine,
    backupStrategies: kept.length > 0 ? kept : undefined,
  };
  return true;
}

/**
 * Persist a binding change. Lives here rather than as a ConfigService method
 * because config-resources.ts sits exactly on its 512-line budget, and these
 * read-modify-write the machines record through the public resource state like
 * any other caller would.
 */
async function persistBinding(
  machineName: string,
  strategyName: string,
  apply: (m: Record<string, MachineConfig>, machine: string, strategy: string) => boolean
): Promise<boolean> {
  const state = await configService.getResourceState();
  const machines = state.getMachines();
  if (!apply(machines, machineName, strategyName)) return false;
  await state.setMachines(machines);
  return true;
}

/** Bind a strategy to a machine. False when the binding already existed. */
export async function bindBackupStrategy(
  machineName: string,
  strategyName: string
): Promise<boolean> {
  if (!(await configService.getBackupStrategy(strategyName))) {
    throw new Error(`Backup strategy "${strategyName}" not found`);
  }
  return persistBinding(machineName, strategyName, addStrategyBinding);
}

/** Unbind a strategy from a machine. False when it was not bound. */
export function unbindBackupStrategy(machineName: string, strategyName: string): Promise<boolean> {
  return persistBinding(machineName, strategyName, removeStrategyBinding);
}

/** Names of the machines whose `backupStrategies[]` lists `strategyName`. */
export async function machinesBoundToStrategy(strategyName: string): Promise<string[]> {
  const state = await configService.getResourceState();
  return Object.entries(state.getMachines())
    .filter(([, m]) => (m.backupStrategies ?? []).includes(strategyName))
    .map(([name]) => name)
    .sort();
}

/** One document edit: delete the strategy and strip it from every machine's bindings. */
function dropStrategyAndBindings(cfg: RdcConfig, strategyName: string): RdcConfig {
  const strategies = { ...(cfg.resources?.backupStrategies ?? {}) };
  delete strategies[strategyName];
  const machines = { ...(cfg.resources?.machines ?? {}) };
  for (const [name, m] of Object.entries(machines)) {
    const current = m.backupStrategies ?? [];
    if (!current.includes(strategyName)) continue;
    const kept = current.filter((s) => s !== strategyName);
    machines[name] = { ...m, backupStrategies: kept.length > 0 ? kept : undefined };
  }
  return {
    ...cfg,
    resources: { ...(cfg.resources ?? {}), backupStrategies: strategies, machines },
  };
}

/**
 * Remove a strategy without leaving dangling bindings. A bound strategy is refused (exit 12,
 * naming the machines) unless `unbind`, which drops the strategy and every binding in ONE
 * document edit. Returns the machines that were unbound (empty on the clean path).
 */
export async function removeStrategyChecked(
  strategyName: string,
  unbind: boolean
): Promise<string[]> {
  const bound = await machinesBoundToStrategy(strategyName);
  if (bound.length === 0) {
    await configService.removeBackupStrategy(strategyName);
    return [];
  }
  if (!unbind) {
    throw stateMismatch(
      t('commands.backup.strategy.remove.bound', {
        strategy: strategyName,
        count: bound.length,
        machines: bound.join(', '),
      }),
      {
        details: bound,
        next: {
          summary: t('commands.backup.strategy.remove.boundNext'),
          options: [
            {
              description: t('commands.backup.strategy.remove.nextUnbind'),
              run: `rdc backup strategy unbind ${strategyName} --machine <machine>`,
            },
            {
              description: t('commands.backup.strategy.remove.nextForce'),
              run: `rdc backup strategy remove ${strategyName} --unbind`,
            },
          ],
        },
      }
    );
  }
  await updateSyncedConfig(configService.getEffectiveConfigName(), (cfg) =>
    dropStrategyAndBindings(cfg, strategyName)
  );
  return bound;
}
