/**
 * `rdc repo replicate` orchestrators (spec 05 §1): create / remove / refresh a
 * managed read-replica set. The pure/composable layer (render, datastore-plane
 * provisioning, state CRUD) lives in repo-replicate.ts; this module sequences
 * it against a cluster: resolve the target (control node, datastore, member
 * nodes), provision the fork datastores, apply the generated overlay through
 * the kube_apply bridge verb, and record the set as managed state (R2-F17).
 *
 * REFRESH is rolling, one replica at a time (N-1 keep serving): a fresh
 * snapshot, then per replica strip its node label (the scheduling gate — see
 * refreshReplicaSet), bounce the ordinal pod, discard + re-fork + re-attach its
 * datastore under the unchanged PV path, and re-stamp the label so kubelet
 * remounts and the readiness probe re-admits it. The old snapshot is deleted
 * once every replica clones from the new one.
 *
 * ALL of it keys off the REPO REF: one managed replica set per repo (spec §4.4),
 * so the set name, its snapshot and its fork tags are all DERIVED from the repo
 * rather than named independently.
 */

import { getCluster } from '../config/config-cluster-ops.js';
import { configService } from '../config/config-resources.js';
import { outputService } from '../core/output.js';
import { controlDatastoreMount } from './cluster-kube.js';
import { resolveExecutionTarget } from './cluster-target.js';
import {
  discardReplicaDatastores,
  dispatch,
  forgetReplicaSet,
  getReplicaSet,
  provisionOneReplica,
  provisionReplicaDatastores,
  type ReplicaNode,
  recordReplicaSet,
  renderReplicaSet,
  replicaSetNameFor,
  replicaSnapshotName,
} from './repo-replicate.js';

const NAMED_DS_BASE = '/mnt/rediacc-ds';
/** Conventional data-volume name repos declare (spec 05 templates). */
const DEFAULT_PVC_NAME = 'data';
const DETACH_RETRIES = 5;
const DETACH_RETRY_MS = 2000;

// Test seams (mirror cluster-kube's __setHealthGateDelay/Clock).
let delayFn: (ms: number) => Promise<void> = (ms) => new Promise((r) => setTimeout(r, ms));
let clockFn: () => number = () => Date.now();
export function __setReplicateDelay(fn: (ms: number) => Promise<void>): void {
  delayFn = fn;
}
export function __setReplicateClock(fn: () => number): void {
  clockFn = fn;
}

export interface ReplicateOptions {
  /** The repo's config/renet key (`name` or `name:tag`) — the set's identity. */
  repo: string;
  /** The repo's cluster, derived from its datastore's backref (spec §2.3). */
  cluster: string;
  /** The named datastore the repo lives in, derived from its placement (§2.3). */
  datastore: string;
  replicas: number;
  /** Engine image the replicas run (same engine as the primary). */
  image: string;
  /** Port the engine serves on. */
  port: number;
  /** Declared PVC/volume name the engine mounts as its data dir. Default: data. */
  pvc?: string;
  /** The primary pod's `app` label value (the -rw Service target). Default: repo. */
  primaryApp?: string;
  headless?: boolean;
  refresh?: string;
  debug?: boolean;
}

/**
 * Create a replica set: ONE datastore snapshot -> N constant-time fork-attaches
 * (--writes local) spread across the cluster -> apply the generated overlay
 * (PVs + StatefulSet + -rw/-ro Services) -> record managed state.
 */
