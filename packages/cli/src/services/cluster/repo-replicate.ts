/**
 * `rdc repo replicate` — instant read replicas (spec 05 §1, the flagship demo).
 *
 * Composes the P1/P2 fork-attach primitives (datastore snapshot + fork + attach
 * --writes local dm-COW overlay, all landed) with generated k8s objects:
 *   1. datastore snapshot (one instant)
 *   2. N fork-attaches, --writes local, spread across the cluster's nodes
 *   3. N generated `local` PVs (one per node, into each fork mount)
 *   4. a generated replica StatefulSet + pod anti-affinity + REDIACC_ROLE=replica
 *   5. two Services: <name>-rw -> the primary pod, <name>-ro -> the N replicas
 *
 * Replicas are WRITABLE point-in-time copies (a DB engine writes WAL/temp even
 * for SELECTs, so it cannot run on a read-only data-dir): each replica does one
 * crash-recovery pass and serves. Throwaway writes. Readiness probes auto-eject a
 * replica while it is re-forked, so rolling `--refresh` is invisible (N-1 keep
 * serving). REPLICATE IS MANAGED STATE WITH CRUD FROM BIRTH (R2-F17): create /
 * status / remove all exist, and `repo status` shows replica sets.
 *
 * HONEST LIMITS (documented in the CLI help + here): point-in-time reads, NO
 * read-your-writes; overlay sizing is × N (storage-health watches the dm-COW
 * fill, the F10 allocation-churn effect applies per replica); the FORK is
 * constant-time regardless of DB size, but each replica then runs a
 * crash-recovery pass proportional to WAL/checkpoint distance with cold caches
 * (F15) — the "1 TB -> 10 replicas in seconds" number holds with a
 * recently-checkpointed primary; L4 Service balancing is per-connection so
 * long-lived DB connections can skew (use --headless for driver-side balancing).
 */

import { DEFAULTS } from '@rediacc/shared/config';
import type { ReplicaSet } from '@rediacc/shared/config-schema';
import { configService } from '../config/config-resources.js';
import { getExecutor } from '../executor/executor-factory.js';
import { parseCapturedJson } from '../executor/local-executor.js';

/** Labels every replicate-generated object carries, for enumerate + teardown. */
const REPLICA_LABEL = 'rediacc.io/replica-set';
const INJECTED_LABEL = 'rediacc.io/injected';
/** Node-label key prefix renet's kube_node_label stamps (distro/label.go). */
const DS_NODE_LABEL_PREFIX = 'rediacc.io/ds-';
/** Named-datastore mount base on machines (renet datastore.NamedMountBase). */
const NAMED_DS_BASE = '/mnt/rediacc-ds';

/** A cluster node available to host a replica. */
export interface ReplicaNode {
  machine: string;
  /** Private IP — kube_node_label resolves the k8s node by InternalIP. */
  ip: string;
}

/** Inputs the orchestrator resolves before composing the datastore plane. */
export interface ProvisionReplicasInput {
  repo: string;
  /**
   * The repo's GUID — its STORAGE identity (#93: storage speaks GUID, k8s
   * objects speak name). The repo folder on the datastore is `repos/<guid>`
   * (#83: `repo create` dispatches `repository create --name <guid>`), so the
   * fork — a byte-clone of the parent — carries `repos/<guid>` too, and every
   * storage-facing verb must address it by GUID; `repo` is only for k8s names.
   */
  repoGuid: string;
  setName: string;
  datastore: string;
  snapshot: string;
  replicas: number;
  /** Cluster nodes to spread replicas across (round-robin). */
  nodes: ReplicaNode[];
  /** Control-plane machine + its CP data-dir mount (kube_node_label target). */
  controlMachine: string;
  controlMount: string;
  debug?: boolean;
}

/** The snapshot a replica set's forks clone from (refresh cycles the suffix). */
export function replicaSnapshotName(setName: string, suffix?: string): string {
  return suffix ? `replicate-${setName}-${suffix}` : `replicate-${setName}`;
}

/**
 * A repo ref's k8s/datastore-safe stem. A repo key may carry a tag (`shop:test`),
 * but a k8s object name and a datastore fork tag both reject `:`.
 */
export function repoKeySlug(repoKey: string): string {
  return repoKey.replaceAll(':', '-');
}

/**
 * The managed replica set's name for a repo (spec §4.4): there is exactly ONE
 * set per repo, so the set is a property OF the repo rather than an
 * independently named object, and its name is DERIVED from the ref instead of
 * being passed in. For an untagged repo this is the same `<repo>-replicas` the
 * old `--set` flag defaulted to, so recorded state keys are unchanged.
 */
export function replicaSetNameFor(repoKey: string): string {
  return `${repoKeySlug(repoKey)}-replicas`;
}

