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

import { DEFAULTS } from '@rediacc/shared/config';
import type { ClusterConfig, ClusterPool } from '../../types/index.js';
import { getCluster } from '../config/config-cluster-ops.js';
import { configService } from '../config/config-resources.js';
import { outputService } from '../core/output.js';
import { type ExecuteResult, getExecutor } from '../executor/executor-factory.js';
import { dispatchCeph, exportCephClientConfig, resolveCephMembers } from './cluster-ceph.js';

const MOUNT_BASE = '/mnt/rediacc/mounts';
export const NAMED_DS_BASE = '/mnt/rediacc-ds';
const API_PORT = 6443;
/** Default size of the anchor control datastore (spec 03 gate-fixed: 10 GiB). */
const CONTROL_DS_DEFAULT_SIZE = '10G';
/**
 * The Ceph CLI cluster name (distinct from the rediacc cluster name). renet's
 * ceph_* functions default it to "rediacc", but the datastore/rbd paths assume
 * "ceph", so we pass it explicitly (mirrors cluster-provision's CEPH_CLUSTER_NAME).
 */
const CEPH_CLI_CLUSTER = 'ceph';

/** k3s server + agent roles (hyperconverged nodes run a server too). */
export const K8S_SERVER_ROLES = new Set(['k8s-server', 'hyperconverged']);

export interface K8sMember {
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
export function clusterMount(clusterName: string): string {
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
export function serverUrl(ip: string): string {
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
export function resolveControlDsBackend(
  cluster: ClusterConfig,
  opts: ControlDatastoreOptions
): 'local' | 'ceph' {
  if (opts.backend) return opts.backend;
  return cluster.pools.some((p) => p.role === 'ceph') ? 'ceph' : 'local';
}

/** Resolve a cluster's k8s pool members (name + private IP) in pool/index order. */
export async function resolveK8sMembers(
  clusterName: string,
  pools: ClusterPool[]
): Promise<K8sMember[]> {
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

export function k8sPoolsOf(cluster: ClusterConfig): ClusterPool[] {
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
export async function assertDestNotRunningOwnK3s(
  destCluster: string,
  dstControlName: string,
  debug?: boolean
): Promise<void> {
  const ownMount = controlDatastoreMount(destCluster);
  const res = await getExecutor().execute({
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
        `(rdc cluster destroy ${destCluster}, or uninstall its k3s) — then retry.`
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
export async function prepareForkDest(
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
 * Give a MIGRATE dest machine access to the SOURCE cluster's Ceph before the
 * fenced attach (finding #19 — the #7/#15 seeding class, migrate arm). The in-Ceph
 * remap maps the SAME rbd image (ds-control-<cluster>) on the destination, which
 * needs the source `/etc/ceph` client config + the `rbd`/sqlite3 tooling the attach
 * shells out to. createCluster only seeds a cluster's OWN nodes with its OWN ceph,
 * so a fresh bare dest of a DIFFERENT machine has neither — mirroring the fork
 * dest's gap. Single machine (migrate moves one CP), so it seeds just `destMachine`.
 * A local-tier source has no ceph pool and never reaches here (the ceph-backend
 * guard rejects it first).
 */
export async function prepareMigrateDest(
  sourceClusterName: string,
  source: ClusterConfig,
  destMachine: string,
  debug?: boolean
): Promise<void> {
  const cephPools = cephPoolsOf(source);
  if (cephPools.length === 0) return;
  const cephMembers = await resolveCephMembers(sourceClusterName, cephPools);
  if (cephMembers.length === 0) return;
  const mon = cephMembers[0];

  outputService.info(
    `  seeding migrate dest "${destMachine}" with source "${sourceClusterName}" ceph access (from ${mon.name})...`
  );
  const payload = await exportCephClientConfig(mon.name, debug);
  await dispatchCeph('kube_fork_dest_prep', destMachine, {}, debug);
  await dispatchCeph(
    'ceph_client_config_install',
    destMachine,
    { conf: payload.conf, keyring: payload.keyring },
    debug
  );
}

/**
 * Dispatch one internal kube_ or repository_ bridge function to a member,
 * throwing on any non-success. captureOutput returns renet's stdout (used to
 * read the join token).
 */
export async function dispatch(
  functionName: string,
  machineName: string,
  params: Record<string, unknown>,
  opts: { debug?: boolean; capture?: boolean } = {}
): Promise<ExecuteResult> {
  const result = await getExecutor().execute({
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

/**
 * The networkID an agent node's k3s unit runs under (`rediacc-k3s-<networkID>`
 * plus its dedicated node interface). Allocation only: no repo, no volume.
 *
 * ★ #25: agent nodes used to get a per-node "cluster image" repo here, sized from
 * the pool, purely to own this mount path. It bought nothing. An agent's k3s state
 * is kubelet + containerd + pod scratch, which is a DISPOSABLE CACHE: the cluster's
 * real state lives in the control plane's anchor datastore (`ds-control-<cluster>`,
 * spec 02 §1), and a lost agent is replaced by rejoining a fresh one, never by
 * restoring its disk. The repo also bought no encryption worth having, since the
 * agent's secrets arrive from the API server at runtime either way. Meanwhile it
 * cost a LUKS volume, a GUID, a config record and a size decision per node.
 *
 * `renet kube join` MkdirAll's its own data-dir under the mount path
 * (`K3sDistro.Install`), so the join contract is UNCHANGED by dropping the repo:
 * the agent simply gets a plain directory instead of a LUKS mount. The networkID
 * is still allocated (it names the systemd unit and the node interface), and the
 * allocator's forward counter is persistent, so no id is ever handed out twice.
 */
export async function allocateAgentNetworkId(): Promise<number> {
  return configService.allocateNetworkId();
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
    const agentNet = await allocateAgentNetworkId();
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
      const net = await allocateAgentNetworkId();
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