export async function replicateRepo(options: ReplicateOptions): Promise<void> {
  const setName = replicaSetNameFor(options.repo);
  if (await getReplicaSet(setName)) {
    throw new Error(
      `Repository "${options.repo}" already has a replica set. Reconcile it by re-running ` +
        `replicate, or remove it first ("rdc repo replicate remove ${options.repo}").`
    );
  }
  if (!Number.isInteger(options.replicas) || options.replicas < 1) {
    throw new Error(`--replicas must be a positive integer, got "${options.replicas}".`);
  }
  const { machineName: control } = await resolveExecutionTarget({ cluster: options.cluster });
  const controlMount = controlDatastoreMount(options.cluster);
  const datastore = options.datastore;
  const nodes = await resolveReplicaNodes(options.cluster);
  const snapshot = replicaSnapshotName(setName);

  // The repo's STORAGE identity (#93): the folder on the datastore — and on
  // every byte-clone fork — is `repos/<guid>` (#83), so the datastore-plane
  // verbs and the generated PV paths speak GUID while every k8s object keeps
  // the name. A cluster repo without a config record cannot be replicated: the
  // GUID is the only address its storage answers to.
  const repoGuid = (await configService.getRepository(options.repo))?.repositoryGuid;
  if (!repoGuid) {
    throw new Error(
      `Repository "${options.repo}" has no repositoryGuid in this config — ` +
        `replicate needs the repo's storage identity (create it with "rdc repo create").`
    );
  }

  outputService.info(
    `Replicating "${options.repo}" (${datastore}): snapshot + ${options.replicas} fork-attach(es) across ${nodes.length} node(s)...`
  );
  const { placements, forks } = await provisionReplicaDatastores({
    repo: options.repo,
    repoGuid,
    setName,
    datastore,
    snapshot,
    replicas: options.replicas,
    nodes,
    controlMachine: control,
    controlMount,
    debug: options.debug,
  });

  const manifest = renderReplicaSet({
    repo: options.repo,
    repoGuid,
    setName,
    datastore,
    primaryApp: options.primaryApp ?? options.repo,
    image: options.image,
    port: options.port,
    pvc: options.pvc ?? DEFAULT_PVC_NAME,
    headless: options.headless ?? false,
    replicas: placements,
  });
  await dispatch(
    'kube_apply',
    control,
    {
      mount_path: controlMount,
      namespace: options.repo,
      manifest,
      name: `replicate-${setName}.yaml`,
      cluster: options.cluster,
      datastore: `${NAMED_DS_BASE}/${datastore}`,
    },
    options.debug
  );

  await recordReplicaSet(setName, {
    repo: options.repo,
    repoGuid,
    datastore,
    cluster: options.cluster,
    replicas: forks,
    headless: options.headless ? true : undefined,
    refresh: options.refresh,
    snapshot,
    createdAt: new Date(clockFn()).toISOString(),
  });
  outputService.success(
    `Replica set "${setName}" created: ${options.replicas} point-in-time read replica(s). ` +
      `Reads: ${options.repo}-ro, writes: ${options.repo}-rw. Replicas are point-in-time ` +
      `copies (no read-your-writes); refresh with "rdc repo replicate refresh ${options.repo}".`
  );
}

/**
 * Remove a repo's replica set: delete the label-scoped overlay, strip the fork
 * node labels, discard the fork datastores, drop the snapshot, forget the state.
 * Every infra step is best-effort (warn + continue) so remove converges even
 * when the cluster is partially gone; state is forgotten last. Removing a repo
 * that has no set is a no-op (§5.4: converge-to-absent).
 */
export async function removeReplicaSet(repoKey: string, debug?: boolean): Promise<void> {
  const setName = replicaSetNameFor(repoKey);
  const set = await getReplicaSet(setName);
  if (!set) {
    outputService.success(`Repository "${repoKey}" has no replica set; nothing to remove.`);
    return;
  }
  const { machineName: control } = await resolveExecutionTarget({ cluster: set.cluster });
  const controlMount = controlDatastoreMount(set.cluster);

  await tryStep(
    'kube_delete',
    control,
    { mount_path: controlMount, namespace: set.repo, replica_set: setName },
    debug
  );
  for (const r of set.replicas) {
    await tryStep(
      'kube_node_label',
      control,
      {
        mount_path: controlMount,
        node_ip: await nodeIp(r.node),
        datastore: r.fork.replace(':', '-'),
        remove: true,
      },
      debug
    );
  }
  await discardReplicaDatastores(set, debug);
  await tryStep(
    'datastore_snapshot_delete',
    control,
    { name: set.datastore, snapshot: set.snapshot ?? replicaSnapshotName(setName) },
    debug
  );
  await forgetReplicaSet(setName);
  outputService.success(`Replica set "${setName}" removed.`);
}

/**
 * Rolling refresh (spec 05 §1): fresh snapshot, then ONE replica at a time —
 * hold the replica down, discard + re-fork + re-attach its datastore under the
 * same tag (so the PV path never changes), and let it back in. Readiness
 * auto-ejects the bouncing replica from -ro; N-1 keep serving.
 *
 * ★ EVICT-AND-HOLD (bug #41). Deleting the ordinal pod first does NOT work: the
 * StatefulSet recreates it within a second, kubelet re-mounts the OLD fork at
 * the unchanged PV path, and the discard-detach then loses to a busy mount
 * forever. The hold is the node label itself — a replica's PV pins via
 * nodeAffinity to `rediacc.io/ds-<datastore>-<tag>`, so STRIPPING that label
 * before the bounce leaves the recreated pod unschedulable (volume node affinity
 * conflict) and it never re-mounts the old fork. It stays Pending until
 * provisionOneReplica re-stamps the label at the end of the swap, at which point
 * it schedules onto the NEW fork. Stripping the label does not disturb the
 * RUNNING pod (kubelet does not re-evaluate node affinity mid-flight), so the
 * replica keeps serving right up to its own bounce. detachWithRetry stays as the
 * belt for kubelet's unmount lag, but it now converges instead of racing.
 */