/** The repo's managed replica set, or undefined when it has none. */
export async function getReplicaSetForRepo(repoKey: string): Promise<ReplicaSet | undefined> {
  return getReplicaSet(replicaSetNameFor(repoKey));
}

/**
 * Provision the datastore plane for a replica set (spec 05 §1 steps 1-2): ONE
 * snapshot of the repo's datastore, then N fork-attaches with --writes local
 * (dm-COW overlay) spread round-robin across the cluster's nodes, each hosting
 * node stamped with the fork's own `rediacc.io/ds-<parent>-<tag>` label so the
 * replica PV pins to wherever the fork datastore lives (follows it on
 * failover, F3). Returns each replica's placement (fork mount + node label)
 * for the manifest render. Composes only landed bridge verbs; the parent is
 * never stopped.
 */
export async function provisionReplicaDatastores(
  input: ProvisionReplicasInput
): Promise<{ placements: ReplicaPlacement[]; forks: ReplicaSet['replicas'] }> {
  if (input.nodes.length === 0) {
    throw new Error(`Cannot replicate "${input.repo}": the cluster has no nodes to host replicas.`);
  }
  // 1. One instant snapshot of the repo's datastore.
  await dispatch(
    'datastore_snapshot_create',
    input.controlMachine,
    { name: input.datastore, snapshot: input.snapshot },
    input.debug
  );

  const placements: ReplicaPlacement[] = [];
  const forks: ReplicaSet['replicas'] = [];
  for (let i = 1; i <= input.replicas; i++) {
    const node = input.nodes[(i - 1) % input.nodes.length];
    await provisionOneReplica(input, i, node);
    const tag = replicaTag(input.setName, i);
    placements.push({
      index: i,
      datastoreLabel: `${DS_NODE_LABEL_PREFIX}${input.datastore}-${tag}`,
      mountPath: replicaForkMount(input.datastore, tag),
    });
    forks.push({ index: i, fork: `${input.datastore}:${tag}`, node: node.machine });
  }
  return { placements, forks };
}

/** Fork + attach + node-label one replica's datastore (create and refresh). */
export async function provisionOneReplica(
  input: Pick<
    ProvisionReplicasInput,
    'repoGuid' | 'setName' | 'datastore' | 'snapshot' | 'controlMachine' | 'controlMount' | 'debug'
  >,
  index: number,
  node: ReplicaNode
): Promise<void> {
  const tag = replicaTag(input.setName, index);
  const forkName = `${input.datastore}:${tag}`;
  // Clone the datastore from the snapshot (constant-time, DB-size-independent).
  // datastore_fork registers the fork record ONLY in the control machine's
  // registry; when the replica lands on a DIFFERENT node, its registry has no
  // such record, so we ferry the record (the `datastore fork --json` output)
  // there via datastore_adopt before attaching (finding #36; mirrors the
  // cluster-fork cross-machine path, cluster-fork.ts:203-218 / finding #14).
  const forkRes = await getExecutor().execute({
    functionName: 'datastore_fork',
    machineName: input.controlMachine,
    params: { parent: input.datastore, tag, snapshot: input.snapshot },
    debug: input.debug,
    captureOutput: true,
  });
  if (!forkRes.success) {
    throw new Error(
      `Replica step "datastore_fork" failed on ${input.controlMachine}: ${forkRes.error ?? DEFAULTS.CLOUD.UNKNOWN_ERROR}`
    );
  }
  if (node.machine !== input.controlMachine) {
    const record = parseCapturedJson<unknown>(forkRes.stdout);
    const recordB64 = Buffer.from(JSON.stringify(record)).toString('base64');
    await dispatch(
      'datastore_adopt',
      node.machine,
      { name: forkName, record_b64: recordB64 },
      input.debug
    );
  }
  // Attach --writes local on the target node (ephemeral dm-COW overlay).
  await dispatch(
    'datastore_attach',
    node.machine,
    { name: forkName, writes: 'local' },
    input.debug
  );
  if (node.machine !== input.controlMachine) {
    // The fork record now lives on the replica node and is attached there; the
    // control's copy (from datastore_fork) is vestigial. Forget it on control
    // (registry-only; the fork is DETACHED there and the clone is owned by the
    // node's record) so a later re-fork of the SAME tag — `repo replicate
    // refresh`, which discards on the node then re-forks on control — does not
    // collide with a stale control record (finding #40).
    await dispatch('datastore_forget', input.controlMachine, { name: forkName }, input.debug);
  }
  // Open the repo's per-volume LUKS images on the fork (bug #49). The fork is a
  // BLOCK-layer clone, so it carries the ciphertext `<fork>/repos/<GUID>/volumes/
  // <pvc>.img` AND the empty directory that image was mounted over. The replica's
  // PV points at that directory. Without this step the image is never opened, the
  // pod bind-mounts the empty dir, and the replica comes up healthy, Ready, and
  // EMPTY — no FailedMount, no event, no symptom except missing data.
  //
  // By GUID, never by name (#93, found live by B1): the repo folder on the
  // datastore — and therefore on its byte-clone fork — is `repos/<guid>`, so a
  // name-based `repo:` param stats `repos/<name>` and aborts every replicate.
  //
  // It MUST precede kube_node_label: the label is the scheduling gate (the PV's
  // nodeAffinity key), so opening first means a pod can never be scheduled onto a
  // volume that is not yet mounted.
  await dispatch(
    'datastore_volumes_open',
    node.machine,
    { name: forkName, repo: input.repoGuid },
    input.debug
  );
  // Stamp the fork's datastore label on the hosting node (PV nodeAffinity key).
  await dispatch(
    'kube_node_label',
    input.controlMachine,
    {
      mount_path: input.controlMount,
      node_ip: node.ip,
      datastore: `${input.datastore}-${tag}`,
    },
    input.debug
  );
}

