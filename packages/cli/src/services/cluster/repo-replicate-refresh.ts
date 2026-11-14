/** `rdc repo replicate refresh`: roll a replica set to a new snapshot, one replica at a time (PLAN-detached-jobs). */

import type { ReplicaSet } from '@rediacc/shared/config-schema';
import { outputService } from '../core/output.js';
import { parseCapturedJson } from '../executor/local-executor.js';
import { bindStepHandler, planStep } from '../jobs/steps.js';
import { jsonParam } from '../jobs/steps-support.js';
import { ClusterPhasePendingError } from './cluster-job.js';
import { controlDatastoreMount } from './cluster-kube.js';
import { resolveExecutionTarget } from './cluster-target.js';
import {
  getReplicaSet,
  recordReplicaSet,
  replicaSetNameFor,
  replicaSnapshotName,
} from './repo-replicate.js';
import {
  bringUpReplica,
  type ForkEntry,
  forgetParam,
  forkLabel,
  forkTag,
  nodeIp,
  notFinished,
  parseForkEntries,
  phase,
  type Replica,
  replicateNow,
  sortedReplicas,
} from './repo-replicate-phase.js';

const VERB_REFRESH = 'repo replicate refresh';

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
  const snapshot = set.refreshing ?? replicaSnapshotName(setName, String(replicateNow()));
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
  await recordReplicaSet(setName, {
    ...set,
    refreshing: undefined,
    snapshot,
    refreshedAt: new Date(replicateNow()).toISOString(),
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
