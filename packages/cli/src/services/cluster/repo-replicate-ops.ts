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

import { DEFAULTS } from '@rediacc/shared/config';
import type { ReplicaSet } from '@rediacc/shared/config-schema';
import { getCluster } from '../config/config-cluster-ops.js';
import { configService } from '../config/config-resources.js';
import { outputService } from '../core/output.js';
import { getExecutor } from '../executor/executor-factory.js';
import { parseCapturedJson } from '../executor/local-executor.js';
import { controlDatastoreMount } from './cluster-kube.js';
import { resolveExecutionTarget } from './cluster-target.js';
import {
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
      `Repository "${options.repo}" has no repositoryGuid in this config. ` +
        `Replicate needs the repo's storage identity (create it with "rdc repo create").`
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
 * Remove a repo's replica set (spec §5.4: converge-to-absent). The teardown is
 * ORDERED and its holder-releasing steps are HARD (bug #95, found live by the B1
 * window):
 *
 *   1. delete the whole overlay (StatefulSet + Services + PVC + PV) by set label
 *      so the replica pods terminate and release their fork mounts,
 *   2. THEN discard each fork,
 *   3. strip the node labels,
 *   4. drop the snapshot,
 *   5. VERIFY no fork of the set survives, and only THEN forget the state.
 *
 * Genuinely idempotent cleanups (LUKS close, label strip, snapshot delete) still
 * warn-and-continue, but they are COUNTED and reported; any step whose failure
 * would strand a holder — the fork discard, and the final verify — PROPAGATES.
 * State is forgotten LAST, and never while a survivor remains.
 *
 * Bug #95 was a FALSE SUCCESS: the old teardown deleted the overlay and detached
 * the forks with `tryStep` (warn-and-continue on EVERY failure), then forgot
 * state unconditionally. In the live run the replica pod still held the fork
 * mount (remove never waited for pod termination), the discard-detach lost the
 * busy race, `tryStep` swallowed it, and remove reported "removed" while the
 * StatefulSet, both Services, both forks, both nodes' dm devices and a node label
 * all stayed live — and `replicate status` then said the set was gone. Removing a
 * repo that has no set stays a no-op.
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
  const skipped: string[] = [];

  // 1. Delete the whole overlay by set label. HARD, and captured: `kubectl
  //    delete` default-waits for the pods to terminate, so a delete that fires is
  //    ALSO the pod-termination wait that lets the fork discard win. Capture the
  //    output so a later failure can name whether the delete removed anything —
  //    bug #95 mechanism (b) was a silent no-op that left the StatefulSet (and so
  //    the pods) running.
  const deleteLog = await captureStep(
    'kube_delete',
    control,
    { mount_path: controlMount, namespace: set.repo, replica_set: setName },
    debug
  );

  // 2. Discard each fork. HARD: a fork left attached IS the bug #95 survivor (dm
  //    cow/pool + the running replica holding it). On final failure this PROPAGATES
  //    (naming the survivor + surfacing the delete log), never reaching the forget.
  await discardForks(set, deleteLog, repoKey, skipped, debug);

  // 3. Strip the fork node labels (best-effort: a stray label holds nothing).
  for (const r of set.replicas) {
    try {
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
    } catch (err) {
      skipped.push(`kube_node_label ${r.fork} on ${r.node}: ${err}`);
    }
  }

  // 4. Drop the set's snapshot (best-effort: a leftover snapshot reclaims free).
  try {
    await dispatch(
      'datastore_snapshot_delete',
      control,
      { name: set.datastore, snapshot: set.snapshot ?? replicaSnapshotName(setName) },
      debug
    );
  } catch (err) {
    skipped.push(`datastore_snapshot_delete on ${control}: ${err}`);
  }

  // 5. VERIFY before forgetting (the #43 verify-then-report principle): confirm
  //    no fork of the set is still attached on its node. datastore_detach
  //    --discard removes the fork datastore, so a fork still enumerated by
  //    datastore_list means the discard SUCCEEDED-but-DID-NOTHING (the false
  //    success class). On any survivor, fail non-zero with the manual repair and
  //    leave state intact so the operator can finish and re-run.
  const survivors = await findSurvivingForks(set, debug);
  if (survivors.length > 0) {
    throw new Error(
      removeFailure(setName, repoKey, `forks still attached: ${survivors.join('; ')}`, deleteLog)
    );
  }

  // 6. Forget state LAST, only after verified teardown.
  await forgetReplicaSet(setName);
  if (skipped.length > 0) {
    outputService.warn(
      `  remove: ${skipped.length} best-effort cleanup step(s) failed (set torn down anyway): ${skipped.join('; ')}`
    );
  }
  outputService.success(`Replica set "${setName}" removed.`);
}

