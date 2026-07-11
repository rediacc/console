/**
 * `rdc repo replicate` orchestrators (spec 05 §1): create / remove / refresh a
 * managed read-replica set. The pure/composable layer (render, datastore-plane
 * provisioning, state CRUD) lives in repo-replicate.ts; this module sequences
 * it against a cluster: resolve the target (control node, datastore, member
 * nodes), provision the fork datastores, apply the generated overlay through
 * the kube_apply bridge verb, and record the set as managed state (R2-F17).
 *
 * REFRESH is rolling, one replica at a time (N-1 keep serving): a fresh
 * snapshot, then per replica bounce the ordinal pod (kube_delete pod_ordinal),
 * discard + re-fork + re-attach its datastore under the unchanged PV path, and
 * let kubelet remount + the readiness probe re-admit it. The old snapshot is
 * deleted once every replica clones from the new one.
 */

import { DEFAULTS } from '@rediacc/shared/config';
import { getCluster } from '../config/config-cluster-ops.js';
import { configService } from '../config/config-resources.js';
import { outputService } from '../core/output.js';
import { localExecutorService, parseCapturedJson } from '../executor/local-executor.js';
import { controlDatastore, controlDatastoreMount } from './cluster-kube.js';
import {
  discardReplicaDatastores,
  dispatch,
  forgetReplicaSet,
  getReplicaSet,
  provisionOneReplica,
  provisionReplicaDatastores,
  recordReplicaSet,
  renderReplicaSet,
  type ReplicaNode,
  replicaSnapshotName,
} from './repo-replicate.js';
import { resolveExecutionTarget } from './cluster-target.js';

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
  repo: string;
  cluster: string;
  replicas: number;
  /** Data datastore holding the repo. Default: the cluster's single data datastore. */
  datastore?: string;
  /** Replica-set name. Default: `<repo>-replicas`. */
  set?: string;
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
  const setName = options.set ?? `${options.repo}-replicas`;
  if (await getReplicaSet(setName)) {
    throw new Error(
      `Replica set "${setName}" already exists. Remove it first ("rdc repo replicate remove ` +
        `--name ${setName}") or pick another --set name.`
    );
  }
  if (!Number.isInteger(options.replicas) || options.replicas < 1) {
    throw new Error(`--replicas must be a positive integer, got "${options.replicas}".`);
  }
  const { machineName: control } = await resolveExecutionTarget({ cluster: options.cluster });
  const controlMount = controlDatastoreMount(options.cluster);
  const datastore =
    options.datastore ?? (await inferClusterDatastore(control, options.cluster, options.debug));
  const nodes = await resolveReplicaNodes(options.cluster);
  const snapshot = replicaSnapshotName(setName);

  outputService.info(
    `Replicating "${options.repo}" (${datastore}): snapshot + ${options.replicas} fork-attach(es) across ${nodes.length} node(s)...`
  );
  const { placements, forks } = await provisionReplicaDatastores({
    repo: options.repo,
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
      `copies (no read-your-writes); refresh with "rdc repo replicate refresh --name ${setName}".`
  );
}

/**
 * Remove a replica set: delete the label-scoped overlay, strip the fork node
 * labels, discard the fork datastores, drop the snapshot, forget the state.
 * Every infra step is best-effort (warn + continue) so remove converges even
 * when the cluster is partially gone; state is forgotten last.
 */
export async function removeReplicaSet(setName: string, debug?: boolean): Promise<void> {
  const set = await getReplicaSet(setName);
  if (!set) {
    throw new Error(`Replica set "${setName}" not found. See "rdc repo replicate status".`);
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
 * bounce its ordinal pod, discard + re-fork + re-attach its datastore under
 * the same tag (so the PV path never changes), re-stamp the node label.
 * Readiness auto-ejects the bouncing replica from -ro; N-1 keep serving.
 */
export async function refreshReplicaSet(setName: string, debug?: boolean): Promise<void> {
  const set = await getReplicaSet(setName);
  if (!set) {
    throw new Error(`Replica set "${setName}" not found. See "rdc repo replicate status".`);
  }
  const { machineName: control } = await resolveExecutionTarget({ cluster: set.cluster });
  const controlMount = controlDatastoreMount(set.cluster);
  const oldSnapshot = set.snapshot ?? replicaSnapshotName(setName);
  const snapshot = replicaSnapshotName(setName, String(clockFn()));

  await dispatch('datastore_snapshot_create', control, { name: set.datastore, snapshot }, debug);
  const one = {
    setName,
    datastore: set.datastore,
    snapshot,
    controlMachine: control,
    controlMount,
    debug,
  };
  for (const r of [...set.replicas].sort((a, b) => a.index - b.index)) {
    outputService.info(`  refresh: replica ${r.index}/${set.replicas.length} on ${r.node}...`);
    // Bounce the ordinal pod; the StatefulSet recreates it, and it blocks in
    // ContainerCreating until the re-forked datastore is attached below.
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
    await detachWithRetry(r.fork, r.node, debug);
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

/** One datastore record from `renet datastore list --json` (fields we filter on). */
interface DatastoreRecord {
  name: string;
  cluster?: string;
  fork?: unknown;
  implicit?: boolean;
}

/**
 * Infer the repo's datastore when --datastore is omitted: the cluster's single
 * cluster-labeled data datastore (excluding the control datastore and forks).
 * Ambiguity is an error naming the candidates — never a guess.
 */
async function inferClusterDatastore(
  control: string,
  cluster: string,
  debug?: boolean
): Promise<string> {
  const res = await localExecutorService.execute({
    functionName: 'datastore_list',
    machineName: control,
    params: {},
    debug,
    captureOutput: true,
  });
  if (!res.success) {
    throw new Error(
      `datastore_list failed on ${control}: ${res.error ?? DEFAULTS.CLOUD.UNKNOWN_ERROR}`
    );
  }
  // datastore_list shells out; captured stdout is `[datastore_list] [...]` — strip
  // the bridge relay prefix before parsing (finding #10 / parseCapturedJson).
  const records = parseCapturedJson<DatastoreRecord[]>(res.stdout);
  const candidates = records
    .filter(
      (r) => !r.implicit && !r.fork && r.cluster === cluster && r.name !== controlDatastore(cluster)
    )
    .map((r) => r.name);
  if (candidates.length === 1) return candidates[0];
  throw new Error(
    candidates.length === 0
      ? `Cluster "${cluster}" has no data datastore to replicate from; pass --datastore.`
      : `Cluster "${cluster}" has ${candidates.length} data datastores (${candidates.join(', ')}); pass --datastore.`
  );
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
