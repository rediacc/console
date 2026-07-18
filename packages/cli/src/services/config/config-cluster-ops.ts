/**
 * Cluster operations that read/write through the live ConfigService, split out
 * of config-resources.ts to keep that file within the line budget. These sit
 * above the pure helpers in config-cluster-logic.ts (which config-resources
 * imports directly); there is no import cycle because config-resources does not
 * import this module.
 */

import type { ClusterConfig } from '../../types/index.js';
import {
  assertUniqueName,
  getClusterFromConfig,
  resolveControlNodeFromConfig,
} from './config-cluster-logic.js';
import { configService } from './config-resources.js';

export async function getCluster(name: string): Promise<ClusterConfig> {
  return getClusterFromConfig(await configService.getCurrent(), name);
}

/** Control node for cluster-wide operations (explicit, or first k8s-server member). */
export async function resolveControlNode(clusterName: string): Promise<string> {
  return resolveControlNodeFromConfig(await configService.getCurrent(), clusterName);
}

/** Enforce a single flat name space across machines, clusters, and members. */
export async function assertUniqueResourceName(name: string): Promise<void> {
  assertUniqueName(await configService.getCurrent(), name);
}

/**
 * Materialize provisioned pool members into resources.machines as
 * `<cluster>-<pool>-<n>` with a `{cluster, pool}` backref. Bypasses the
 * uniqueness check because member names legitimately match their own cluster's
 * projection.
 */
export async function materializeClusterMachines(
  clusterName: string,
  members: { pool: string; index: number; ip: string; user: string; port?: number }[]
): Promise<void> {
  for (const m of members) {
    await configService.writeClusterMember(`${clusterName}-${m.pool}-${m.index}`, {
      ip: m.ip,
      user: m.user,
      port: m.port,
      cluster: { cluster: clusterName, pool: m.pool },
    });
  }
}
