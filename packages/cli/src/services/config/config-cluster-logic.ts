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
    // BUG #22: also drop the parallel state.clusters entry. Leaving it stranded a
    // dead cluster in state after destroy (B1 witnessed b1src/rdst twice), and —
    // worse — a same-name recreate would inherit the old memberIds ledger and
    // renumber onto the wrong VM ids. State is observation; when the cluster is
    // gone, its state goes with it.
    const stateClusters = { ...(cfg.state?.clusters ?? {}) };
    delete stateClusters[name];

    // BUG #89: #22 stated that principle and then applied it to ONE field. Everything
    // else the cluster owned kept its observation: state.datastores still named
    // `<cluster>-cp-1` as the holder of a datastore whose cluster was gone.
    //
    // That is not untidiness, it is a routing hazard. `state.datastores[*].attachedTo` IS
    // the derived-machine routing hint, and machine names are DETERMINISTIC — a same-name
    // recreate re-mints `<cluster>-cp-1`, so the stale hint does not dangle harmlessly, it
    // re-aims at a brand-new, same-named machine that has no such datastore. resolve-machine
    // throws only when the hint is ABSENT; a hint that is merely WRONG is trusted.
    //
    // So the observation goes, and the DECLARATION stays. That split is the whole rule:
    // `resources.*` is what the operator declared and may well intend to recreate; a spec
    // outliving its cluster is defensible. `state.*` is what we observed, and an observation
    // of a world that no longer exists is a lie by construction. Do not "fix" this by also
    // deleting the resources — that would discard the operator's intent.
    const ownedDatastores = new Set(
      Object.entries(cfg.resources?.datastores ?? {})
        .filter(([, ds]) => ds.cluster === name)
        .map(([dsName]) => dsName)
    );
    const stateDatastores = { ...(cfg.state?.datastores ?? {}) };
    for (const ds of ownedDatastores) delete stateDatastores[ds];

    // A repo's observation lives or dies with the datastore it was placed on.
    const stateRepos = { ...(cfg.state?.repos ?? {}) };
    for (const [repo, family] of Object.entries(cfg.resources?.repositories ?? {})) {
      const placement = family.placement;
      if (placement && 'datastore' in placement && ownedDatastores.has(placement.datastore)) {
        delete stateRepos[repo];
      }
    }

    return {
      ...cfg,
      resources: { ...(cfg.resources ?? {}), clusters },
      state: {
        ...(cfg.state ?? {}),
        clusters: stateClusters,
        datastores: stateDatastores,
        repos: stateRepos,
      },
    };
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

/**
 * #89, third site of the class: `machine remove` dropped the DECLARATION and kept the
 * OBSERVATION — `state.machines[m]`, and every `state.datastores[*]` hint still naming `m`.
 *
 * The datastore half is the one that bites. `state.datastores[*].attachedTo` IS the
 * derived-machine routing hint; `resolve-machine` throws only when it is ABSENT, so a hint
 * that is merely WRONG gets followed. Machine names are DETERMINISTIC, so re-adding the name
 * re-aims that hint at a brand-new machine which has no such datastore. That is the #89
 * hazard arriving through `machine remove` instead of `cluster destroy`.
 *
 * The DECLARATIONS (`resources.datastores`) stay: the operator may intend to re-add the
 * machine and re-attach. A spec outliving its machine is defensible; an observation of a
 * world that no longer exists is a lie by construction.
 */
export async function dropMachineObservations(
  configName: string,
  machineName: string
): Promise<void> {
  await configFileStorage.updateState(configName, (cfg) => {
    const machines = { ...(cfg.state?.machines ?? {}) };
    delete machines[machineName];
    const datastores = { ...(cfg.state?.datastores ?? {}) };
    for (const [ds, hint] of Object.entries(datastores)) {
      if (hint.attachedTo === machineName) delete datastores[ds];
    }
    return { ...cfg, state: { ...(cfg.state ?? {}), machines, datastores } };
  });
}