export async function refreshReplicaSet(repoKey: string, debug?: boolean): Promise<void> {
  const setName = replicaSetNameFor(repoKey);
  const set = await getReplicaSet(setName);
  if (!set) {
    throw new Error(
      `Repository "${repoKey}" has no replica set. See "rdc repo replicate status ${repoKey}".`
    );
  }
  const { machineName: control } = await resolveExecutionTarget({ cluster: set.cluster });
  const controlMount = controlDatastoreMount(set.cluster);
  const oldSnapshot = set.snapshot ?? replicaSnapshotName(setName);
  const snapshot = replicaSnapshotName(setName, String(clockFn()));

  await dispatch('datastore_snapshot_create', control, { name: set.datastore, snapshot }, debug);
  const one = {
    // Storage identity (#93); pre-guid recorded sets fall back to the name.
    repoGuid: set.repoGuid ?? set.repo,
    setName,
    datastore: set.datastore,
    snapshot,
    controlMachine: control,
    controlMount,
    debug,
  };
  for (const r of [...set.replicas].sort((a, b) => a.index - b.index)) {
    outputService.info(`  refresh: replica ${r.index}/${set.replicas.length} on ${r.node}...`);
    // 1. Close the scheduling gate BEFORE the bounce (see the evict-and-hold note).
    await dispatch(
      'kube_node_label',
      control,
      {
        mount_path: controlMount,
        node_ip: await nodeIp(r.node),
        datastore: r.fork.replace(':', '-'),
        remove: true,
      },
      debug
    );
    // 2. Bounce the ordinal pod. It cannot come back: no node satisfies its PV.
    await dispatch(
      'kube_delete',
      control,
      {
        mount_path: controlMount,
        namespace: set.repo,
        replica_set: setName,
        pod_ordinal: r.index - 1,
      },
      debug
    );
    // 3. The mount is nobody's now; discard and re-fork under the same tag.
    //    Close the per-volume LUKS images first (bug #49's mirror): provisioning
    //    opened them, and a fork holding a live LUKS mapping plus its loop device
    //    is BUSY, so the discard below would burn its retries and then throw.
    //    Best-effort — a replica with nothing open is a no-op, and the retrying
    //    detach remains the real guard.
    await tryStep(
      'datastore_volumes_close',
      r.node,
      { name: r.fork, repo: set.repoGuid ?? set.repo },
      debug
    );
    await detachWithRetry(r.fork, r.node, debug);
    // 4. provisionOneReplica re-stamps the label last, which re-opens the gate.
    await provisionOneReplica(one, r.index, { machine: r.node, ip: await nodeIp(r.node) });
  }
  await tryStep(
    'datastore_snapshot_delete',
    control,
    { name: set.datastore, snapshot: oldSnapshot },
    debug
  );
  await recordReplicaSet(setName, {
    ...set,
    snapshot,
    refreshedAt: new Date(clockFn()).toISOString(),
  });
  outputService.success(
    `Replica set "${setName}" refreshed: all ${set.replicas.length} replica(s) now serve the new point-in-time snapshot.`
  );
}

/** Retry a discard-detach while the terminating pod still holds the mount. */
async function detachWithRetry(fork: string, node: string, debug?: boolean): Promise<void> {
  for (let attempt = 1; ; attempt++) {
    try {
      await dispatch('datastore_detach', node, { name: fork, discard: true }, debug);
      return;
    } catch (err) {
      if (attempt >= DETACH_RETRIES) throw err;
      outputService.warn(
        `  refresh: detach ${fork} busy on ${node} (attempt ${attempt}/${DETACH_RETRIES}), retrying...`
      );
      await delayFn(DETACH_RETRY_MS);
    }
  }
}

/** Best-effort teardown step: warn and continue instead of aborting remove. */
async function tryStep(
  functionName: string,
  machineName: string,
  params: Record<string, unknown>,
  debug?: boolean
): Promise<void> {
  try {
    await dispatch(functionName, machineName, params, debug);
  } catch (err) {
    outputService.warn(`  remove: ${functionName} on ${machineName} failed (continuing): ${err}`);
  }
}

/** The cluster's k8s-capable members (replica hosts), in pool/index order. */
async function resolveReplicaNodes(clusterName: string): Promise<ReplicaNode[]> {
  const cluster = await getCluster(clusterName);
  const nodes: ReplicaNode[] = [];
  for (const pool of cluster.pools) {
    if (pool.role !== 'k8s-server' && pool.role !== 'k8s-agent' && pool.role !== 'hyperconverged') {
      continue;
    }
    for (let i = 1; i <= pool.count; i++) {
      const name = `${clusterName}-${pool.name}-${i}`;
      const machine = await configService.getLocalMachine(name);
      nodes.push({ machine: name, ip: machine.ip });
    }
  }
  return nodes;
}

/** A replica node's private IP (kube_node_label resolves nodes by InternalIP). */
async function nodeIp(machineName: string): Promise<string> {
  return (await configService.getLocalMachine(machineName)).ip;
}
