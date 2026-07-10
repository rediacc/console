/**
 * Map a ClusterConfig onto the VM topology `renet ops` understands.
 *
 * `renet ops` models one libvirt network holding a control/registry VM plus two
 * addressable id sets: workers and ceph nodes. A cluster instead has arbitrarily
 * named pools with roles. This module is the translation, and it is the only
 * place that decides which numeric VM id a pool member gets.
 *
 * The allocation is deterministic, but it is still persisted into the cluster
 * config (`kvm.memberIds`) rather than recomputed on demand: `ops down` tears VMs
 * down by id, so a later change to a pool's `count` must not renumber the VMs
 * that are already running.
 */

import type { VMNetworkConfig } from '@rediacc/provisioning';
import type { ClusterConfig, ClusterKvm, ClusterPool } from '../../types/index.js';

/** First id for each renet id-space. Matches the ops harness convention. */
const CONTROL_ID = 1;
const WORKER_ID_BASE = 11;
const CEPH_ID_BASE = 21;

interface KvmMember {
  pool: string;
  /** 1-based index within the pool, matching materializeClusterMachines. */
  index: number;
  vmId: number;
  ip: string;
}

export interface KvmTopology {
  network: VMNetworkConfig;
  members: KvmMember[];
  /** pool name -> vm ids, to persist back into the cluster config. */
  memberIds: Record<string, number[]>;
  /** The cluster's kvm block, already validated as present. */
  kvm: ClusterKvm;
}

/** renet derives a VM's address as netBase.(netOffset + vmId). */
export function vmIp(netBase: string, netOffset: number, vmId: number): string {
  return `${netBase}.${netOffset + vmId}`;
}

function isCephPool(pool: ClusterPool): boolean {
  return pool.role === 'ceph';
}

/**
 * Allocate VM ids per pool, reusing any already persisted for that pool so a
 * running cluster keeps its addresses. Ceph pools draw from the ceph id space,
 * every other supported role from the worker one.
 */
function allocateIds(cluster: ClusterConfig): Record<string, number[]> {
  const persisted = cluster.kvm?.memberIds ?? {};
  const allocation: Record<string, number[]> = {};

  const used = new Set<number>([cluster.kvm?.controlId ?? CONTROL_ID]);
  for (const ids of Object.values(persisted)) {
    for (const id of ids) used.add(id);
  }

  const nextFree = (base: number): number => {
    let id = base;
    while (used.has(id)) id++;
    used.add(id);
    return id;
  };

  for (const pool of cluster.pools) {
    const base = isCephPool(pool) ? CEPH_ID_BASE : WORKER_ID_BASE;
    const existing = persisted[pool.name] ?? [];
    const ids = existing.slice(0, pool.count);
    while (ids.length < pool.count) ids.push(nextFree(base));
    allocation[pool.name] = ids;
  }
  return allocation;
}

/**
 * Resolve the full topology. Throws when the cluster cannot be expressed in the
 * ops model, rather than booting something that does not match the config.
 */
export function resolveKvmTopology(clusterName: string, cluster: ClusterConfig): KvmTopology {
  if (!cluster.kvm) {
    throw new Error(
      `Cluster "${clusterName}" has no kvm topology. Add one with ` +
        `\`rdc config cluster add --provider kvm --net-name <libvirt-net> --net-base <a.b.c>\`.`
    );
  }
  const unsupported = cluster.pools.filter((p) => p.role === 'hyperconverged');
  if (unsupported.length > 0) {
    throw new Error(
      `KVM clusters cannot express hyperconverged pools (${unsupported
        .map((p) => p.name)
        .join(', ')}): renet ops separates worker and ceph VMs. ` +
        `Split them into a k8s pool and a ceph pool.`
    );
  }

  const { netName, netBase, controlId, dockerRegistry } = cluster.kvm;
  const netOffset = cluster.kvm.netOffset ?? 0;
  const memberIds = allocateIds(cluster);

  const workerIds: number[] = [];
  const cephIds: number[] = [];
  const members: KvmMember[] = [];

  for (const pool of cluster.pools) {
    const ids = memberIds[pool.name];
    for (const [i, vmId] of ids.entries()) {
      (isCephPool(pool) ? cephIds : workerIds).push(vmId);
      members.push({
        pool: pool.name,
        index: i + 1,
        vmId,
        ip: vmIp(netBase, netOffset, vmId),
      });
    }
  }

  return {
    network: {
      netBase,
      netOffset,
      bridgeId: controlId,
      workerIds,
      cephIds,
      netName,
      dockerRegistry,
    },
    members,
    memberIds,
    kvm: cluster.kvm,
  };
}
