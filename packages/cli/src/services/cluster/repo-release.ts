/**
 * Release ladder (spec 05 §2) — v1: rung 0 + canary weight templating.
 *
 *   0. SNAPSHOT   auto group-snap before any release-class mutation (undo)
 *   1. REHEARSE   `cluster rehearse` (landed in P3-w2)
 *   2. CANARY     SHARED live data + Rediacc-proxy weighted routing
 *   3. BLUE/GREEN fork-green + weight flip (composes; no dedicated verb in v1)
 *
 * RUNG 0: every release-class mutation here (canary create, weight change)
 * first takes a crash-consistent GROUP snapshot of the cluster's datastores
 * (`datastore_snapshot_create --group`, landed in P1) named
 * `release-undo-<epoch>` — the universal undo. Snapshots accumulate by design;
 * retention is the operator's policy (`datastore snapshot list/delete`).
 *
 * CANARY deliberately does NOT fork data: canary users on forked data would
 * read stale data and write into a doomed copy. The canary Deployment runs the
 * NEW image against the SAME live volumes; the expand-contract schema
 * discipline between the two versions is the application's burden. The traffic
 * split is the Rediacc proxy's (renet router) weighted routing: the canary
 * Service carries `rediacc.canary_of: <stable-svc>` + `rediacc.weight: <0-100>`
 * annotations, and the router rewrites the stable hostname's backend into a
 * weighted round-robin (renet pkg/router/canary.go). The flip is a weight
 * re-apply; the router picks it up on its refresh tick.
 *
 * BLUE/GREEN (schema-BREAKING releases) composes the same primitives with a
 * fork instead of shared data: green = instant CoW fork of blue INCLUDING data
 * (`rdc repo fork` / `cluster fork`), pointed at via the same weight mechanism
 * at weight 100. Rollback = restart the untouched CoW parent — but the fork
 * moment splits history: post-flip writes exist only in green, so the rollback
 * window is a POLICY decision, not magic. For zero-loss major DB upgrades,
 * logical replication (Postgres/MySQL native, cross-version) streams the delta
 * from blue to green until the flip. No `release --strategy` orchestrator in
 * v1 — the primitives compose.
 */

import type { CanarySet } from '../../schema/state-schema.js';
import { configService } from '../config/config-resources.js';
import { outputService } from '../core/output.js';
import { controlDatastoreMount } from './cluster-kube.js';
import { resolveExecutionTarget } from './cluster-target.js';
import { dispatch } from './repo-replicate.js';

/** Overlay-set label (shared with replicate; kube_delete scopes to it). */
const REPLICA_LABEL = 'rediacc.io/replica-set';
const INJECTED_LABEL = 'rediacc.io/injected';

// Test seam (mirrors repo-replicate-ops).
let clockFn: () => number = () => Date.now();
export function __setReleaseClock(fn: () => number): void {
  clockFn = fn;
}

/**
 * Rung 0: take the release-undo GROUP snapshot of the cluster's datastores
 * before a release-class mutation. Returns the snapshot name (recorded on the
 * mutated set so `status` shows what to roll back to).
 */
export async function releaseUndoSnapshot(
  clusterName: string,
  control: string,
  debug?: boolean
): Promise<string> {
  const snapshot = `release-undo-${clockFn()}`;
  outputService.info(`  rung 0: group snapshot ${snapshot} of cluster "${clusterName}"...`);
  await dispatch('datastore_snapshot_create', control, { group: clusterName, snapshot }, debug);
  return snapshot;
}

export interface CanaryOptions {
  repo: string;
  cluster: string;
  /** New engine image the canary Deployment runs (against SHARED live data). */
  image: string;
  /** Port the app serves on (must match the stable Service's port). */
  port: number;
  /** The stable Service to split traffic with. Default: the repo name. */
  service?: string;
  /** % of traffic to the canary (0 = dark, 100 = the blue/green flip). */
  weight: number;
  replicas?: number;
  debug?: boolean;
}

/** The canary set name (and Deployment/Service name) for a stable service. */
function canarySetName(service: string): string {
  return `${service}-canary`;
}

/**
 * Render the canary overlay: one Deployment running the new image + one
 * Service annotated with the router's canary contract. Pure; kube_apply stamps
 * namespace/cluster context on top (author-set annotations are preserved).
 */
export function renderCanaryOverlay(input: {
  repo: string;
  service: string;
  image: string;
  port: number;
  weight: number;
  replicas: number;
}): string {
  const name = canarySetName(input.service);
  return `apiVersion: apps/v1
kind: Deployment
metadata:
  name: ${name}
  namespace: ${input.repo}
  labels:
    ${INJECTED_LABEL}: "true"
    ${REPLICA_LABEL}: ${name}
spec:
  replicas: ${input.replicas}
  selector:
    matchLabels:
      app: ${name}
  template:
    metadata:
      labels:
        app: ${name}
        ${REPLICA_LABEL}: ${name}
    spec:
      containers:
        - name: canary
          image: ${input.image}
          ports:
            - containerPort: ${input.port}
          env:
            - { name: REDIACC_ROLE, value: canary }
---
apiVersion: v1
kind: Service
metadata:
  name: ${name}
  namespace: ${input.repo}
  labels:
    ${INJECTED_LABEL}: "true"
    ${REPLICA_LABEL}: ${name}
  annotations:
    rediacc.service_name: ${name}
    rediacc.service_port: "${input.port}"
    rediacc.canary_of: ${input.service}
    rediacc.weight: "${input.weight}"
spec:
  selector:
    app: ${name}
  ports:
    - { port: ${input.port}, targetPort: ${input.port} }
`;
}

