/**
 * Pure cluster helpers + config-store writes, split out of config-resources.ts
 * to keep that file under the line budget. These take a plain config value or a
 * config name; they do not import the ConfigService, so there is no import
 * cycle. ConfigService exposes thin methods that delegate here.
 */

import { configFileStorage } from '../../adapters/config-file-storage.js';
import type { CloudProviderConfig, ClusterConfig, RdcConfig } from '../../types/index.js';

/** Projected `<cluster>-<pool>-<n>` names across all clusters -> owning cluster. */
function projectedMemberNames(config: RdcConfig | null): Map<string, string> {
  const byName = new Map<string, string>();
  for (const [cn, cluster] of Object.entries(config?.resources?.clusters ?? {})) {
    for (const pool of cluster.pools) {
      for (let i = 1; i <= pool.count; i++) {
        byName.set(`${cn}-${pool.name}-${i}`, cn);
      }
    }
  }
  return byName;
}

/** Throw if `name` collides with a machine, cluster, or projected member. */
export function assertUniqueName(config: RdcConfig | null, name: string): void {
  if (name in (config?.resources?.machines ?? {})) {
    throw new Error(`Name "${name}" is already a machine`);
  }
  if (name in (config?.resources?.clusters ?? {})) {
    throw new Error(`Name "${name}" is already a cluster`);
  }
  const owner = projectedMemberNames(config).get(name);
  if (owner) {
    throw new Error(`Name "${name}" is a projected member of cluster "${owner}"`);
  }
}

/** Throw if any of a new cluster's projected members collide with existing resources. */
export function assertClusterMembersUnique(
  config: RdcConfig | null,
  name: string,
  clusterConfig: ClusterConfig
): void {
  const existingMachines = config?.resources?.machines ?? {};
  const existingProjected = projectedMemberNames(config);
  for (const pool of clusterConfig.pools) {
    for (let i = 1; i <= pool.count; i++) {
      const member = `${name}-${pool.name}-${i}`;
      if (member in existingMachines) {
        throw new Error(`Cluster "${name}" member "${member}" collides with an existing machine`);
      }
      const owner = existingProjected.get(member);
      if (owner && owner !== name) {
        throw new Error(`Cluster "${name}" member "${member}" collides with cluster "${owner}"`);
      }
    }
  }
}

export function getClusterFromConfig(config: RdcConfig | null, name: string): ClusterConfig {
  const cluster = config?.resources?.clusters?.[name];
  if (!cluster) {
    const available = Object.keys(config?.resources?.clusters ?? {}).join(', ') || 'none';
    throw new Error(`Cluster "${name}" not found. Available: ${available}`);
  }
  return cluster;
}

export function listClustersFromConfig(
  config: RdcConfig | null
): { name: string; config: ClusterConfig }[] {
  if (!config?.resources?.clusters) return [];
  return Object.entries(config.resources.clusters)
    .map(([name, clusterConfig]) => ({ name, config: clusterConfig }))
    .sort((a, b) => a.name.localeCompare(b.name));
}

/** Control node: explicit controlNode, else the first k8s-server/hyperconverged member. */
export function resolveControlNodeFromConfig(
  config: RdcConfig | null,
  clusterName: string
): string {
  const cluster = getClusterFromConfig(config, clusterName);
  if (cluster.controlNode) return cluster.controlNode;
  const pool = cluster.pools.find((p) => p.role === 'k8s-server' || p.role === 'hyperconverged');
  if (!pool) {
    throw new Error(
      `Cluster "${clusterName}" has no k8s-server or hyperconverged pool; set controlNode explicitly.`
    );
  }
  return `${clusterName}-${pool.name}-1`;
}

export async function writeClusterToStore(
  configName: string,
  name: string,
  clusterConfig: ClusterConfig
): Promise<void> {
  await configFileStorage.update(configName, (cfg) => ({
    ...cfg,
    resources: {
      ...(cfg.resources ?? {}),
      clusters: { ...(cfg.resources?.clusters ?? {}), [name]: clusterConfig },
    },
  }));
}

export async function updateClusterInStore(
  configName: string,
  name: string,
  updates: Partial<ClusterConfig>
): Promise<void> {
  await configFileStorage.update(configName, (cfg) => {
    const clusters = { ...(cfg.resources?.clusters ?? {}) };
    if (!(name in clusters)) throw new Error(`Cluster "${name}" not found`);
    clusters[name] = { ...clusters[name], ...updates };
    return { ...cfg, resources: { ...(cfg.resources ?? {}), clusters } };
  });
}

/**
 * Read the persisted KVM member-id ledger (v3 `state.clusters[name].memberIds`,
 * R2-F2 / Carry-in 5). Empty when the cluster has never booted.
 */
export function getClusterMemberIdsFromConfig(
  config: RdcConfig | null,
  name: string
): Record<string, number[]> {
  return config?.state?.clusters?.[name]?.memberIds ?? {};
}

/**
 * Persist the KVM member-id ledger via `updateState` (no version bump) so a
 * later pool-count change never renumbers the VMs already running.
 */
export async function setClusterMemberIdsInStore(
  configName: string,
  name: string,
  memberIds: Record<string, number[]>
): Promise<void> {
  await configFileStorage.updateState(configName, (cfg) => {
    const clusters = { ...(cfg.state?.clusters ?? {}) };
    clusters[name] = { ...(clusters[name] ?? {}), memberIds };
    return { ...cfg, state: { ...(cfg.state ?? {}), clusters } };
  });
}

export async function removeClusterFromStore(configName: string, name: string): Promise<void> {
  await configFileStorage.update(configName, (cfg) => {
    const clusters = { ...(cfg.resources?.clusters ?? {}) };
    if (!(name in clusters)) throw new Error(`Cluster "${name}" not found`);
    delete clusters[name];
    return { ...cfg, resources: { ...(cfg.resources ?? {}), clusters } };
  });
}

export async function writeCloudProviderToStore(
  configName: string,
  name: string,
  config: CloudProviderConfig
): Promise<void> {
  await configFileStorage.update(configName, (cfg) => ({
    ...cfg,
    resources: {
      ...(cfg.resources ?? {}),
      cloudProviders: { ...(cfg.resources?.cloudProviders ?? {}), [name]: config },
    },
  }));
}

export async function removeCloudProviderFromStore(
  configName: string,
  name: string
): Promise<void> {
  await configFileStorage.update(configName, (cfg) => {
    const providers = { ...(cfg.resources?.cloudProviders ?? {}) };
    if (!(name in providers)) throw new Error(`Cloud provider "${name}" not found`);
    delete providers[name];
    return { ...cfg, resources: { ...(cfg.resources ?? {}), cloudProviders: providers } };
  });
}
