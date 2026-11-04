/**
 * `rdc repo replicate` orchestrators (spec 05 §1): create / remove / refresh a
 * managed read-replica set, as a chain of machine jobs (PLAN-detached-jobs).
 *
 * A licence cannot be issued before its fork exists, because the fork mints its
 * datastore id and each issuance claims a slot, so the chain has to come back to
 * the client between the fork and the volume open. Each verb is therefore one
 * first job, then a ticket step (`replicateTail`, `refreshTail`, `removeTail`)
 * that starts the further jobs. Under `--background` the verb returns at the
 * first job, and `rdc job wait` or the interactive notice runs the step.
 *
 * Everything converges, so a client that goes away leaves nothing a rerun cannot
 * finish. The set is recorded as `phase: placing` before its first job, with its
 * planned replicas, which makes it both resumable and removable. The renet
 * compounds reuse what exists. An installed licence for the fork's id ends a
 * retried issuance before it spends a slot. A refresh records the snapshot it is
 * rolling to, so a rerun resumes on that snapshot instead of minting another.
 *
 * ALL of it keys off the REPO REF: one managed replica set per repo (spec §4.4),
 * so the set name, its snapshot and its fork tags are all DERIVED from the repo
 * rather than named independently.
 */

import type { ReplicaSet } from '@rediacc/shared/config-schema';
import {
  assertMachineSlotsAvailable,
  partialPlacementGuidance,
} from '../account/license-preflight.js';
import { getCluster } from '../config/config-cluster-ops.js';
import { configService } from '../config/config-resources.js';
import { outputService } from '../core/output.js';
import { parseCapturedJson } from '../executor/local-executor.js';
import { bindStepHandler, type PlannedStep, planStep } from '../jobs/steps.js';
import { jsonParam } from '../jobs/steps-support.js';
import {
  ClusterPhasePendingError,
  type ClusterPhaseResult,
  runClusterPhase,
} from './cluster-job.js';
import { controlDatastoreMount } from './cluster-kube.js';
import { resolveExecutionTarget } from './cluster-target.js';
import {
  ensureForkLicense,
  forgetReplicaSet,
  getReplicaSet,
  planReplicas,
  type ReplicaNode,
  recordReplicaSet,
  renderReplicaSet,
  replicaPlacement,
  replicaSetNameFor,
  replicaSnapshotName,
} from './repo-replicate.js';

const NAMED_DS_BASE = '/mnt/rediacc-ds';
/** Conventional data-volume name repos declare (spec 05 templates). */
const DEFAULT_PVC_NAME = 'data';
const VERB_CREATE = 'repo replicate';
const VERB_REFRESH = 'repo replicate refresh';
const VERB_REMOVE = 'repo replicate remove';
const STEP_LABEL = 'Replica step';
const FORK_WRITES = 'local';

// Test seam (mirrors cluster-kube's __setHealthGateClock).
let clockFn: () => number = () => Date.now();
export function __setReplicateClock(fn: () => number): void {
  clockFn = fn;
}

