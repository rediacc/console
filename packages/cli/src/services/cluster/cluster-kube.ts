/**
 * Kubernetes cluster orchestration: multi-node k3s bring-up + the ANCHOR+REJOIN
 * whole-cluster fork/migrate/scale flows (docs/design/04-cluster-fork-migrate.md).
 * These sit above the renet datastore_* / kube_* / repository_* bridge primitives
 * and sequence them across a cluster's members:
 *   - the control-plane data-dir lives INSIDE a dedicated, cluster-labeled control
 *     datastore (ds-control-<cluster>), so "the control-plane image IS the cluster"
 *     and it forks/migrates by moving that datastore — not by reflinking per-node
 *     images (the old drain+reflink recipe carried the parent CA and is deleted);
 *   - FORK = crash-consistent rbd group snapshot (parent never stops) → clone each
 *     datastore → attach on the dest with --writes composing → control-plane
 *     identity rewrite operation=fork (F1-safe PKI re-mint + secret scrub) → fresh
 *     agent rejoins with the new-CA token → stale-Node cleanup;
 *   - MIGRATE = in-Ceph fenced remap (detach → fenced attach → identity rewrite
 *     operation=migrate, CA preserved, IP-only, zero data copy) + a health gate.
 */

import { randomUUID } from 'node:crypto';
import { DEFAULTS } from '@rediacc/shared/config';
import type { ClusterConfig, ClusterPool } from '../../types/index.js';
import { getCluster } from '../config/config-cluster-ops.js';
import { configService } from '../config/config-resources.js';
import { auditService } from '../core/audit.js';
import { outputService } from '../core/output.js';
import {
  type LocalExecuteResult,
  localExecutorService,
  parseCapturedJson,
} from '../executor/local-executor.js';
import { dispatchCeph, exportCephClientConfig, resolveCephMembers } from './cluster-ceph.js';

const MOUNT_BASE = '/mnt/rediacc/mounts';
const NAMED_DS_BASE = '/mnt/rediacc-ds';
const API_PORT = 6443;
const DEFAULT_NODE_SIZE = '20G';
/** Default size of the anchor control datastore (spec 03 gate-fixed: 10 GiB). */
const CONTROL_DS_DEFAULT_SIZE = '10G';
/**
 * The Ceph CLI cluster name (distinct from the rediacc cluster name). renet's
 * ceph_* functions default it to "rediacc", but the datastore/rbd paths assume
 * "ceph", so we pass it explicitly (mirrors cluster-provision's CEPH_CLUSTER_NAME).
 */
const CEPH_CLI_CLUSTER = 'ceph';

/** k3s server + agent roles (hyperconverged nodes run a server too). */
const K8S_SERVER_ROLES = new Set(['k8s-server', 'hyperconverged']);

interface K8sMember {
  name: string;
  ip: string;
  pool: string;
  index: number;
  role: string;
}

/** The per-node cluster image repo is named after the cluster (agent nodes). */
function clusterRepo(clusterName: string): string {
  return clusterName;
}
function clusterMount(clusterName: string): string {
  return `${MOUNT_BASE}/${clusterRepo(clusterName)}`;
}
/**
 * The anchor control datastore holds the control-plane data-dir (spec 02 §1 /
 * 04 §1: "the control-plane image IS the cluster"). Named per-cluster and
 * cluster-labeled so it is group-snap-forkable and so repository dispatch +
 * `kube_identity_rewrite --operation fork` find the CP by construction.
 */
export function controlDatastore(clusterName: string): string {
  return `ds-control-${clusterName}`;
}
export function controlDatastoreMount(clusterName: string): string {
  return `${NAMED_DS_BASE}/${controlDatastore(clusterName)}`;
}
function serverUrl(ip: string): string {
  return `https://${ip}:${API_PORT}`;
}

/** Options controlling the anchor control datastore backend + size. */
export interface ControlDatastoreOptions {
  /** local | ceph. Default: ceph when the cluster has a ceph pool, else local. */
  backend?: 'local' | 'ceph';
  /** rbd pool for the ceph backend. Default: the cluster's ceph pool. */
  pool?: string;
  /** Datastore size. Default: CONTROL_DS_DEFAULT_SIZE (10 GiB). */
  size?: string;
}

/**
 * Resolve the anchor control datastore backend: an explicit override wins, else
 * ceph when the cluster provisions ceph (rbd-backed CP = group-snap-forkable),
 * else local (a zero-Ceph cluster whose CP forks by folder reflink).
 */
function resolveControlDsBackend(
  cluster: ClusterConfig,
  opts: ControlDatastoreOptions
): 'local' | 'ceph' {
  if (opts.backend) return opts.backend;
  return cluster.pools.some((p) => p.role === 'ceph') ? 'ceph' : 'local';
}