/**
 * Discard every fork of the set (bug #95 step 2): per fork, close its per-volume
 * LUKS images (best-effort mirror of provisioning, bug #49 — a fork holding a
 * live LUKS mapping is BUSY) then detach --discard, retrying through kubelet's
 * unmount lag exactly like the refresh path. The detach is HARD: on final failure
 * it THROWS (naming the fork + surfacing the delete log) so remove exits non-zero
 * and never reaches the state-forget.
 */
async function discardForks(
  set: ReplicaSet,
  deleteLog: string,
  repoKey: string,
  skipped: string[],
  debug?: boolean
): Promise<void> {
  for (const r of set.replicas) {
    try {
      await dispatch(
        'datastore_volumes_close',
        r.node,
        { name: r.fork, repo: set.repoGuid ?? set.repo },
        debug
      );
    } catch (err) {
      skipped.push(`datastore_volumes_close ${r.fork} on ${r.node}: ${err}`);
    }
    try {
      await detachWithRetry(r.fork, r.node, debug);
    } catch (err) {
      throw new Error(
        removeFailure(
          replicaSetNameFor(repoKey),
          repoKey,
          `fork ${r.fork} could not be discarded on ${r.node}: ${err}`,
          deleteLog
        )
      );
    }
  }
}

/**
 * The non-zero remove message: name the survivor, surface the captured
 * overlay-delete log (bug #95 mechanism b — so the next run names the cause
 * instead of guessing), and spell out the manual repair. State is preserved on
 * this path, so the operator can finish the teardown and re-run.
 */
function removeFailure(
  setName: string,
  repoKey: string,
  survivor: string,
  deleteLog: string
): string {
  const log = deleteLog.trim();
  return (
    `Replica set "${setName}" NOT removed: ${survivor}. State was PRESERVED. ` +
    `Overlay delete reported: ${log.length > 0 ? log : '(no output, so it may have deleted nothing)'}. ` +
    `Terminate any surviving replica pods and detach the fork(s) with --discard on their nodes, ` +
    `then re-run "rdc repo replicate remove ${repoKey}".`
  );
}

/**
 * Dispatch a bridge verb capturing its stdout; throw on non-success. Used for the
 * overlay delete (whose output must be surfaced on failure) and the survivor
 * probe (whose output is the datastore listing).
 */
async function captureStep(
  functionName: string,
  machineName: string,
  params: Record<string, unknown>,
  debug?: boolean
): Promise<string> {
  const res = await getExecutor().execute({
    functionName,
    machineName,
    params,
    debug,
    captureOutput: true,
  });
  if (!res.success) {
    throw new Error(
      `Replica teardown step "${functionName}" failed on ${machineName}: ${res.error ?? DEFAULTS.CLOUD.UNKNOWN_ERROR}`
    );
  }
  return res.stdout ?? '';
}

/**
 * The set's forks still attached on their nodes after the discard — the bug #95
 * survivor probe. `datastore_detach --discard` removes the fork datastore, so a
 * fork still enumerated by `datastore_list` on its node means the discard did
 * nothing; a node we cannot query is itself unverifiable and counts as a survivor
 * (fail loud rather than forget state blind).
 */
async function findSurvivingForks(set: ReplicaSet, debug?: boolean): Promise<string[]> {
  const survivors: string[] = [];
  for (const r of set.replicas) {
    const res = await getExecutor().execute({
      functionName: 'datastore_list',
      machineName: r.node,
      params: {},
      debug,
      captureOutput: true,
    });
    if (!res.success) {
      survivors.push(
        `${r.fork} on ${r.node} (unverifiable: ${res.error ?? DEFAULTS.CLOUD.UNKNOWN_ERROR})`
      );
      continue;
    }
    let records: { name?: string }[];
    try {
      records = parseCapturedJson<{ name?: string }[]>(res.stdout);
    } catch (err) {
      survivors.push(`${r.fork} on ${r.node} (unverifiable: ${err})`);
      continue;
    }
    if (records.some((d) => d.name === r.fork)) survivors.push(`${r.fork} on ${r.node}`);
  }
  return survivors;
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
