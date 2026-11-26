/** Ceph install steps for a cluster's ceph-pool members, split from cluster-provision.ts. */

import { DEFAULTS } from '@rediacc/shared/config';
import type { ClusterConfig, ClusterPool } from '../../types/index.js';
import { outputService } from '../core/output.js';
import { getExecutor } from '../executor/executor-factory.js';
import { runJobGroup } from '../jobs/job-group.js';
import {
  CEPH_CLUSTER_NAME,
  dispatchCeph,
  exportCephClientConfig,
  resolveCephMembers,
} from './cluster-ceph.js';
import { ClusterPhasePendingError, clusterVerb } from './cluster-job.js';

/**
 * Install Ceph on the cluster's ceph-pool members, ceph-first:
 *   1. ceph_install_prerequisites on EVERY member,
 *   2. ceph_bootstrap_cluster on the first member (monitor = its IP),
 *   3. ceph_cluster_create once from the first member (all member IPs as nodes),
 *   4. ceph_pool_create for the application pool.
 * A non-success at any step throws (via dispatchCeph) so the install fails loud.
 */
/**
 * Reports whether a ceph mon already answers on a member (i.e. ceph was already
 * bootstrapped, e.g. by the ops provisioning phase). Non-throwing: any failure
 * (mon unreachable, no ceph.conf) means "not bootstrapped", so the caller runs
 * the full bootstrap. A HEALTH_WARN mon still counts as bootstrapped.
 */
async function cephIsBootstrapped(machineName: string, debug?: boolean): Promise<boolean> {
  try {
    const res = await getExecutor().execute({
      functionName: 'ceph_health',
      machineName,
      params: { cluster: CEPH_CLUSTER_NAME },
      captureOutput: true,
      debug,
    });
    return res.success;
  } catch {
    return false;
  }
}

export async function installCeph(
  clusterName: string,
  cephPools: ClusterPool[],
  cluster: ClusterConfig,
  debug?: boolean
): Promise<void> {
  const members = await resolveCephMembers(clusterName, cephPools);
  if (members.length === 0) return; // count>=1 guarantees a member; guard for safety.
  const first = members[0];

  outputService.info(
    `Cluster "${clusterName}": installing Ceph on ${members.length} member(s) as "${CEPH_CLUSTER_NAME}"...`
  );

  // Idempotency: the ops provisioning phase (`renet ops up`) may already have bootstrapped ceph on the ceph-role VMs (mon + /etc/ceph/ceph.conf + OSDs). Re-running ceph_bootstrap then fails hard ("ceph.conf already exists"). If a mon already answers, SKIP prerequisites + bootstrap + cluster_create and only converge the application pool (idempotent). BUG #4: double-bootstrap
  // collision.
  const alreadyUp = await cephIsBootstrapped(first.name, debug);
  if (alreadyUp) {
    outputService.info(
      `  Ceph already bootstrapped on ${first.name} (ops phase); converging pool only.`
    );
  } else {
    // 1. Prerequisites on every ceph member: one job per member under one ticket group, since no member's install needs another's.
    outputService.info(
      `  ceph_install_prerequisites on ${members.map((m) => m.name).join(', ')}...`
    );
    const prerequisites = await runJobGroup(
      clusterVerb(),
      members.map((m) => ({
        machineName: m.name,
        functionName: 'ceph_install_prerequisites',
        params: {},
      })),
      {},
      { debug, label: 'Ceph install step "ceph_install_prerequisites"' }
    );
    // The bootstrap below needs every member installed, so a member still running past its window stops the chain.
    if (prerequisites.pending) {
      throw new ClusterPhasePendingError(
        'ceph_install_prerequisites',
        prerequisites.pendingMachines.join(', '),
        undefined
      );
    }

    // 2. Bootstrap the monitor on the first member.
    outputService.info(`  ceph_bootstrap_cluster (monitor ${first.ip}) on ${first.name}...`);
    await dispatchCeph(
      'ceph_bootstrap_cluster',
      first.name,
      { cluster: CEPH_CLUSTER_NAME, monitor: first.ip },
      debug
    );

    // 3. Create the cluster + OSDs from the first member. The disk's `purpose`
    // field carries the OSD device path; default to /dev/sdb when unspecified.
    const osdDevice = cephPools[0]?.disks?.[0]?.purpose ?? DEFAULTS.CEPH.OSD_DEVICE;
    const nodes = members.map((m) => m.ip).join(',');
    outputService.info(
      `  ceph_cluster_create (nodes ${nodes}, osd ${osdDevice}) on ${first.name}...`
    );
    await dispatchCeph(
      'ceph_cluster_create',
      first.name,
      { cluster: CEPH_CLUSTER_NAME, nodes, osd_device: osdDevice },
      debug
    );
  }

  // 4. Create the application pool (pg_num omitted, let renet default it).
  const pool = cluster.ceph?.pool ?? DEFAULTS.CEPH.POOL;
  const poolParams: Record<string, unknown> = { pool, cluster: CEPH_CLUSTER_NAME };
  // Small/test topologies (<3 OSDs) cannot satisfy the Ceph default size 3, the pool would sit active+undersized+degraded (HEALTH_WARN) forever. When the cluster's own ceph spec has fewer than 3 OSDs, ask for size 2 / min_size
  // 1 so the pool is active+clean. A production topology (>=3 OSDs) passes
  // nothing and keeps Ceph's defaults untouched (finding #9; P2 gate ruling:
  // never change the product default).
  const osdCount = cephOsdCount(cephPools);
  if (osdCount > 0 && osdCount < 3) {
    poolParams.size = 2;
    poolParams.min_size = 1;
    // pg_num 32 for <3-OSD topologies (finding #17 belt-and-suspenders): the default 128 pg × size on 2 OSDs, on top of the ops-phase pool, can exceed mon_max_pg_per_osd (250) and make `osd pool create` hard-fail with ERANGE before autoscaling shrinks the pools. 32 pg (ceph's own small-cluster target) keeps the budget well under the cap regardless of timing.
    poolParams.pg_num = 32;
    outputService.info(
      `  small ceph topology (${osdCount} OSD(s)): creating pool "${pool}" at size 2/min_size 1, pg_num 32.`
    );
  }
  outputService.info(`  ceph_pool_create (pool ${pool}) on ${first.name}...`);
  await dispatchCeph('ceph_pool_create', first.name, poolParams, debug);

  outputService.success(`Cluster "${clusterName}": Ceph pool "${pool}" ready.`);
}