/**
 * Rung 2 create: rung-0 undo snapshot, then apply the canary overlay and
 * record the managed set (R2-F17).
 */
export async function createCanary(options: CanaryOptions): Promise<void> {
  const service = options.service ?? options.repo;
  const setName = canarySetName(service);
  assertWeight(options.weight);
  if (await getCanary(setName)) {
    throw new Error(
      `Canary "${setName}" already exists. Change its split with "rdc repo canary weight ` +
        `--name ${setName} --weight <n>" or remove it first.`
    );
  }
  const { machineName: control } = await resolveExecutionTarget({ cluster: options.cluster });
  const undoSnapshot = await releaseUndoSnapshot(options.cluster, control, options.debug);
  const set: CanarySet = {
    repo: options.repo,
    cluster: options.cluster,
    service,
    image: options.image,
    port: options.port,
    replicas: options.replicas ?? 1,
    weight: options.weight,
    undoSnapshot,
    createdAt: new Date(clockFn()).toISOString(),
  };
  await applyCanary(setName, set, control, options.debug);
  await recordCanary(setName, set);
  outputService.success(
    `Canary "${setName}" live at ${options.weight}% on SHARED data (expand-contract schema ` +
      `discipline is the app's burden). Flip: "rdc repo canary weight --name ${setName} ` +
      `--weight <n>"; undo snapshot: ${undoSnapshot}.`
  );
}

/**
 * The weight change — rung 2 nudge or the rung 3 flip (weight 100). Takes a
 * fresh rung-0 undo snapshot, re-applies the overlay with the new weight, and
 * updates the set. The router applies the new split on its refresh tick.
 */
export async function setCanaryWeight(
  setName: string,
  weight: number,
  debug?: boolean
): Promise<void> {
  assertWeight(weight);
  const set = await getCanary(setName);
  if (!set) {
    throw new Error(`Canary "${setName}" not found. See "rdc repo canary status".`);
  }
  const { machineName: control } = await resolveExecutionTarget({ cluster: set.cluster });
  const undoSnapshot = await releaseUndoSnapshot(set.cluster, control, debug);
  const updated: CanarySet = {
    ...set,
    weight,
    undoSnapshot,
    updatedAt: new Date(clockFn()).toISOString(),
  };
  await applyCanary(setName, updated, control, debug);
  await recordCanary(setName, updated);
  outputService.success(
    `Canary "${setName}" weight -> ${weight}% (router applies it on its refresh tick).`
  );
}

/**
 * Remove a canary: delete its label-scoped overlay and forget the state. NO
 * datastores to discard — a canary shares the live data. Undo snapshots are
 * retained (operator policy; prune via "rdc datastore snapshot list/delete").
 */
export async function removeCanary(setName: string, debug?: boolean): Promise<void> {
  const set = await getCanary(setName);
  if (!set) {
    throw new Error(`Canary "${setName}" not found. See "rdc repo canary status".`);
  }
  const { machineName: control } = await resolveExecutionTarget({ cluster: set.cluster });
  try {
    await dispatch(
      'kube_delete',
      control,
      {
        mount_path: controlDatastoreMount(set.cluster),
        namespace: set.repo,
        replica_set: setName,
      },
      debug
    );
  } catch (err) {
    outputService.warn(`  remove: kube_delete on ${control} failed (continuing): ${err}`);
  }
  await forgetCanary(setName);
  outputService.success(
    `Canary "${setName}" removed; the stable Service serves 100% again. Undo snapshots retained.`
  );
}

/** Render + kube_apply the canary overlay through the control node. */
async function applyCanary(
  setName: string,
  set: CanarySet,
  control: string,
  debug?: boolean
): Promise<void> {
  const manifest = renderCanaryOverlay({
    repo: set.repo,
    service: set.service,
    image: set.image,
    port: set.port,
    weight: set.weight,
    replicas: set.replicas,
  });
  await dispatch(
    'kube_apply',
    control,
    {
      mount_path: controlDatastoreMount(set.cluster),
      namespace: set.repo,
      manifest,
      name: `canary-${setName}.yaml`,
      cluster: set.cluster,
    },
    debug
  );
}

function assertWeight(weight: number): void {
  if (!Number.isInteger(weight) || weight < 0 || weight > 100) {
    throw new Error(`--weight must be an integer 0..100, got "${weight}".`);
  }
}

// --- managed state (R2-F17): canary sets are CRUD-from-birth ------------------

/** Record a canary set in the config state bucket. */
async function recordCanary(setName: string, set: CanarySet): Promise<void> {
  const current = await listCanaries();
  await configService.setStateBucket('canaries', { ...current, [setName]: set });
}

/** Read all canary sets (for `repo canary status` / `repo status`). */
export async function listCanaries(): Promise<Record<string, CanarySet>> {
  const cfg = await configService.getCurrent();
  return cfg?.state?.canaries ?? {};
}

/** Read one canary set by name. */
async function getCanary(setName: string): Promise<CanarySet | undefined> {
  return (await listCanaries())[setName];
}

/** Remove a canary set from state (after its overlay is gone). */
async function forgetCanary(setName: string): Promise<void> {
  const current = { ...(await listCanaries()) };
  delete current[setName];
  await configService.setStateBucket('canaries', current);
}