/** The fork clone's mount path `/mnt/rediacc-ds/<parent>-<tag>` on its node. */
function replicaForkMount(datastore: string, tag: string): string {
  return `${NAMED_DS_BASE}/${datastore}-${tag}`;
}

/** Dispatch a bridge verb, throwing on non-success. */
export async function dispatch(
  functionName: string,
  machineName: string,
  params: Record<string, unknown>,
  debug?: boolean
): Promise<void> {
  const res = await getExecutor().execute({ functionName, machineName, params, debug });
  if (!res.success) {
    throw new Error(
      `Replica step "${functionName}" failed on ${machineName}: ${res.error ?? DEFAULTS.CLOUD.UNKNOWN_ERROR}`
    );
  }
}

// --- managed state (R2-F17): replica sets are CRUD-from-birth -----------------

/** Record a replica set in the config state bucket. */
export async function recordReplicaSet(setName: string, set: ReplicaSet): Promise<void> {
  const current = await listReplicaSets();
  await configService.setStateBucket('replicaSets', { ...current, [setName]: set });
}

/** Read all replica sets (for `repo replicate status` / `repo status`). */
export async function listReplicaSets(): Promise<Record<string, ReplicaSet>> {
  const cfg = await configService.getCurrent();
  return cfg?.state?.replicaSets ?? {};
}

/** Read one replica set by name. */
export async function getReplicaSet(setName: string): Promise<ReplicaSet | undefined> {
  return (await listReplicaSets())[setName];
}

/** Remove a replica set from state (after its datastores + manifests are gone). */
export async function forgetReplicaSet(setName: string): Promise<void> {
  const current = { ...(await listReplicaSets()) };
  delete current[setName];
  await configService.setStateBucket('replicaSets', current);
}

/** The datastore fork record key + mount for replica `i` of a repo's datastore. */
function replicaTag(setName: string, i: number): string {
  return `${setName}-r${i}`;
}

/** The rendered spec inputs (resolved by the orchestrator from the cluster). */
export interface ReplicaRenderInput {
  /** Repo name = the k8s namespace + the workload/Service base name. */
  repo: string;
  /**
   * The repo's GUID — the on-datastore folder identity (#93: storage speaks
   * GUID, k8s objects speak name). Only PATHS use it: the replica PV points
   * into the fork mount at `mounts/volumes/<guid>/<pvc>`, mirroring what the
   * parent's volumes-open/CSI produce (kubevolume.MountPath keyed by the renet
   * repo identifier, which #83 made the GUID).
   */
  repoGuid: string;
  /** The replica-set name (defaults to `<repo>-replicas`). */
  setName: string;
  /** The datastore the repo (and its replicas) live in. */
  datastore: string;
  /** The primary pod's app label selector value (the -rw Service targets it). */
  primaryApp: string;
  /** Container image the replicas run (same engine as the primary). */
  image: string;
  /** Container port the DB serves on. */
  port: number;
  /** The declared PVC name the engine mounts as its data dir. */
  pvc: string;
  /** Per-replica placement: node label value the replica PV pins to. */
  replicas: ReplicaPlacement[];
  /** DNS returns all replica pod IPs (driver-side balancing) instead of a VIP. */
  headless: boolean;
}

/** One replica's node placement + its fork datastore/mount. */
export interface ReplicaPlacement {
  index: number;
  /** The node this replica's fork datastore is attached to (rediacc.io/ds-<x>). */
  datastoreLabel: string;
  /** The fork datastore mount path on that node. */
  mountPath: string;
}

