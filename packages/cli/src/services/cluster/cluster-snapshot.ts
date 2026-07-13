/**
 * `rdc cluster snapshot` (spec 03 §5.5, R2-F13) — porcelain over the group
 * snapshot plumbing (`datastore snapshot --group`, landed in P1).
 *
 * A cluster snapshot is ONE crash-consistent instant across every rbd-backed
 * datastore the cluster owns (control plane + data), taken through Ceph's group
 * snapshot. Nothing stops; the cluster never notices. It is the same primitive
 * `cluster fork` and the release ladder's rung 0 take before they mutate.
 *
 * ★ The honest limit, surfaced in the payload rather than buried: a LOCAL-backend
 * datastore in the cluster (the NVMe tiering case, 03 §3) has no block-level group
 * primitive, so it is OUTSIDE the instant. That is a warning, not an error, but an
 * operator who thinks they snapshotted the whole cluster and did not is exactly the
 * person who finds out during a restore.
 */

import { getCluster } from '../config/config-cluster-ops.js';
import { outputService } from '../core/output.js';
import { parseCapturedJson } from '../executor/local-executor.js';
import { dispatch, K8S_SERVER_ROLES, k8sPoolsOf, resolveK8sMembers } from './cluster-kube.js';

/** One datastore record from `renet datastore list --json`. */
interface DatastoreRecord {
  name: string;
  backend: string;
  cluster?: string;
  fork?: unknown;
  implicit?: boolean;
}

/** The cluster's control-plane machine: every group op dispatches through it. */
async function controlMachine(clusterName: string): Promise<string> {
  const cluster = await getCluster(clusterName);
  const members = await resolveK8sMembers(clusterName, k8sPoolsOf(cluster));
  const control = members.find((m) => K8S_SERVER_ROLES.has(m.role));
  if (!control) {
    throw new Error(`Cluster "${clusterName}" has no k8s-server member to snapshot through.`);
  }
  return control.name;
}

/** The cluster's datastores, split by whether the group instant covers them. */
async function clusterDatastores(
  control: string,
  clusterName: string,
  debug?: boolean
): Promise<{ inInstant: string[]; outsideInstant: string[] }> {
  const res = await dispatch('datastore_list', control, {}, { debug, capture: true });
  const records = parseCapturedJson<DatastoreRecord[]>(res.stdout).filter(
    (r) => !r.implicit && !r.fork && r.cluster === clusterName
  );
  return {
    inInstant: records.filter((r) => r.backend === 'ceph').map((r) => r.name),
    outsideInstant: records.filter((r) => r.backend !== 'ceph').map((r) => r.name),
  };
}

export interface ClusterSnapshotOptions {
  /** Snapshot label. Default: a UTC timestamp (spec §5.3 [P0-DECIDED]). */
  snapshot?: string;
  debug?: boolean;
}

/** Snapshot every rbd-backed datastore in the cluster at one instant. */
export async function createClusterSnapshot(
  clusterName: string,
  options: ClusterSnapshotOptions = {}
): Promise<void> {
  const snapshot = options.snapshot ?? new Date().toISOString().replace(/[:.]/g, '-');
  const control = await controlMachine(clusterName);
  const { inInstant, outsideInstant } = await clusterDatastores(
    control,
    clusterName,
    options.debug
  );
  if (inInstant.length === 0) {
    throw new Error(
      `Cluster "${clusterName}" has no ceph-backed datastores, so there is no group instant to ` +
        `take. Snapshot its datastores individually: rdc datastore snapshot create <name>.`
    );
  }

  await dispatch(
    'datastore_snapshot_create',
    control,
    { group: clusterName, snapshot },
    { debug: options.debug }
  );

  outputService.success(
    `Cluster "${clusterName}" snapshotted as "${snapshot}": ${inInstant.length} datastore(s) ` +
      `(${inInstant.join(', ')}) at ONE crash-consistent instant. Nothing stopped.`
  );
  if (outsideInstant.length > 0) {
    outputService.warn(
      `Outside the instant: ${outsideInstant.join(', ')} (local-backend datastores have no ` +
        `block-level group primitive, 03 §3). They are NOT part of this snapshot.`
    );
  }
}

/** List the cluster's group snapshots. */
export async function listClusterSnapshots(
  clusterName: string,
  options: { debug?: boolean } = {}
): Promise<unknown> {
  const control = await controlMachine(clusterName);
  const res = await dispatch(
    'datastore_snapshot_list',
    control,
    { group: clusterName },
    { debug: options.debug, capture: true }
  );
  return parseCapturedJson<unknown>(res.stdout);
}