/** Resolve a cluster's k8s pool members (name + private IP) in pool/index order. */
async function resolveK8sMembers(clusterName: string, pools: ClusterPool[]): Promise<K8sMember[]> {
  const members: K8sMember[] = [];
  for (const pool of pools) {
    for (let i = 1; i <= pool.count; i++) {
      const name = `${clusterName}-${pool.name}-${i}`;
      const machine = await configService.getLocalMachine(name);
      members.push({ name, ip: machine.ip, pool: pool.name, index: i, role: pool.role });
    }
  }
  return members;
}

function k8sPoolsOf(cluster: ClusterConfig): ClusterPool[] {
  return cluster.pools.filter(
    (p) => p.role === 'k8s-server' || p.role === 'k8s-agent' || p.role === 'hyperconverged'
  );
}

function cephPoolsOf(cluster: ClusterConfig): ClusterPool[] {
  return cluster.pools.filter((p) => p.role === 'ceph');
}

/**
 * Refuse a fork onto a destination whose control node is ALREADY running its own
 * k3s control plane (finding #8). The fork's identity rewrite boots the fork's
 * k3s bound to the dest control node's IP:6443, but stopK3sUnitsForRewrite only
 * stops the src/target networkID units — NOT a DIFFERENT cluster's control plane
 * already bound to that IP:port. Two k3s servers, one IP:6443 → `bind: address
 * already in use`, failing deep in the identity rewrite AFTER the snapshot+clone.
 *
 * Probe cheaply BEFORE any snapshot/clone work (fail fast, dispatch nothing
 * destructive): is the dest's OWN control datastore CP serving? A bare dest (the
 * only valid fork target) has no such CP, so kube_health fails and we proceed.
 */
async function assertDestNotRunningOwnK3s(
  destCluster: string,
  dstControlName: string,
  debug?: boolean
): Promise<void> {
  const ownMount = controlDatastoreMount(destCluster);
  const res = await localExecutorService.execute({
    functionName: 'kube_health',
    machineName: dstControlName,
    params: { mount_path: ownMount },
    captureOutput: true,
    debug,
  });
  if (res.success) {
    throw new Error(
      `Cluster fork onto "${destCluster}" refused: its control node ${dstControlName} is already ` +
        `running its own k3s control plane (${controlDatastore(destCluster)} at ${ownMount}). The ` +
        `fork's control plane binds the same :${API_PORT} and would collide. Fork onto a BARE ` +
        `destination — tear the destination cluster's control plane down first ` +
        `(rdc cluster destroy --name ${destCluster}, or uninstall its k3s) — then retry.`
    );
  }
}

/**
 * Give a fork's DEST members access to the SOURCE cluster's Ceph before the
 * adopt/attach loop (findings #7 + #15). createCluster only distributes a
 * cluster's OWN ceph config to its OWN nodes, so a fork dest of a DIFFERENT
 * cluster has neither the source `/etc/ceph` client config (needed to map the
 * fork's rbd clone) NOR the package tooling the attach + kine-scrub shell out to
 * (`rbd` from ceph-common; `sqlite3`). Seed both on every dest member. A
 * local-tier source (no ceph pool) has nothing to seed — its fork clones are not
 * rbd-backed — so this is a no-op there.
 */
async function prepareForkDest(
  sourceClusterName: string,
  source: ClusterConfig,
  dstMembers: K8sMember[],
  debug?: boolean
): Promise<void> {
  const cephPools = cephPoolsOf(source);
  if (cephPools.length === 0) return;
  const cephMembers = await resolveCephMembers(sourceClusterName, cephPools);
  if (cephMembers.length === 0) return;
  const mon = cephMembers[0];

  outputService.info(
    `  seeding fork dest members with source "${sourceClusterName}" ceph access (from ${mon.name})...`
  );
  const payload = await exportCephClientConfig(mon.name, debug);
  for (const member of dstMembers) {
    // Package prereqs first (rbd + sqlite3), then the /etc/ceph client config.
    await dispatchCeph('kube_fork_dest_prep', member.name, {}, debug);
    await dispatchCeph(
      'ceph_client_config_install',
      member.name,
      { conf: payload.conf, keyring: payload.keyring },
      debug
    );
  }
}

/**
 * Dispatch one internal kube_ or repository_ bridge function to a member,
 * throwing on any non-success. captureOutput returns renet's stdout (used to
 * read the join token).
 */
async function dispatch(
  functionName: string,
  machineName: string,
  params: Record<string, unknown>,
  opts: { debug?: boolean; capture?: boolean } = {}
): Promise<LocalExecuteResult> {
  const result = await localExecutorService.execute({
    functionName,
    machineName,
    params,
    debug: opts.debug,
    captureOutput: opts.capture,
  });
  if (!result.success) {
    throw new Error(
      `Cluster step "${functionName}" failed on ${machineName}: ${result.error ?? DEFAULTS.CLOUD.UNKNOWN_ERROR}`
    );
  }
  return result;
}

