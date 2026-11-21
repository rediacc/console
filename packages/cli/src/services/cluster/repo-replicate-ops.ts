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
import { configService } from '../config/config-resources.js';
import { outputService } from '../core/output.js';
import { bindStepHandler, planStep } from '../jobs/steps.js';
import { jsonParam } from '../jobs/steps-support.js';
import { ClusterPhasePendingError, type ClusterPhaseResult } from './cluster-job.js';
import { controlDatastoreMount } from './cluster-kube.js';
import { resolveExecutionTarget } from './cluster-target.js';
import {
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
import {
  type BringUp,
  bringUpReplica,
  forgetParam,
  forkLabel,
  forkTag,
  nodeIp,
  notFinished,
  parseForkEntries,
  phase,
  type Replica,
  replicateNow,
  resolveReplicaNodes,
  sortedReplicas,
} from './repo-replicate-phase.js';

const NAMED_DS_BASE = '/mnt/rediacc-ds';
/** Conventional data-volume name repos declare (spec 05 templates). */
const DEFAULT_PVC_NAME = 'data';
const VERB_CREATE = 'repo replicate';
const VERB_REMOVE = 'repo replicate remove';

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
    createdAt: existing?.createdAt ?? new Date(replicateNow()).toISOString(),
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