export interface ReplicateOptions {
  /** The repo's config/renet key (`name` or `name:tag`), the set's identity. */
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

type Replica = ReplicaSet['replicas'][number];

interface PhaseOptions {
  debug?: boolean;
  capture?: boolean;
  steps?: PlannedStep[];
}

function phase(
  verb: string,
  functionName: string,
  machineName: string,
  params: Record<string, unknown>,
  options: PhaseOptions = {}
): Promise<ClusterPhaseResult> {
  return runClusterPhase(functionName, machineName, params, {
    label: STEP_LABEL,
    verb,
    ...options,
  });
}

/** One tag of `replica_fork`'s answer (renet pkg/datastore/replica.go). */
interface ForkEntry {
  tag: string;
  name: string;
  state: 'forked' | 'reused' | 'placed';
  record?: unknown;
}

function parseForkEntries(output: string | undefined): ForkEntry[] | undefined {
  if (!output) return undefined;
  try {
    const parsed = parseCapturedJson<ForkEntry[]>(output);
    return Array.isArray(parsed) ? parsed : undefined;
  } catch {
    return undefined;
  }
}

function forkTag(fork: string): string {
  return fork.slice(fork.indexOf(':') + 1);
}

function forkLabel(fork: string): string {
  return fork.replace(':', '-');
}

function sortedReplicas(set: ReplicaSet): Replica[] {
  return [...set.replicas].sort((a, b) => a.index - b.index);
}

/** A replica's private IP (kube_node_label resolves nodes by InternalIP). */
async function nodeIp(machineName: string): Promise<string> {
  return (await configService.getLocalMachine(machineName)).ip;
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

// --- one replica's way up, shared by create and refresh ------------------------

interface BringUp {
  verb: string;
  repo: string;
  repoGuid: string;
  control: string;
  debug?: boolean;
}

/**
 * Attach a fork on its node, license it, and open its volumes. The fork record
 * lives on control until the publish, so an off-control node gets it ferried.
 *
 * The order is load-bearing. renet licence-checks datastore_volumes_open against
 * the fork's own datastore id, so the licence comes first; and the open has to
 * precede the node label the publish stamps, because the label is the scheduling
 * gate and a pod must never reach a volume that is not mounted (bug #49: such a
 * replica comes up healthy, Ready and EMPTY).
 *
 * By GUID, never by name (#93): the repo folder on the fork is `repos/<guid>`.
 */
async function bringUpReplica(input: BringUp, replica: Replica, entry?: ForkEntry): Promise<void> {
  const params: Record<string, unknown> = { name: replica.fork, writes: FORK_WRITES };
  if (replica.node !== input.control && entry?.record) {
    params.record_b64 = Buffer.from(JSON.stringify(entry.record)).toString('base64');
  }
  const attached = await phase(input.verb, 'replica_attach', replica.node, params, {
    debug: input.debug,
    capture: true,
  });
  const record = parseCapturedJson<{ datastoreId?: unknown }>(attached.result.stdout);
  if (typeof record.datastoreId !== 'string' || record.datastoreId === '') {
    throw new Error(
      `Cannot license replica fork "${replica.fork}" on ${replica.node}: its datastore registry reports no datastore id for it.`
    );
  }
  await ensureForkLicense(
    { repo: input.repo, repoGuid: input.repoGuid },
    replica.fork,
    replica.node,
    record.datastoreId
  );
  await phase(
    input.verb,
    'datastore_volumes_open',
    replica.node,
    { name: replica.fork, repo: input.repoGuid },
    { debug: input.debug }
  );
}

// --- create --------------------------------------------------------------------

/** What `replicateTail` needs and the set record does not hold. No secret: names, an image and a port. */
interface CreatePlan {
  setName: string;
  image: string;
  port: number;
  pvc: string;
  primaryApp: string;
  headless: boolean;
  control: string;
  controlMount: string;
  debug?: boolean;
}

function placementFailure(error: unknown, set: ReplicaSet, placed: string[]): unknown {
  if (error instanceof ClusterPhasePendingError) return error;
  const machines = [...new Set(set.replicas.map((r) => r.node))];
  return new Error(
    `${error instanceof Error ? error.message : String(error)}\n\n${partialPlacementGuidance({
      placed,
      remaining: machines.filter((m) => !placed.includes(m)),
      command: `rdc repo replicate ${set.repo} --replicas ${set.replicas.length}`,
    })}`,
    { cause: error }
  );
}

function notFinished(setName: string, repo: string, what: string): Error {
  return new Error(
    `Replica set "${setName}" is not finished: ${what}. ` +
      `Re-run the command to resume it, or remove it with "rdc repo replicate remove ${repo}".`
  );
}

/**
 * Create a replica set: ONE datastore snapshot and N constant-time forks, then
 * per replica an attach (--writes local), a licence and the volume open, then the
 * node labels and the generated overlay (PVs + StatefulSet + -rw/-ro Services).
 * Re-running a set still `placing` resumes it.
 */
export async function replicateRepo(options: ReplicateOptions): Promise<void> {
  const setName = replicaSetNameFor(options.repo);
  const existing = await getReplicaSet(setName);
  assertCreatable(options, setName, existing);
  const { machineName: control } = await resolveExecutionTarget({ cluster: options.cluster });
  const nodes = await resolveReplicaNodes(options.cluster);
  if (nodes.length === 0) {
    throw new Error(
      `Cannot replicate "${options.repo}": the cluster has no nodes to host replicas.`
    );
  }
  const set = await placingRecord(options, setName, nodes, existing);
  // Replicas land round-robin, so the machines this touches are the distinct nodes the rotation reaches, fewer than `replicas` when replicas outnumber nodes. Asked before anything is recorded or started, because everything after it is placement.
  await assertMachineSlotsAvailable({
    machineCount: new Set(set.replicas.map((r) => r.node)).size,
  });
  await recordReplicaSet(setName, set);

  outputService.info(
    `Replicating "${options.repo}" (${set.datastore}): snapshot + ${options.replicas} fork-attach(es) across ${nodes.length} node(s)...`
  );
  const plan: CreatePlan = {
    setName,
    image: options.image,
    port: options.port,
    pvc: options.pvc ?? DEFAULT_PVC_NAME,
    primaryApp: options.primaryApp ?? options.repo,
    headless: options.headless ?? false,
    control,
    controlMount: controlDatastoreMount(options.cluster),
    ...(options.debug ? { debug: true } : {}),
  };
  let forked: ClusterPhaseResult;
  try {
    forked = await phase(VERB_CREATE, 'replica_fork', control, forkParams(set), {
      debug: options.debug,
      capture: true,
      steps: [planStep('replicateTail', { plan: JSON.stringify(plan) })],
    });
  } catch (error) {
    throw placementFailure(error, set, []);
  }
  if (!forked.pending && forked.unfinished.length > 0) {
    throw notFinished(setName, options.repo, 'the placement did not complete');
  }
}

/** One set per repo, and a set still placing resumes only on its own plan. */
function assertCreatable(
  options: ReplicateOptions,
  setName: string,
  existing: ReplicaSet | undefined
): void {
  if (existing && existing.phase !== 'placing') {
    throw new Error(
      `Repository "${options.repo}" already has a replica set. Reconcile it by re-running ` +
        `replicate, or remove it first ("rdc repo replicate remove ${options.repo}").`
    );
  }
  if (!Number.isInteger(options.replicas) || options.replicas < 1) {
    throw new Error(`--replicas must be a positive integer, got "${options.replicas}".`);
  }
  if (existing && existing.replicas.length !== options.replicas) {
    throw new Error(
      `Replica set "${setName}" is being placed with ${existing.replicas.length} replica(s), not ${options.replicas}. ` +
        `Resume it with --replicas ${existing.replicas.length}, or remove it first ("rdc repo replicate remove ${options.repo}").`
    );
  }
}

/** The record written before the first job. A rerun keeps the plan it finds. */
async function placingRecord(
  options: ReplicateOptions,
  setName: string,
  nodes: ReplicaNode[],
  existing: ReplicaSet | undefined
): Promise<ReplicaSet> {
  // The repo's STORAGE identity (#93): the folder on the datastore, and on every byte-clone fork, is `repos/<guid>` (#83), so the datastore-plane verbs and the generated PV paths speak GUID while every k8s object keeps the name. A cluster repo without a config record cannot be replicated: the GUID is the only address its storage answers to.
  const repoGuid = (await configService.getRepository(options.repo))?.repositoryGuid;
  if (!repoGuid) {
    throw new Error(
      `Repository "${options.repo}" has no repositoryGuid in this config. ` +
        `Replicate needs the repo's storage identity (create it with "rdc repo create").`
    );
  }
  const datastore = options.datastore;
  return {
    repo: options.repo,
    repoGuid,
    datastore,
    cluster: options.cluster,
    replicas:
      existing?.replicas ?? planReplicas({ setName, datastore, replicas: options.replicas, nodes }),
    headless: options.headless ? true : undefined,
    refresh: options.refresh,
    snapshot: existing?.snapshot ?? replicaSnapshotName(setName),
    createdAt: existing?.createdAt ?? new Date(clockFn()).toISOString(),
    phase: 'placing',
  };
}

function forkParams(set: ReplicaSet): Record<string, unknown> {
  return {
    parent: set.datastore,
    snapshot: set.snapshot,
    tags: set.replicas.map((r) => forkTag(r.fork)).join(','),
  };
}

/** Attach, license and open every replica, then publish. Skipped once the set is no longer placing: a stale retake. */
bindStepHandler('replicateTail', async ({ params, output }) => {
  const plan = jsonParam<CreatePlan>(params, 'plan');
  const set = await getReplicaSet(plan.setName);
  if (set?.phase !== 'placing') return;
  const { debug, control } = plan;
  const placed: string[] = [];
  try {
    // The fork job's answer, or (an observer that could not read its log) the same answer again: the job reuses every fork it already made.
    const entries =
      parseForkEntries(output) ??
      parseForkEntries(
        (
          await phase(VERB_CREATE, 'replica_fork', control, forkParams(set), {
            debug,
            capture: true,
          })
        ).result.stdout
      ) ??
      [];
    const bringUp: BringUp = {
      verb: VERB_CREATE,
      repo: set.repo,
      repoGuid: set.repoGuid ?? set.repo,
      control,
      debug,
    };
    for (const replica of sortedReplicas(set)) {
      await bringUpReplica(
        bringUp,
        replica,
        entries.find((e) => e.name === replica.fork)
      );
      if (!placed.includes(replica.node)) placed.push(replica.node);
    }
  } catch (error) {
    throw placementFailure(error, set, placed);
  }
  const published = await publishSet(plan, set);
  if (published.pending) return;
  if (published.unfinished.length > 0) {
    throw notFinished(plan.setName, set.repo, 'the set record was not written');
  }
  outputService.success(
    `Replica set "${plan.setName}" created: ${set.replicas.length} point-in-time read replica(s). ` +
      `Reads: ${set.repo}-ro, writes: ${set.repo}-rw. Replicas are point-in-time ` +
      `copies (no read-your-writes); refresh with "rdc repo replicate refresh ${set.repo}".`
  );
});

async function publishSet(plan: CreatePlan, set: ReplicaSet): Promise<ClusterPhaseResult> {
  const manifest = renderReplicaSet({
    repo: set.repo,
    repoGuid: set.repoGuid ?? set.repo,
    setName: plan.setName,
    datastore: set.datastore,
    primaryApp: plan.primaryApp,
    image: plan.image,
    port: plan.port,
    pvc: plan.pvc,
    headless: plan.headless,
    replicas: sortedReplicas(set).map((r) => replicaPlacement(set.datastore, r)),
  });
  const labels = await Promise.all(
    set.replicas.map(async (r) => `${forkLabel(r.fork)}@${await nodeIp(r.node)}`)
  );
  const ready: ReplicaSet = { ...set, phase: 'ready' };
  return phase(
    VERB_CREATE,
    'replica_publish',
    plan.control,
    {
      mount_path: plan.controlMount,
      labels: labels.join(','),
      ...forgetParam(set.replicas, plan.control),
      namespace: set.repo,
      manifest,
      name: `replicate-${plan.setName}.yaml`,
      cluster: set.cluster,
      datastore: `${NAMED_DS_BASE}/${set.datastore}`,
    },
    {
      debug: plan.debug,
      steps: [
        planStep('recordReplicaSet', {
          set: plan.setName,
          replicaSet: JSON.stringify(ready),
        }),
      ],
    }
  );
}

/**
 * The control copies of the fork records. A record on a node is the live one, and
 * a later re-fork of the same tag would collide with the leftover (finding #40).
 */
function forgetParam(replicas: Replica[], control: string): { forget?: string } {
  const forget = replicas.filter((r) => r.node !== control).map((r) => r.fork);
  return forget.length > 0 ? { forget: forget.join(',') } : {};
}

// --- remove --------------------------------------------------------------------

interface RemovePlan {
  setName: string;
  repoKey: string;
  debug?: boolean;
}

/**
 * Remove a repo's replica set (spec §5.4: converge-to-absent). The teardown is
 * ORDERED and its holder-releasing steps are HARD (bug #95, found live by the B1
 * window):
 *
 *   1. delete the whole overlay (StatefulSet + Services + PVC + PV) by set label
 *      so the replica pods terminate and release their fork mounts,
 *   2. THEN discard each fork; `replica_discard` fails on a survivor,
 *   3. strip the node labels,
 *   4. drop the snapshot,
 *   5. only THEN forget the state.
 *
 * Genuinely idempotent cleanups (label strip, snapshot delete) warn-and-continue,
 * but they are COUNTED and reported. State is forgotten LAST, and never while a
 * survivor remains. Removing a repo that has no set stays a no-op, and a set still
 * `placing` is removable: it also discards the control copies its forks left.
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
  const plan: RemovePlan = { setName, repoKey, ...(debug ? { debug: true } : {}) };

  // 1. Delete the whole overlay by set label. HARD, and captured: `kubectl delete` default-waits for the pods to terminate, so a delete that fires is ALSO the pod-termination wait that lets the fork discard win. The output reaches a later failure message, because bug #95 mechanism (b) was a silent no-op that left the StatefulSet (and so the pods) running.
  const deleted = await phase(
    VERB_REMOVE,
    'kube_delete',
    control,
    { mount_path: controlMount, namespace: set.repo, replica_set: setName },
    {
      debug,
      capture: true,
      steps: [planStep('removeTail', { plan: JSON.stringify(plan) })],
    }
  );
  if (deleted.pending) return;
  if (deleted.unfinished.length > 0) {
    throw new Error(
      `Replica set "${setName}" NOT removed: the teardown did not finish. State was PRESERVED. ` +
        `Re-run "rdc repo replicate remove ${repoKey}".`
    );
  }
}

/** Machines holding a copy of this replica's fork record, the node first: a set not fully published may leave one on control. */
function discardTargets(set: ReplicaSet, replica: Replica, control: string): string[] {
  const unsettled = set.phase === 'placing' || set.refreshing !== undefined;
  return unsettled && replica.node !== control ? [replica.node, control] : [replica.node];
}

/** The second phase of `repo replicate remove`, once the overlay is gone. */
bindStepHandler('removeTail', async ({ params, output }) => {
  const plan = jsonParam<RemovePlan>(params, 'plan');
  const set = await getReplicaSet(plan.setName);
  if (!set) return;
  const { machineName: control } = await resolveExecutionTarget({ cluster: set.cluster });

  await discardForks(plan, set, control, output ?? '');
  const skipped = [
    ...(await stripForkLabels(plan, set, control)),
    ...(await dropSetSnapshots(plan, set, control)),
  ];

  // 5. Forget state LAST, only after verified teardown.
  await forgetReplicaSet(plan.setName);
  if (skipped.length > 0) {
    outputService.warn(
      `  remove: ${skipped.length} best-effort cleanup step(s) failed (set torn down anyway): ${skipped.join('; ')}`
    );
  }
  outputService.success(`Replica set "${plan.setName}" removed.`);
});

/** 2. Discard each fork. HARD: a fork left attached IS the bug #95 survivor (dm cow/pool + the running replica holding it). On final failure this PROPAGATES (naming the survivor + surfacing the delete log), never reaching the forget. */
async function discardForks(
  plan: RemovePlan,
  set: ReplicaSet,
  control: string,
  deleteLog: string
): Promise<void> {
  for (const r of set.replicas) {
    for (const machine of discardTargets(set, r, control)) {
      try {
        await phase(
          VERB_REMOVE,
          'replica_discard',
          machine,
          { name: r.fork, repo: set.repoGuid ?? set.repo },
          { debug: plan.debug }
        );
      } catch (err) {
        throw new Error(
          removeFailure(
            plan.setName,
            plan.repoKey,
            `fork ${r.fork} could not be discarded on ${machine}: ${err}`,
            deleteLog
          ),
          { cause: err }
        );
      }
    }
  }
}

/** 3. Strip the fork node labels (best-effort: a stray label holds nothing). */
async function stripForkLabels(
  plan: RemovePlan,
  set: ReplicaSet,
  control: string
): Promise<string[]> {
  const skipped: string[] = [];
  for (const r of set.replicas) {
    try {
      await phase(
        VERB_REMOVE,
        'kube_node_label',
        control,
        {
          mount_path: controlDatastoreMount(set.cluster),
          node_ip: await nodeIp(r.node),
          datastore: forkLabel(r.fork),
          remove: true,
        },
        { debug: plan.debug }
      );
    } catch (err) {
      skipped.push(`kube_node_label ${r.fork} on ${r.node}: ${err}`);
    }
  }
  return skipped;
}

/** 4. Drop the set's snapshots (best-effort: a leftover snapshot reclaims free). */
async function dropSetSnapshots(
  plan: RemovePlan,
  set: ReplicaSet,
  control: string
): Promise<string[]> {
  const skipped: string[] = [];
  const snapshots = [set.snapshot ?? replicaSnapshotName(plan.setName), set.refreshing].filter(
    (s): s is string => typeof s === 'string'
  );
  for (const snapshot of snapshots) {
    try {
      await phase(
        VERB_REMOVE,
        'datastore_snapshot_delete',
        control,
        { name: set.datastore, snapshot },
        { debug: plan.debug }
      );
    } catch (err) {
      skipped.push(`datastore_snapshot_delete on ${control}: ${err}`);
    }
  }
  return skipped;
}

/**
 * The non-zero remove message: name the survivor, surface the captured
 * overlay-delete log (bug #95 mechanism b, so the next run names the cause
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

// --- refresh -------------------------------------------------------------------

interface RefreshPlan {
  setName: string;
  snapshot: string;
  control: string;
  controlMount: string;
  debug?: boolean;
}

/**
 * Rolling refresh (spec 05 §1): fresh snapshot, then ONE replica at a time ,
 * hold the replica down, discard + re-fork + re-attach its datastore under the
 * same tag (so the PV path never changes), and let it back in. Readiness
 * auto-ejects the bouncing replica from -ro; N-1 keep serving.
 *
 * ★ EVICT-AND-HOLD (bug #41). Deleting the ordinal pod first does NOT work: the
 * StatefulSet recreates it within a second, kubelet re-mounts the OLD fork at
 * the unchanged PV path, and the discard-detach then loses to a busy mount
 * forever. The hold is the node label itself, a replica's PV pins via
 * nodeAffinity to `rediacc.io/ds-<datastore>-<tag>`, so STRIPPING that label
 * before the bounce leaves the recreated pod unschedulable (volume node affinity
 * conflict) and it never re-mounts the old fork. It stays Pending until the
 * publish re-stamps the label at the end of the swap, at which point it schedules
 * onto the NEW fork. Stripping the label does not disturb the RUNNING pod (kubelet
 * does not re-evaluate node affinity mid-flight), so the replica keeps serving
 * right up to its own bounce. The discard's retry stays as the belt for kubelet's
 * unmount lag, but it now converges instead of racing.
 *
 * The snapshot being rolled to is recorded first (`refreshing`), so a failed run
 * resumes on it: a replica already on it skips its bounce, and the gate stays
 * closed on the one that failed until the rerun re-opens it.
 */
export async function refreshReplicaSet(repoKey: string, debug?: boolean): Promise<void> {
  const setName = replicaSetNameFor(repoKey);
  const set = await getReplicaSet(setName);
  if (!set) {
    throw new Error(
      `Repository "${repoKey}" has no replica set. See "rdc repo replicate status ${repoKey}".`
    );
  }
  if (set.phase === 'placing') {
    throw new Error(
      `Replica set "${setName}" is still being placed. Finish it by re-running ` +
        `"rdc repo replicate ${repoKey}", or remove it ("rdc repo replicate remove ${repoKey}").`
    );
  }
  const { machineName: control } = await resolveExecutionTarget({ cluster: set.cluster });
  const controlMount = controlDatastoreMount(set.cluster);
  const snapshot = set.refreshing ?? replicaSnapshotName(setName, String(clockFn()));
  await recordReplicaSet(setName, { ...set, refreshing: snapshot });

  const plan: RefreshPlan = {
    setName,
    snapshot,
    control,
    controlMount,
    ...(debug ? { debug: true } : {}),
  };
  // No tags: the job only takes the snapshot, and an existing one is kept, so this is safe to repeat.
  const taken = await phase(
    VERB_REFRESH,
    'replica_fork',
    control,
    { parent: set.datastore, snapshot },
    { debug, steps: [planStep('refreshTail', { plan: JSON.stringify(plan) })] }
  );
  if (taken.pending) return;
  if (taken.unfinished.length > 0) {
    throw notFinished(setName, repoKey, 'the refresh stopped part-way');
  }
}

/** The fork's record on its node, when the node holds one. */
async function readNodeFork(
  replica: Replica,
  debug?: boolean
): Promise<{ fork?: { clonedFrom?: string } } | undefined> {
  const listed = await phase(
    VERB_REFRESH,
    'datastore_list',
    replica.node,
    {},
    {
      debug,
      capture: true,
    }
  );
  const rows = parseCapturedJson<{ name?: string; fork?: { clonedFrom?: string } }[]>(
    listed.result.stdout
  );
  return rows.find((row) => row.name === replica.fork);
}

/** Hold one replica down and put its fork on the new snapshot. Answers with the new fork's record. */
async function swapReplicaFork(
  plan: RefreshPlan,
  set: ReplicaSet,
  replica: Replica
): Promise<ForkEntry | undefined> {
  const { debug, control, controlMount, setName, snapshot } = plan;
  // 1. Close the scheduling gate BEFORE the bounce (see the evict-and-hold note).
  await phase(
    VERB_REFRESH,
    'kube_node_label',
    control,
    {
      mount_path: controlMount,
      node_ip: await nodeIp(replica.node),
      datastore: forkLabel(replica.fork),
      remove: true,
    },
    { debug }
  );
  // 2. Bounce the ordinal pod. It cannot come back: no node satisfies its PV.
  await phase(
    VERB_REFRESH,
    'kube_delete',
    control,
    {
      mount_path: controlMount,
      namespace: set.repo,
      replica_set: setName,
      pod_ordinal: replica.index - 1,
    },
    { debug }
  );
  // 3. The mount is nobody's now; discard and re-fork under the same tag.
  await phase(
    VERB_REFRESH,
    'replica_discard',
    replica.node,
    { name: replica.fork, repo: set.repoGuid ?? set.repo },
    { debug }
  );
  const forked = await phase(
    VERB_REFRESH,
    'replica_fork',
    control,
    { parent: set.datastore, snapshot, tags: forkTag(replica.fork) },
    { debug, capture: true }
  );
  return parseForkEntries(forked.result.stdout)?.find((e) => e.name === replica.fork);
}

/** Roll every replica to the snapshot. Skipped once the set no longer rolls to it: a stale retake. */
bindStepHandler('refreshTail', async ({ params }) => {
  const plan = jsonParam<RefreshPlan>(params, 'plan');
  const set = await getReplicaSet(plan.setName);
  if (set?.refreshing !== plan.snapshot) return;
  const { setName, snapshot } = plan;
  for (const replica of sortedReplicas(set)) {
    await rollReplica(plan, set, replica);
  }
  await deleteOldSnapshot(plan, set);
  const { refreshing: _done, ...settled } = set;
  await recordReplicaSet(setName, {
    ...settled,
    snapshot,
    refreshedAt: new Date(clockFn()).toISOString(),
  });
  outputService.success(
    `Replica set "${setName}" refreshed: all ${set.replicas.length} replica(s) now serve the new point-in-time snapshot.`
  );
});

/** One replica's turn. A fork already on the snapshot skips its bounce, and the rest is safe to repeat. */
async function rollReplica(plan: RefreshPlan, set: ReplicaSet, replica: Replica): Promise<void> {
  const { control, controlMount, debug, snapshot } = plan;
  outputService.info(
    `  refresh: replica ${replica.index}/${set.replicas.length} on ${replica.node}...`
  );
  const current = await readNodeFork(replica, debug);
  const entry =
    current?.fork?.clonedFrom === snapshot ? undefined : await swapReplicaFork(plan, set, replica);
  await bringUpReplica(
    {
      verb: VERB_REFRESH,
      repo: set.repo,
      // Storage identity (#93); pre-guid recorded sets fall back to the name.
      repoGuid: set.repoGuid ?? set.repo,
      control,
      debug,
    },
    replica,
    entry
  );
  // The label re-opens the gate, and the control copy of the record goes with it.
  await phase(
    VERB_REFRESH,
    'replica_publish',
    control,
    {
      mount_path: controlMount,
      labels: `${forkLabel(replica.fork)}@${await nodeIp(replica.node)}`,
      ...forgetParam([replica], control),
    },
    { debug }
  );
}

/** Best-effort: a leftover snapshot reclaims free, and every replica already serves the new one. */
async function deleteOldSnapshot(plan: RefreshPlan, set: ReplicaSet): Promise<void> {
  const oldSnapshot = set.snapshot ?? replicaSnapshotName(plan.setName);
  if (oldSnapshot === plan.snapshot) return;
  try {
    await phase(
      VERB_REFRESH,
      'datastore_snapshot_delete',
      plan.control,
      { name: set.datastore, snapshot: oldSnapshot },
      { debug: plan.debug }
    );
  } catch (err) {
    if (err instanceof ClusterPhasePendingError) throw err;
    outputService.warn(
      `  refresh: datastore_snapshot_delete on ${plan.control} failed (continuing): ${err}`
    );
  }
}