/** Create the node's (unencrypted) cluster image with a fresh networkID. */
async function createNodeImage(
  member: K8sMember,
  clusterName: string,
  size: string,
  debug?: boolean
): Promise<number> {
  const networkId = await configService.allocateNetworkId();
  await dispatch(
    'repository_create',
    member.name,
    {
      repository: clusterRepo(clusterName),
      size,
      guid: randomUUID(),
      network_id: networkId,
      start_docker: false,
    },
    { debug }
  );
  return networkId;
}

function poolSize(pools: ClusterPool[], poolName: string): string {
  return pools.find((p) => p.name === poolName)?.size ?? DEFAULT_NODE_SIZE;
}

/**
 * Provision the anchor control datastore on the control node and install the
 * k3s server with its --data-dir INSIDE it (spec 02 §1 / 04 §1). This is what
 * makes the control plane forkable/migratable by construction and what writes
 * the descriptor + distro.json that wireKubeDeps/findClusterControlPlane and the
 * fork arm rely on. Returns the CP mount path.
 */
async function installControlPlane(
  clusterName: string,
  cluster: ClusterConfig,
  control: K8sMember,
  controlDs: ControlDatastoreOptions,
  debug?: boolean
): Promise<string> {
  const dsName = controlDatastore(clusterName);
  const backend = resolveControlDsBackend(cluster, controlDs);
  const createParams: Record<string, unknown> = {
    name: dsName,
    backend,
    size: controlDs.size ?? CONTROL_DS_DEFAULT_SIZE,
    cluster: clusterName,
  };
  if (backend === 'ceph') {
    createParams.pool = controlDs.pool ?? cluster.ceph?.pool ?? DEFAULTS.CEPH.POOL;
    createParams.ceph_cluster = CEPH_CLI_CLUSTER;
  }

  outputService.info(
    `Cluster "${clusterName}": creating anchor control datastore ${dsName} (${backend}) on ${control.name}...`
  );
  await dispatch('datastore_create', control.name, createParams, { debug });
  await dispatch('datastore_attach', control.name, { name: dsName }, { debug });

  const mount = controlDatastoreMount(clusterName);
  const serverNet = await configService.allocateNetworkId();
  outputService.info(
    `Cluster "${clusterName}": installing embedded k3s server on ${control.name} (${control.ip})...`
  );
  await dispatch(
    'kube_install',
    control.name,
    { mount_path: mount, network_id: serverNet, role: 'server', bind_ip: control.ip },
    { debug }
  );
  return mount;
}

/**
 * Bring up the cluster's k8s pools: install the control-plane on the first
 * server member (anchor datastore + embedded k3s, bound to its real NIC), then
 * join every agent (real NIC + the CA-derived token). Server-first ordering
 * (S2 verdict 3); agents are disposable (their per-node image is a plain repo).
 */
