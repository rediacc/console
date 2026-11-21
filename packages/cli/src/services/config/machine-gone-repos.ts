/**
 * Repository entries whose machine is gone from the config (#80f7476a).
 *
 * A repo's placement names the machine that holds its image: `{machine}` directly, or `{datastore}`
 * through the machine the datastore is attached to. Once that machine leaves the config (`machine
 * deprovision`, `machine remove`), nothing can reach the image, and every repo verb used to refuse
 * with `Machine "<name>" not found`, `repo delete` included, so the entry could not be removed.
 */

import type { RdcConfig } from '@rediacc/shared/config-schema';

/** The machine a family's placement resolves to, or undefined when it names none. */
function placementMachine(
  config: RdcConfig,
  placement: { machine: string } | { datastore: string } | undefined
): string | undefined {
  if (!placement) return undefined;
  if ('machine' in placement) return placement.machine || undefined;
  return config.state?.datastores?.[placement.datastore]?.attachedTo || undefined;
}

/** True when `machine` is a machine of this config. */
export function machineExists(config: RdcConfig, machine: string): boolean {
  return machine in (config.resources?.machines ?? {});
}

/** The repository keys (`name:tag`) whose placement resolves to `machine`. */
export function repoKeysPlacedOn(config: RdcConfig, machine: string): string[] {
  const keys: string[] = [];
  for (const [name, family] of Object.entries(config.resources?.repositories ?? {})) {
    if (placementMachine(config, family.placement) !== machine) continue;
    for (const tag of Object.keys(family.tags)) keys.push(`${name}:${tag}`);
  }
  return keys;
}

export interface GoneMachineRepo {
  /** The family name. */
  name: string;
  /** The machine its placement names, which the config no longer has. */
  machine: string;
  /** Grand tag's GUID, for cross-checking. */
  guid?: string;
}

/** Families placed on a machine the config no longer has. */
export function findGoneMachineRepos(config: RdcConfig): GoneMachineRepo[] {
  const out: GoneMachineRepo[] = [];
  for (const [name, family] of Object.entries(config.resources?.repositories ?? {})) {
    const machine = placementMachine(config, family.placement);
    if (machine === undefined || machineExists(config, machine)) continue;
    const grand = family.grand ? family.tags[family.grand] : undefined;
    out.push({ name, machine, guid: grand?.repositoryGuid });
  }
  return out;
}
