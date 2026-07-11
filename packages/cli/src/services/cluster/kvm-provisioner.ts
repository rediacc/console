/**
 * KVM (local libvirt) cluster provisioning.
 *
 * KVM is a pseudo-provider that never goes through OpenTofu; it boots VMs via
 * `renet ops`, threading a per-cluster group env so two clusters on one host
 * cannot address each other's VMs. It returns the same member shape the tofu path
 * produces, so createCluster stays provider-agnostic downstream.
 */

import { dirname } from 'node:path';
import { DEFAULTS } from '@rediacc/shared/config';
import { OpsManager, buildGroupEnv } from '@rediacc/provisioning';
import type { ClusterConfig, ClusterKvm } from '../../types/index.js';
import {
  getClusterMemberIdsFromConfig,
  setClusterMemberIdsInStore,
} from '../config/config-cluster-logic.js';
import { configService } from '../config/config-resources.js';
import { outputService } from '../core/output.js';
import { opsExecutorService } from '../executor/ops-executor.js';
import { type KvmTopology, resolveKvmTopology } from './kvm-topology.js';

interface ProvisionedMember {
  pool: string;
  index: number;
  ip: string;
}

export interface KvmProvisionResult {
  members: ProvisionedMember[];
  /** The kvm block to persist, carrying the id allocation destroy/scale reuse. */
  kvm: ClusterKvm;
}

/** How long a freshly booted fleet gets to answer SSH before we give up. */
const VM_READY_TIMEOUT_MS = 300_000;

/** renet writes its diagnostics to stderr, falling back to stdout when it is quiet. */
function failureDetail(result: { stdout: string; stderr: string }): string {
  return result.stderr.trim() === '' ? result.stdout : result.stderr;
}

/**
 * Resolve renet the way every other CLI command does. The provisioning package's
 * own resolver walks up from __dirname, which is meaningless once the CLI is a
 * bundled single-file executable.
 */
async function opsManagerFor(topology: KvmTopology, cephPool?: string): Promise<OpsManager> {
  const binaryPath = await opsExecutorService.getRenetPath();
  const groupEnv = buildGroupEnv(topology.network);
  // Finding #17: make the ops phase create the SAME pool the cluster/datastore
  // path uses (default `rbd`) instead of its own `rediacc_rbd_pool`. Otherwise
  // ops makes `rediacc_rbd_pool` and installCeph makes `rbd` — a non-idempotent
  // double pool that also blows the pg budget on small topologies. One pool named
  // what downstream references keeps create/install idempotent and pg-safe.
  if (cephPool) groupEnv.CEPH_POOL_NAME = cephPool;
  return new OpsManager({
    network: topology.network,
    renet: { binaryPath, rootPath: dirname(binaryPath) },
    groupEnv,
  });
}

/**
 * The ceph pool a cluster's ops phase should create — the cluster's own pool
 * (default `rbd`, what the datastore/fork path references), so ops and install
 * converge ONE pool. Undefined for a cluster with no ceph pool (nothing to name).
 */
export function clusterCephPool(config: ClusterConfig): string | undefined {
  if (!config.pools.some((p) => p.role === 'ceph')) return undefined;
  return config.ceph?.pool ?? DEFAULTS.CEPH.POOL;
}

/**
 * Boot a cluster's pool members on local KVM and return their private IPs.
 */
export async function provisionKvmCluster(
  clusterName: string,
  config: ClusterConfig
): Promise<KvmProvisionResult> {
  // Reuse the persisted id ledger so growing a pool never renumbers running VMs.
  const persisted = getClusterMemberIdsFromConfig(await configService.getCurrent(), clusterName);
  const topology = resolveKvmTopology(clusterName, config, persisted);
  const ops = await opsManagerFor(topology, clusterCephPool(config));

  outputService.info(
    `Provisioning ${topology.members.length} KVM VM(s) for "${clusterName}" on ${topology.network.netName}...`
  );
  const started = await ops.startVMs({ force: true, parallel: true });
  if (!started.success) {
    throw new Error(`renet ops up failed for cluster "${clusterName}": ${failureDetail(started)}`);
  }

  if (!(await ops.waitForAllVMs(VM_READY_TIMEOUT_MS))) {
    throw new Error(
      `Cluster "${clusterName}" VMs did not become SSH-reachable within ${VM_READY_TIMEOUT_MS / 1000}s.`
    );
  }

  // Persist the id ledger to state.clusters[*].memberIds (Carry-in 5) so
  // `ops down` and later scale-ups address the SAME VMs.
  await setClusterMemberIdsInStore(
    configService.getEffectiveConfigName(),
    clusterName,
    topology.memberIds
  );

  return {
    members: topology.members.map((m) => ({ pool: m.pool, index: m.index, ip: m.ip })),
    kvm: topology.kvm,
  };
}

/**
 * Destroy a cluster's KVM VMs. `ops down` addresses them by the ids in the group
 * env, which is why the allocation is persisted rather than recomputed.
 */
export async function teardownKvmCluster(
  clusterName: string,
  config: ClusterConfig
): Promise<void> {
  const persisted = getClusterMemberIdsFromConfig(await configService.getCurrent(), clusterName);
  const topology = resolveKvmTopology(clusterName, config, persisted);
  const ops = await opsManagerFor(topology);

  const stopped = await ops.stopVMs();
  if (!stopped.success) {
    throw new Error(
      `renet ops down failed for cluster "${clusterName}": ${failureDetail(stopped)}`
    );
  }
}
