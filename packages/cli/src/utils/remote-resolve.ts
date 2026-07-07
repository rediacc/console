/**
 * Resolves a remote name to either a machine or storage from config.
 * Used by push/pull commands to unify --to/--from flags.
 */
import { t } from '../i18n/index.js';
import { configService } from '../services/config/config-resources.js';
import { getCluster } from '../services/config/config-cluster-ops.js';
import { ValidationError } from './errors.js';

type RemoteType = 'machine' | 'storage' | 'cluster';

export interface ResolvedRemote {
  type: RemoteType;
  name: string;
}

/**
 * Resolve a remote name to a machine, storage, or cluster.
 * Resolution order: machine, then storage, then cluster. Machine-first means
 * materialized cluster members (`<cluster>-<pool>-<n>`, which ARE machines)
 * resolve as machines, while the cluster's own name resolves as a cluster.
 */
export async function resolveRemoteName(name: string): Promise<ResolvedRemote> {
  try {
    await configService.getLocalMachine(name);
    return { type: 'machine', name };
  } catch {
    // Not a machine
  }

  try {
    await configService.getStorage(name);
    return { type: 'storage', name };
  } catch {
    // Not a storage
  }

  try {
    await getCluster(name);
    return { type: 'cluster', name };
  } catch {
    // Not a cluster
  }

  const machines = await configService.listMachines();
  const storages = await configService.listStorages();
  const clusters = await configService.listClusters();
  const machineNames = machines.map((m) => m.name).join(', ') || 'none';
  const storageNames = storages.map((s) => s.name).join(', ') || 'none';
  const clusterNames = clusters.map((c) => c.name).join(', ') || 'none';
  throw new ValidationError(
    t('errors.remoteNotFound', {
      name,
      machines: machineNames,
      storages: storageNames,
      clusters: clusterNames,
    })
  );
}
