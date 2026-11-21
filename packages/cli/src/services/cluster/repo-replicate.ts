/**
 * `rdc repo replicate`, instant read replicas (spec 05 §1, the flagship demo).
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
 * (F15), the "1 TB -> 10 replicas in seconds" number holds with a
 * recently-checkpointed primary; L4 Service balancing is per-connection so
 * long-lived DB connections can skew (use --headless for driver-side balancing).
 */

import { DEFAULTS } from '@rediacc/shared/config';
import { WK_INFRA_DOMAIN } from '@rediacc/shared/config/well-known.generated';
import type { ReplicaSet } from '@rediacc/shared/config-schema';
import { issueFreeRepoLicense, resolveLicenseAuthority } from '../account/free-license.js';
import { readRuntimeRepoLicenseStatuses, refreshRepoLicenseIdentity } from '../account/license.js';
import { authorizeSubscriptionViaDeviceCode } from '../account/subscription-device-auth.js';
import { configService } from '../config/config-resources.js';
import { getExecutor } from '../executor/executor-factory.js';
import { machineConnections } from '../machine/machine-connection.js';

/** Labels every replicate-generated object carries, for enumerate + teardown. */
const REPLICA_LABEL = `${WK_INFRA_DOMAIN}/replica-set`;
const INJECTED_LABEL = `${WK_INFRA_DOMAIN}/injected`;
/** Node-label key prefix renet's kube_node_label stamps (distro/label.go). */
const DS_NODE_LABEL_PREFIX = `${WK_INFRA_DOMAIN}/ds-`;
/** Named-datastore mount base on machines (renet datastore.NamedMountBase). */
const NAMED_DS_BASE = '/mnt/rediacc-ds';

/** A cluster node available to host a replica. */
export interface ReplicaNode {
  machine: string;
  /** Private IP, kube_node_label resolves the k8s node by InternalIP. */
  ip: string;
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
export function getReplicaSetForRepo(repoKey: string): Promise<ReplicaSet | undefined> {
  return getReplicaSet(replicaSetNameFor(repoKey));
}

/**
 * Where each replica of a set goes: round-robin across the cluster's nodes. The
 * plan is recorded before the first job, so a rerun and a remove of a set that
 * stopped part-way both know every fork it may have made.
 */
export function planReplicas(input: {
  setName: string;
  datastore: string;
  replicas: number;
  nodes: ReplicaNode[];
}): ReplicaSet['replicas'] {
  return Array.from({ length: input.replicas }, (_, i) => ({
    index: i + 1,
    fork: `${input.datastore}:${replicaTag(input.setName, i + 1)}`,
    node: input.nodes[i % input.nodes.length].machine,
  }));
}

/** One replica's fork mount and the node label its PV pins to, for the manifest render. */
export function replicaPlacement(
  datastore: string,
  replica: ReplicaSet['replicas'][number]
): ReplicaPlacement {
  const tag = replica.fork.slice(replica.fork.indexOf(':') + 1);
  return {
    index: replica.index,
    datastoreLabel: `${DS_NODE_LABEL_PREFIX}${datastore}-${tag}`,
    mountPath: replicaForkMount(datastore, tag),
  };
}

/** The device-code login the licence paths run when a terminal operator picks "log in". */
async function loginViaDeviceCode(): Promise<void> {
  await authorizeSubscriptionViaDeviceCode(undefined, {
    interactive: process.stdin.isTTY && process.stdout.isTTY,
    announceIntro: true,
  });
}

/**
 * Install the repo licence for the fork's datastore id on its node, through the
 * account or the FREE licence. A fork gets a fresh datastore id (datastore/fork.go)
 * and renet licence-checks datastore_volumes_open against it. Each issuance claims
 * a monthly slot with no dedupe by id, so an installed valid licence for this id
 * ends a retry here, and a machine that cannot answer stops it rather than spending.
 * The licence travels over SFTP: never in a vault, a ticket or a step plan.
 */
export async function ensureForkLicense(
  input: { repo: string; repoGuid: string },
  forkName: string,
  machine: string,
  datastoreId: string
): Promise<void> {
  const repo = await configService.getRepository(input.repo);
  // A grand repo carries no grandGuid (unset or self-referential, see config/resource-state.ts), so it is its own grand and the repo guid is the right value.
  const grandGuid = repo?.grandGuid ?? input.repoGuid;
  const lease = await machineConnections.acquire(machine);
  try {
    const { machine: machineConfig, sshPrivateKey, sftp } = lease;
    const installed = await readRuntimeRepoLicenseStatuses(machine, machineConfig);
    if (
      installed.some(
        (s) =>
          s.repositoryGuid === input.repoGuid &&
          s.datastoreId === datastoreId &&
          s.status === 'valid'
      )
    ) {
      return;
    }
    const authority = await resolveLicenseAuthority(loginViaDeviceCode);
    if (authority === 'free') {
      // No datastoreMount: the FREE route takes a fixed 3 GB cap and never sizes the image (FreeLicenseParams has no mount field), unlike the token path's size probe.
      await issueFreeRepoLicense(
        machine,
        machineConfig,
        sshPrivateKey,
        { repositoryGuid: input.repoGuid, grandGuid, kind: 'fork', datastoreId },
        undefined,
        sftp
      );
      return;
    }
    const issued = await refreshRepoLicenseIdentity(
      machine,
      machineConfig,
      sshPrivateKey,
      {
        repositoryGuid: input.repoGuid,
        grandGuid,
        kind: 'fork',
        datastoreId,
        datastoreMount: forkMountFromName(forkName),
      },
      undefined,
      sftp
    );
    if (!issued) {
      throw new Error(
        `Cannot license replica fork "${forkName}" on ${machine}: the account did not issue a licence.`
      );
    }
  } finally {
    lease.release();
  }
}

/** `<parent>:<tag>` to its mount path `/mnt/rediacc-ds/<parent>-<tag>`. */
function forkMountFromName(forkName: string): string {
  const [parent, tag] = forkName.split(':');
  return replicaForkMount(parent, tag);
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
   * The repo's GUID, the on-datastore folder identity (#93: storage speaks
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