/**
 * Count the OSDs a cluster's ceph pools declare: one per disk device per ceph
 * member (a disk's optional `count` lets a member carry several). A pool with no
 * `disks[]` defaults to a single OSD device per member (the /dev/sdb default).
 * Used to decide whether the application pool needs the small-topology size (#9).
 */
function cephOsdCount(cephPools: ClusterPool[]): number {
  return cephPools.reduce((total, p) => {
    const disksPerMember = p.disks?.reduce((s, d) => s + (d.count ?? 1), 0) ?? 1;
    return total + p.count * Math.max(1, disksPerMember);
  }, 0);
}

/**
 * Distribute ceph client config (/etc/ceph/ceph.conf + admin keyring) from the
 * first ceph mon to every k8s-role node so ANY node can attach an rbd-backed
 * datastore (datastore-mobility, spec 02 §3). cephadm places client config only
 * on ceph hosts; the datastore-centric model needs it on the k8s nodes too, the
 * control node to CREATE the rbd ds-control, a peer node to ATTACH a fork clone.
 * The (base64) conf+keyring are read off the mon and written into /etc/ceph on
 * each target.
 */
export async function distributeCephClientConfig(
  clusterName: string,
  cephPools: ClusterPool[],
  k8sPools: ClusterPool[],
  debug?: boolean
): Promise<void> {
  const cephMembers = await resolveCephMembers(clusterName, cephPools);
  if (cephMembers.length === 0) return;
  const mon = cephMembers[0];

  const payload = await exportCephClientConfig(mon.name, debug);

  for (const pool of k8sPools) {
    for (let i = 1; i <= pool.count; i++) {
      const name = `${clusterName}-${pool.name}-${i}`;
      outputService.info(`  distributing ceph client config to ${name}...`);
      await dispatchCeph(
        'ceph_client_config_install',
        name,
        { conf: payload.conf, keyring: payload.keyring },
        debug
      );
    }
  }
}