/**
 * Render the full replica-set manifest set (spec 05 §1 steps 3-5): one `local`
 * PV per replica (nodeAffinity-pinned to the node holding that replica's fork
 * datastore), a StatefulSet of N replicas with pod anti-affinity + REDIACC_ROLE=
 * replica, and the two Services (-rw -> primary, -ro -> replicas). Pure: the
 * orchestrator applies the returned YAML.
 */
export function renderReplicaSet(input: ReplicaRenderInput): string {
  const docs: string[] = [];
  for (const r of input.replicas) {
    docs.push(renderReplicaPV(input, r));
  }
  docs.push(renderReplicaStatefulSet(input));
  docs.push(renderReadService(input));
  docs.push(renderWriteService(input));
  return docs.join('---\n');
}

/** A `local` PV pinned (nodeAffinity) to the node holding this replica's fork. */
function renderReplicaPV(input: ReplicaRenderInput, r: ReplicaPlacement): string {
  const pvName = `${input.setName}-${r.index}-${input.pvc}`;
  return `apiVersion: v1
kind: PersistentVolume
metadata:
  name: ${pvName}
  labels:
    ${INJECTED_LABEL}: "true"
    ${REPLICA_LABEL}: ${input.setName}
spec:
  storageClassName: rediacc-ds-${input.datastore}
  capacity: { storage: 1Gi }
  accessModes: [ReadWriteOnce]
  persistentVolumeReclaimPolicy: Retain
  volumeMode: Filesystem
  local:
    path: ${r.mountPath}/mounts/volumes/${input.repoGuid}/${input.pvc}
  nodeAffinity:
    required:
      nodeSelectorTerms:
        - matchExpressions:
            - key: ${r.datastoreLabel}
              operator: In
              values: ["true"]
  claimRef:
    namespace: ${input.repo}
    name: ${input.pvc}-${input.setName}-${r.index - 1}
`;
}

/**
 * The replica StatefulSet: N pods, each pinned to a distinct replica node via pod
 * anti-affinity, running the engine with REDIACC_ROLE=replica (so the app knows
 * it is a throwaway read copy). Each pod's PVC is pre-bound to its `local` PV.
 */
function renderReplicaStatefulSet(input: ReplicaRenderInput): string {
  return `apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: ${input.setName}
  namespace: ${input.repo}
  labels:
    ${INJECTED_LABEL}: "true"
    ${REPLICA_LABEL}: ${input.setName}
spec:
  serviceName: ${input.repo}-ro
  replicas: ${input.replicas.length}
  selector:
    matchLabels:
      ${REPLICA_LABEL}: ${input.setName}
  template:
    metadata:
      labels:
        ${REPLICA_LABEL}: ${input.setName}
        app: ${input.setName}
    spec:
      affinity:
        podAntiAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            - labelSelector:
                matchLabels:
                  ${REPLICA_LABEL}: ${input.setName}
              topologyKey: kubernetes.io/hostname
      containers:
        - name: replica
          image: ${input.image}
          ports:
            - containerPort: ${input.port}
          env:
            - { name: REDIACC_ROLE, value: replica }
          volumeMounts:
            - { name: ${input.pvc}, mountPath: /data }
  volumeClaimTemplates:
    - metadata:
        name: ${input.pvc}
        labels:
          ${INJECTED_LABEL}: "true"
          ${REPLICA_LABEL}: ${input.setName}
      spec:
        accessModes: [ReadWriteOnce]
        storageClassName: rediacc-ds-${input.datastore}
        resources:
          requests:
            storage: 1Gi
`;
}

/** `<repo>-ro` Service: load-balances reads across the replica pods (or headless). */
function renderReadService(input: ReplicaRenderInput): string {
  const clusterIP = input.headless ? '\n  clusterIP: None' : '';
  return `apiVersion: v1
kind: Service
metadata:
  name: ${input.repo}-ro
  namespace: ${input.repo}
  labels:
    ${INJECTED_LABEL}: "true"
    ${REPLICA_LABEL}: ${input.setName}
spec:${clusterIP}
  selector:
    ${REPLICA_LABEL}: ${input.setName}
  ports:
    - { port: ${input.port}, targetPort: ${input.port} }
`;
}

/** `<repo>-rw` Service: routes writes to the PRIMARY pod only. */
function renderWriteService(input: ReplicaRenderInput): string {
  return `apiVersion: v1
kind: Service
metadata:
  name: ${input.repo}-rw
  namespace: ${input.repo}
  labels:
    ${INJECTED_LABEL}: "true"
    ${REPLICA_LABEL}: ${input.setName}
spec:
  selector:
    app: ${input.primaryApp}
  ports:
    - { port: ${input.port}, targetPort: ${input.port} }
`;
}