export async function installK8s(
  clusterName: string,
  cluster: ClusterConfig,
  k8sPools: ClusterPool[],
  options: { debug?: boolean; controlDs?: ControlDatastoreOptions } = {}
): Promise<void> {
  const { debug } = options;
  const members = await resolveK8sMembers(clusterName, k8sPools);
  const servers = members.filter((m) => K8S_SERVER_ROLES.has(m.role));
  const agents = members.filter((m) => m.role === 'k8s-agent');
  if (servers.length === 0) {
    throw new Error(
      `Cluster "${clusterName}" has no k8s-server (or hyperconverged) pool member to host the control plane.`
    );
  }
  const control = servers[0];
  const mount = await installControlPlane(
    clusterName,
    cluster,
    control,
    options.controlDs ?? {},
    debug
  );

  // The CA-derived join token new nodes present. The agents' data-dir mount is a
  // plain per-node repo (disposable cache); only the CP rides the anchor datastore.
  const tokenRes = await dispatch(
    'kube_join_token',
    control.name,
    { mount_path: mount },
    { debug, capture: true }
  );
  const token = /K10[^"\s]+/.exec(tokenRes.stdout ?? '')?.[0];
  if (!token) {
    throw new Error(`Could not read the k3s join token from ${control.name}.`);
  }

  for (const agent of agents) {
    outputService.info(`  joining agent ${agent.name} (${agent.ip})...`);
    const agentNet = await createNodeImage(
      agent,
      clusterName,
      poolSize(k8sPools, agent.pool),
      debug
    );
    await dispatch(
      'kube_join',
      agent.name,
      {
        mount_path: mount,
        network_id: agentNet,
        role: 'agent',
        token,
        endpoint: serverUrl(control.ip),
        bind_ip: agent.ip,
      },
      { debug }
    );
  }
  outputService.success(
    `Cluster "${clusterName}": k3s control plane up (1 server + ${agents.length} agent(s)).`
  );
}

export interface ForkClusterOptions {
  tag: string;
  /** Existing destination cluster to fork onto (its members host the fork). */
  cluster?: string;
  /**
   * Write disposition for the fork's datastores (04 §2): `local` = ephemeral
   * dm-COW overlay over a read-only clone (zero Ceph footprint — a throwaway test
   * cluster), `ceph` = durable RW clone. Default `local`.
   */
  writes?: 'local' | 'ceph';
  /** Bring the forked repos up and gate on cluster health after the fork boots. */
  up?: boolean;
  /**
   * Effect-isolation ROLE written into the fork's ROLE ConfigMap (02 §4):
   * `fork` (default) or `rehearsal` (a throwaway that runs secretless and reports
   * REDIACC_ROLE=rehearsal, so apps degrade gracefully). `cluster rehearse` sets it.
   */
  role?: 'fork' | 'rehearsal';
  debug?: boolean;
}

/**
 * What a fork produced — enough to tear it down (cluster rehearse discards it).
 */
export interface ForkResult {
  /** Destination control-plane machine name. */
  destControl: string;
  /** The fork control-plane mount path (fork clone of ds-control-<cluster>). */
  forkMount: string;
  /** The fork control-plane networkID (its k3s unit). */
  networkId: number;
  /** Source cluster datastore names that were cloned (record keys are `<name>:<tag>`). */
  datastores: string[];
  /** The fork tag. */
  tag: string;
}

/** The fork datastore record key `<parent>:<tag>` (datastore attach/detach). */
function forkRecordName(parent: string, tag: string): string {
  return `${parent}:${tag}`;
}
/** The fork clone's mount path `/mnt/rediacc-ds/<parent>-<tag>`. */
function forkDatastoreMount(parent: string, tag: string): string {
  return `${NAMED_DS_BASE}/${parent}-${tag}`;
}

/** One datastore record from `renet datastore list --json`. */
interface DatastoreRecord {
  name: string;
  backend: string;
  cluster?: string;
  fork?: unknown;
  implicit?: boolean;
}

/**
 * List the source cluster's CEPH-backed, non-fork datastores (the control
 * datastore + every data datastore) — the group-snap membership and the set to
 * clone. Read from the machine registry via `datastore_list`; the control
 * datastore `ds-control-<cluster>` is guaranteed present first.
 */
async function listClusterCephDatastores(
  machineName: string,
  clusterName: string,
  debug?: boolean
): Promise<string[]> {
  const res = await dispatch('datastore_list', machineName, {}, { debug, capture: true });
  // datastore_list shells out to `renet datastore list --json`; captured stdout is
  // the `[datastore_list] [...]` bridge relay format — strip the prefix (finding #10).
  const records = parseCapturedJson<DatastoreRecord[]>(res.stdout);
  const members = records
    .filter((r) => !r.implicit && !r.fork && r.backend === 'ceph' && r.cluster === clusterName)
    .map((r) => r.name);
  if (members.length === 0) {
    throw new Error(
      `Cluster "${clusterName}" has no ceph-backed datastores to fork. The whole-cluster ` +
        `fork requires an rbd-backed control datastore (created by "cluster create" on ceph); ` +
        `a local-tier cluster forks per-repo by reflink instead.`
    );
  }
  // Deterministic order: control datastore first, then data datastores sorted.
  const control = controlDatastore(clusterName);
  return [...members.filter((m) => m === control), ...members.filter((m) => m !== control).sort()];
}

/**
 * Fork a whole cluster onto a destination cluster's nodes — the ANCHOR+REJOIN
 * model (04 §2, promoted from the P2-A proven battery). The control-plane image
 * IS the cluster, so we move the ANCHOR (a crash-consistent group snapshot of the
 * cluster's datastores — the parent NEVER stops) and let agents REJOIN fresh with
 * the new-CA token. This is F1-safe by construction: the control-plane identity
 * rewrite runs `--operation fork`, which re-mints the whole PKI and scrubs
 * secrets, so the fork can NEVER carry the parent cluster's CA key.
 *
 * dstAgents >= srcAgents no longer applies: destination node count is free (1..N).
 * Same-machine forks stay forbidden (two k3s cannot share a host netns).
 */
export async function forkCluster(
  clusterName: string,
  options: ForkClusterOptions
): Promise<ForkResult> {
  const startTime = Date.now();
  const role = options.role ?? DEFAULTS.CLUSTER.FORK_ROLE;
  if (!options.cluster) {
    throw new Error(
      `A whole-cluster fork must land on distinct machines (two k3s cannot share a host netns). ` +
        `Provision or name a destination cluster and pass --cluster <dest>.`
    );
  }
  // Validate against the allowed set on a string-typed value: an unvalidated CLI
  // string (or a test bypassing the type) must still be rejected, but the typed
  // union would make the literal comparison "always false" to the checker.
  const writesRaw: string = options.writes ?? DEFAULTS.CLUSTER.FORK_WRITES;
  if (writesRaw !== 'local' && writesRaw !== 'ceph') {
    throw new Error(`--writes must be "local" or "ceph" (got "${writesRaw}").`);
  }
  const writes = writesRaw;

  const source = await getCluster(clusterName);
  const dest = await getCluster(options.cluster);
  const srcMembers = await resolveK8sMembers(clusterName, k8sPoolsOf(source));
  const dstMembers = await resolveK8sMembers(options.cluster, k8sPoolsOf(dest));
  const srcControl = srcMembers.find((m) => K8S_SERVER_ROLES.has(m.role));
  const dstControl = dstMembers.find((m) => K8S_SERVER_ROLES.has(m.role));
  const dstAgents = dstMembers.filter((m) => m.role === 'k8s-agent');
  if (!srcControl || !dstControl) {
    throw new Error(`Both "${clusterName}" and "${options.cluster}" need a k8s-server member.`);
  }

  // 0. Fail fast (finding #8): refuse a dest whose control node already runs its
  //    own k3s (:6443 collision) BEFORE any snapshot/clone work — dispatch
  //    nothing destructive on a bad target.
  await assertDestNotRunningOwnK3s(options.cluster, dstControl.name, options.debug);

  // 0b. Give the dest members SOURCE-ceph access + the rbd/sqlite3 tooling the
  //     adopt/attach + kine-scrub need (findings #7/#15) — createCluster only
  //     seeds a cluster's own nodes with its own ceph.
  await prepareForkDest(clusterName, source, dstMembers, options.debug);

  const snapshot = `fork-${options.tag}`;
  outputService.info(
    `Fork "${clusterName}" -> "${options.cluster}" [${options.tag}, writes=${writes}]: ` +
      `group snapshot (parent stays live)...`
  );

  // 1. ONE atomic, crash-consistent group snapshot across the cluster's ceph
  //    datastores. No drain, no stop — the parent never notices (04 §2 step 1).
  const clusterDatastores = await listClusterCephDatastores(
    srcControl.name,
    clusterName,
    options.debug
  );
  await dispatch(
    'datastore_snapshot_create',
    srcControl.name,
    { group: clusterName, snapshot },
    { debug: options.debug }
  );

  // 2. Clone each datastore from the group snap (clone-format-2 per-call). The
  //    fork records are `<ds>:<tag>` DETACHED (04 §2 step 2). datastore_fork
  //    registers the fork record ONLY in the SOURCE machine's registry; the attach
  //    below runs on the DEST, whose registry has no such record — so we ferry the
  //    record (the `datastore fork --json` output) to the dest and `datastore_adopt`
  //    it there before attaching (finding #14: cross-machine fork-record propagation).
  for (const ds of clusterDatastores) {
    const forkRes = await dispatch(
      'datastore_fork',
      srcControl.name,
      { parent: ds, tag: options.tag, snapshot, group: clusterName },
      { debug: options.debug, capture: true }
    );
    const record = parseCapturedJson<unknown>(forkRes.stdout);
    const recordB64 = Buffer.from(JSON.stringify(record)).toString('base64');
    await dispatch(
      'datastore_adopt',
      dstControl.name,
      { name: forkRecordName(ds, options.tag), record_b64: recordB64 },
      { debug: options.debug }
    );
  }

  // 3. Attach every clone on the destination control node with --writes composing
  //    (one beefy machine mounts all — 04 §2 step 3 / §3). `local` = ephemeral
  //    dm-COW overlay, `ceph` = durable RW clone.
  for (const ds of clusterDatastores) {
    await dispatch(
      'datastore_attach',
      dstControl.name,
      { name: forkRecordName(ds, options.tag), writes },
      { debug: options.debug }
    );
  }

  // 4. Control-plane identity rewrite, operation=FORK: the F1-safe 8-step PKI
  //    re-mint + secret scrub + ROLE=fork rewrite + stale-Node delete, with a NEW
  //    networkID (04 §2 step 4). The clone mounts at the stable-name path.
  const controlDs = controlDatastore(clusterName);
  const forkMount = forkDatastoreMount(controlDs, options.tag);
  const forkNet = await configService.allocateNetworkId();
  outputService.info(
    `  control-plane fork identity rewrite (PKI re-mint + scrub) on ${dstControl.name}...`
  );
  await dispatch(
    'kube_identity_rewrite',
    dstControl.name,
    {
      mount_path: forkMount,
      operation: 'fork',
      mode: 'server',
      new_node_ip: dstControl.ip,
      new_network_id: forkNet,
      role,
      writes,
    },
    { debug: options.debug }
  );

  // 5. Fresh agents REJOIN the fork with the NEW-CA token (04 §2 step 5; agents
  //    are disposable, dst count is free). The fork's F8 already deleted the
  //    parent's stale Node objects, so fresh agents register clean.
  const tokenRes = await dispatch(
    'kube_join_token',
    dstControl.name,
    { mount_path: forkMount },
    { debug: options.debug, capture: true }
  );
  const token = /K10[^"\s]+/.exec(tokenRes.stdout ?? '')?.[0];
  if (!token) throw new Error('Could not read the fork control-plane join token.');
  const forkEndpoint = serverUrl(dstControl.ip);
  for (const agent of dstAgents) {
    outputService.info(`  fresh agent join ${agent.name} (${agent.ip})...`);
    const agentNet = await createNodeImage(
      agent,
      options.cluster,
      poolSize(k8sPoolsOf(dest), agent.pool),
      options.debug
    );
    await dispatch(
      'kube_join',
      agent.name,
      {
        mount_path: clusterMount(options.cluster),
        network_id: agentNet,
        role: 'agent',
        token,
        endpoint: forkEndpoint,
        bind_ip: agent.ip,
      },
      { debug: options.debug }
    );
  }

  // 6. --up + health gate (04 §4): gate the fork control plane on readiness before
  //    declaring success (the rollback window — the parent is untouched throughout).
  if (options.up) {
    await clusterHealthGate(dstControl.name, forkMount, options.debug);
  }

  auditService.recordOperation({
    functionName: 'cluster_fork',
    machineName: clusterName,
    success: true,
    exitCode: 0,
    durationMs: Date.now() - startTime,
  });
  outputService.success(
    `Cluster "${clusterName}" forked as "${options.tag}" onto "${options.cluster}" ` +
      `(${clusterDatastores.length} datastore(s), ${dstAgents.length} agent(s), writes=${writes}, ` +
      `role=${role}) — PKI re-minted, parent untouched.`
  );
  return {
    destControl: dstControl.name,
    forkMount,
    networkId: forkNet,
    datastores: clusterDatastores,
    tag: options.tag,
  };
}

/** Per-attempt gate timeout + total window (04 §4 / gate C5 defaults). */
const HEALTH_GATE_ATTEMPT_MS = 30_000;
const HEALTH_GATE_WINDOW_MS = 300_000;

/**
 * Gate on the cluster control plane becoming healthy (04 §4 layer 1: the distro
 * /readyz healthcheck), retrying until the window expires. Used by fork --up and
 * migrate to confirm the destination serves before releasing the source. Throws
 * on window expiry so the caller keeps the rollback source intact.
 */
async function clusterHealthGate(
  machineName: string,
  mountPath: string,
  debug?: boolean
): Promise<void> {
  const deadline = gateNow() + HEALTH_GATE_WINDOW_MS;
  let lastErr = '';
  while (gateNow() < deadline) {
    const res = await localExecutorService.execute({
      functionName: 'kube_health',
      machineName,
      params: { mount_path: mountPath },
      captureOutput: true,
      debug,
    });
    if (res.success) return;
    lastErr = res.error ?? DEFAULTS.CLOUD.UNKNOWN_ERROR;
    await delay(HEALTH_GATE_ATTEMPT_MS);
  }
  throw new Error(`Cluster health gate did not pass within ${HEALTH_GATE_WINDOW_MS}ms: ${lastErr}`);
}

/** Injectable delay + clock (overridden in tests to avoid real waits/wall-clock). */
let delay: (ms: number) => Promise<void> = (ms) => new Promise((r) => setTimeout(r, ms));
let gateNow: () => number = Date.now;
/** Test seam: replace the health-gate delay. */
export function __setHealthGateDelay(fn: (ms: number) => Promise<void>): void {
  delay = fn;
}
/** Test seam: replace the health-gate clock (so a failing gate expires fast). */
export function __setHealthGateClock(fn: () => number): void {
  gateNow = fn;
}

export interface RehearseClusterOptions {
  /** Destination cluster whose nodes host the throwaway rehearsal fork. */
  cluster?: string;
  /** Optional tag for the rehearsal fork (default a timestamped one). */
  tag?: string;
  debug?: boolean;
}

/**
 * Rehearse a cluster: boot an EPHEMERAL throwaway fork of the latest state on a
 * destination, health-gate it, report, and DISCARD it (05 §2 rung 1 + 04 §4).
 * This is a thin wrapper over `forkCluster` with `--writes local` (zero Ceph
 * footprint) + `role=rehearsal` (the fork runs SECRETLESS — apps see
 * REDIACC_ROLE=rehearsal and degrade gracefully) + `--up` (health gate). It is
 * the "costs ~nothing, catches most" pre-release rung: a fork rehearsal proves a
 * release/upgrade boots healthy before it touches the live cluster. The parent is
 * never stopped; the rehearsal is always torn down (best-effort discard even on a
 * failed gate, so a rehearsal never leaves state behind).
 */
export async function rehearseCluster(
  clusterName: string,
  options: RehearseClusterOptions
): Promise<void> {
  const tag = options.tag ?? `rehearse-${Date.now()}`;
  outputService.info(
    `Rehearse "${clusterName}" [${tag}] on "${options.cluster}" (ephemeral fork)...`
  );

  let result: ForkResult;
  try {
    result = await forkCluster(clusterName, {
      tag,
      cluster: options.cluster,
      writes: 'local',
      role: 'rehearsal',
      up: true,
      debug: options.debug,
    });
  } catch (err) {
    // A failed fork/gate still tries to discard whatever partial state exists.
    await discardRehearsal(options.cluster, clusterName, tag, options.debug);
    throw err;
  }

  outputService.success(
    `Rehearsal "${clusterName}" [${tag}] passed the health gate (secretless, role=rehearsal). Discarding...`
  );
  await discardRehearsal(result.destControl, clusterName, tag, options.debug, result);
  outputService.success(`Rehearsal "${clusterName}" [${tag}] discarded — no residue.`);
}

/**
 * Tear down a rehearsal fork: uninstall the fork's k3s control plane, then
 * `datastore detach --discard` every fork clone (removes the overlay/clone + the
 * record). Best-effort per step so a partial rehearsal still cleans up.
 */
async function discardRehearsal(
  destControl: string | undefined,
  clusterName: string,
  tag: string,
  debug?: boolean,
  result?: ForkResult
): Promise<void> {
  if (!destControl) return;
  const forkMount = result?.forkMount ?? forkDatastoreMount(controlDatastore(clusterName), tag);
  // The datastores to discard: from the fork result, else re-derive from the
  // registry (a partial rehearsal that failed before returning a result).
  let datastores = result?.datastores;
  if (!datastores) {
    try {
      datastores = await listClusterCephDatastores(destControl, clusterName, debug);
    } catch {
      datastores = [controlDatastore(clusterName)];
    }
  }
  await tryDispatch('kube_uninstall', destControl, { mount_path: forkMount }, debug);
  for (const ds of datastores) {
    await tryDispatch(
      'datastore_detach',
      destControl,
      { name: forkRecordName(ds, tag), discard: true },
      debug
    );
  }
}

/** Dispatch a teardown step, swallowing failures (discard is best-effort). */
async function tryDispatch(
  functionName: string,
  machineName: string,
  params: Record<string, unknown>,
  debug?: boolean
): Promise<void> {
  try {
    await localExecutorService.execute({ functionName, machineName, params, debug });
  } catch (err) {
    outputService.warn(`  discard: ${functionName} on ${machineName} failed (continuing): ${err}`);
  }
}

export interface MigrateClusterOptions {
  to: string;
  debug?: boolean;
}

/**
 * Migrate a cluster's control plane to another machine — the anchor-model
 * IN-CEPH FENCED REMAP (04 §3): a pure datastore failover with ZERO data copy.
 * The control-plane data-dir lives in the rbd-backed control datastore, so
 * relocating it is: down() the source CP → detach the datastore (release its
 * exclusive lock) → attach on the destination (FENCING any stale holder) →
 * identity rewrite `--operation migrate` (CA PRESERVED — same principal —
 * networkID KEPT, IP-only) → health-gate the destination before declaring done.
 * Node-to-node moves inside one Ceph reach stop being "migrate" and become this
 * failover; today's backup_push block transfer disappears for this case.
 *
 * Cross-site migrate (different Ceph reach: rbd-mirror / iterated export-diff
 * between separate ceph clusters, or ceph→local) needs a datastore-level transfer
 * transport that is NOT a landed primitive (the old backup_push was repo-image
 * level, from the pre-anchor model) — it is a documented P3 follow-up; this path
 * refuses cleanly rather than do a half-correct transfer.
 */
export async function migrateCluster(
  clusterName: string,
  options: MigrateClusterOptions
): Promise<void> {
  const startTime = Date.now();
  const source = await getCluster(clusterName);
  const members = await resolveK8sMembers(clusterName, k8sPoolsOf(source));
  const control = members.find((m) => K8S_SERVER_ROLES.has(m.role));
  if (!control) throw new Error(`Cluster "${clusterName}" has no k8s-server member to migrate.`);

  // The anchor control datastore must be ceph-backed for the in-Ceph remap.
  if (resolveControlDsBackend(source, {}) !== 'ceph') {
    throw new Error(
      `cluster migrate "${clusterName}" currently supports the in-Ceph fenced remap only ` +
        `(ceph-backed control datastore). Cross-site / local-tier cluster migrate (datastore ` +
        `transfer via rbd-mirror or export-diff) is a P3 follow-up.`
    );
  }

  const destMachine = await configService.getLocalMachine(options.to);
  const controlDs = controlDatastore(clusterName);
  const controlDsMount = controlDatastoreMount(clusterName);
  const downStart = Date.now();

  outputService.info(
    `Migrate "${clusterName}" -> "${options.to}" (in-Ceph fenced remap, zero copy)...`
  );

  // 1. down() the source control plane so the datastore is consistent before the
  //    lock is released (04 §4 step 0 — a clean shutdown, not a crash).
  await dispatch(
    'kube_prep_fork',
    control.name,
    { mount_path: controlDsMount, node: '' },
    { debug: options.debug }
  );

  // 2. Detach the control datastore from the source (release its exclusive lock).
  await dispatch('datastore_detach', control.name, { name: controlDs }, { debug: options.debug });

  // 3. Attach on the destination, FENCING any stale holder (rbd lock break + osd
  //    blocklist). Same mount path (mount-path stability, 04 §6) — PV objects in
  //    kine reference it and need zero rewriting.
  await dispatch(
    'datastore_attach',
    options.to,
    { name: controlDs, force: true },
    { debug: options.debug }
  );

  // 4. Identity rewrite operation=migrate: CA PRESERVED, networkID KEPT (no
  //    new_network_id), serving leaf regenerated for the new IP, secrets stay.
  await dispatch(
    'kube_identity_rewrite',
    options.to,
    {
      mount_path: controlDsMount,
      operation: 'migrate',
      mode: 'server',
      new_node_ip: destMachine.ip,
    },
    { debug: options.debug }
  );

  // 5. Health-gate the destination control plane before declaring done — the
  //    rollback window (04 §4 step 4): the source is only released once the gate
  //    passes (here the datastore already moved, so a gate failure is surfaced
  //    loudly for operator recovery rather than silently succeeding).
  await clusterHealthGate(options.to, controlDsMount, options.debug);

  const downtimeMs = Date.now() - downStart;
  auditService.recordOperation({
    functionName: 'cluster_migrate',
    machineName: clusterName,
    success: true,
    exitCode: 0,
    durationMs: Date.now() - startTime,
  });
  outputService.success(
    `Cluster "${clusterName}" migrated to "${options.to}" (zero-copy in-Ceph remap). ` +
      `Cutover downtime: ${(downtimeMs / 1000).toFixed(1)}s.`
  );
}

/**
 * Scale a k8s pool: add agents (join) or remove agents (drain + node remove).
 * Ceph pool scaling is reported as a follow-up (cephadm orch host add/OSD).
 */
export async function scaleK8sPool(
  clusterName: string,
  pool: ClusterPool,
  targetCount: number,
  currentCount: number,
  debug?: boolean
): Promise<void> {
  const cluster = await getCluster(clusterName);
  const members = await resolveK8sMembers(clusterName, k8sPoolsOf(cluster));
  const control = members.find((m) => K8S_SERVER_ROLES.has(m.role));
  if (!control) throw new Error(`Cluster "${clusterName}" has no control plane to scale against.`);
  const mount = clusterMount(clusterName);

  if (targetCount > currentCount) {
    const tokenRes = await dispatch(
      'kube_join_token',
      control.name,
      { mount_path: mount, network_id: 0 },
      { debug, capture: true }
    );
    const token = /K10[^"\s]+/.exec(tokenRes.stdout ?? '')?.[0];
    if (!token) throw new Error('Could not read the join token for scale-up.');
    for (let i = currentCount + 1; i <= targetCount; i++) {
      const name = `${clusterName}-${pool.name}-${i}`;
      const machine = await configService.getLocalMachine(name);
      const net = await configService.allocateNetworkId();
      await dispatch(
        'repository_create',
        name,
        {
          repository: clusterRepo(clusterName),
          size: pool.size ?? DEFAULT_NODE_SIZE,
          guid: randomUUID(),
          network_id: net,
          start_docker: false,
        },
        { debug }
      );
      await dispatch(
        'kube_join',
        name,
        {
          mount_path: mount,
          network_id: net,
          role: 'agent',
          token,
          endpoint: serverUrl(control.ip),
          bind_ip: machine.ip,
        },
        { debug }
      );
    }
  } else {
    for (let i = currentCount; i > targetCount; i--) {
      const name = `${clusterName}-${pool.name}-${i}`;
      await dispatch('kube_prep_fork', name, { mount_path: mount, node: name }, { debug });
      await dispatch(
        'kube_node_remove',
        control.name,
        { mount_path: mount, node: name },
        { debug }
      );
    }
  }
}
