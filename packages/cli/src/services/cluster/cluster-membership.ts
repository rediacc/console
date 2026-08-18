/**
 * Cluster membership verbs (P2 §P2 items 4-5, spec 03 §5.5):
 *   - join <machine> --cluster <c>: adopt an EXISTING registered machine as a
 *     k3s agent node, riding the same CA-derived join token as anchor+rejoin.
 *   - evict <machine>: the codified drain -> delete-Node -> deregister sequence
 *     (02 §3 / 05 §4). It refuses a machine that still mounts a named datastore,
 *     teaching the operator to move the datastore first (single-mounter model).
 *
 * These sit above the renet kube_* / repository_* bridge primitives and set /
 * clear the machine's `cluster` membership backref (schema MachineClusterRef),
 * the same field `repo create --machine` refuses on (R2-F12). Final CLI naming
 * is P4; the command shapes here follow current conventions.
 */

import { DEFAULTS } from '@rediacc/shared/config';
import type { ClusterConfig, ClusterPool } from '../../types/index.js';
import { assertMachineSlotsAvailable } from '../account/license-preflight.js';
import { getCluster } from '../config/config-cluster-ops.js';
import { configService } from '../config/config-resources.js';
import { auditService } from '../core/audit.js';
import { outputService } from '../core/output.js';
import { type ExecuteResult, getExecutor } from '../executor/executor-factory.js';
import { allocateAgentNetworkId } from './cluster-kube.js';

const MOUNT_BASE = '/mnt/rediacc/mounts';
const NAMED_DS_BASE = '/mnt/rediacc-ds';
const API_PORT = 6443;

/**
 * The agent's per-node k3s image (a disposable repo) is mounted here; the
 * control-plane data-dir instead rides the anchor `ds-control-<cluster>`
 * datastore (02 §1 / anchor model), whose mount the token read + node ops use.
 */
function clusterMount(clusterName: string): string {
  return `${MOUNT_BASE}/${clusterName}`;
}
function controlDatastoreMount(clusterName: string): string {
  return `${NAMED_DS_BASE}/ds-control-${clusterName}`;
}
function serverUrl(ip: string): string {
  return `https://${ip}:${API_PORT}`;
}

/** Dispatch one internal bridge function to a member, throwing on failure. */
async function dispatch(
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
      `Membership step "${functionName}" failed on ${machineName}: ${result.error ?? DEFAULTS.CLOUD.UNKNOWN_ERROR}`
    );
  }
  return result;
}

/** The first control-plane (k3s server / hyperconverged) member of a cluster. */
function controlMember(clusterName: string, cluster: ClusterConfig): { name: string } {
  if (cluster.controlNode) return { name: cluster.controlNode };
  const pool = cluster.pools.find((p) => p.role === 'k8s-server' || p.role === 'hyperconverged');
  if (!pool) {
    throw new Error(
      `Cluster "${clusterName}" has no k8s-server or hyperconverged pool to host the control plane.`
    );
  }
  return { name: `${clusterName}-${pool.name}-1` };
}

/** The agent pool an adopted node is recorded against (the membership backref). */
function agentPool(clusterName: string, cluster: ClusterConfig): ClusterPool {
  const pool = cluster.pools.find((p) => p.role === 'k8s-agent');
  if (!pool) {
    throw new Error(
      `Cluster "${clusterName}" has no k8s-agent pool. Add one before adopting an agent node.`
    );
  }
  return pool;
}

// Carry-in 1 seam note: the datastore node label (rediacc.io/ds-<name>) is
// stamped/stripped through the renet `kube_node_label` bridge function (control
// plane admin kubectl, node resolved by InternalIP). Because node labels persist
// in kine across a same-node reboot, only RELOCATION/failover re-stamps them
// (remove-before-add). The `datastore attach`/`detach` porcelain that wires this
// dispatch is P4; until then it is exercised via the renet primitive directly.

export interface JoinClusterOptions {
  cluster: string;
  debug?: boolean;
}

/**
 * Adopt an existing registered machine as a k3s agent node. Idempotent: a
 * machine already in THIS cluster is a success no-op (spec 03 §5.5).
 */
export async function joinCluster(machineName: string, options: JoinClusterOptions): Promise<void> {
  const startTime = Date.now();
  const machine = await configService.getLocalMachine(machineName);
  if (machine.cluster) {
    if (machine.cluster.cluster === options.cluster) {
      outputService.success(`"${machineName}" is already a member of "${options.cluster}".`);
      return;
    }
    throw new Error(
      `"${machineName}" is already a member of cluster "${machine.cluster.cluster}". ` +
        `Evict it first: rdc cluster evict ${machineName}.`
    );
  }

  // One more machine that will hold repositories, so one more slot.
  await assertMachineSlotsAvailable({ machineCount: 1 });

  const cluster = await getCluster(options.cluster);
  const control = controlMember(options.cluster, cluster);
  const controlMachine = await configService.getLocalMachine(control.name);
  const pool = agentPool(options.cluster, cluster);
  const agentMount = clusterMount(options.cluster);
  const controlMount = controlDatastoreMount(options.cluster);

  outputService.info(
    `Joining "${machineName}" (${machine.ip}) to cluster "${options.cluster}" as an agent...`
  );

  // The CA-derived join token is read from the control plane's anchor datastore.
  const tokenRes = await dispatch(
    'kube_join_token',
    control.name,
    { mount_path: controlMount },
    { debug: options.debug, capture: true }
  );
  const token = /K10[^"\s]+/.exec(tokenRes.stdout ?? '')?.[0];
  if (!token) {
    throw new Error(`Could not read the k3s join token from ${control.name}.`);
  }

  // ★ #25: no per-node repo. An adopted agent's k3s state is a disposable cache;
  // `renet kube join` creates its own data-dir under the mount path. Only the
  // networkID (its systemd unit + node interface) is allocated. See
  // allocateAgentNetworkId in cluster-kube.ts for the full reasoning.
  const net = await allocateAgentNetworkId();
  await dispatch(
    'kube_join',
    machineName,
    {
      mount_path: agentMount,
      network_id: net,
      role: 'agent',
      token,
      endpoint: serverUrl(controlMachine.ip),
      bind_ip: machine.ip,
    },
    { debug: options.debug }
  );

  // Record the membership backref (repo create --machine refuses on it, R2-F12).
  await configService.updateMachine(machineName, {
    cluster: { cluster: options.cluster, pool: pool.name },
  });

  auditService.recordOperation({
    functionName: 'cluster_join',
    machineName,
    success: true,
    exitCode: 0,
    durationMs: Date.now() - startTime,
  });
  outputService.success(`"${machineName}" joined cluster "${options.cluster}" as an agent.`);
}

export interface EvictClusterOptions {
  force?: boolean;
  debug?: boolean;
}

/** Named datastores this machine currently mounts, per the state routing hint. */
async function attachedDatastoresOn(machineName: string): Promise<string[]> {
  const cfg = await configService.getCurrent();
  const datastores = cfg?.state?.datastores ?? {};
  return Object.entries(datastores)
    .filter(([, d]) => d.attachedTo === machineName)
    .map(([name]) => name);
}

/**
 * Remove a node from its cluster via the codified drain -> delete-Node ->
 * deregister sequence (02 §3). The cluster is derived from the machine's
 * membership backref; there is no --cluster flag. Refuses a machine that still
 * mounts a named datastore (single-mounter: move it first, spec 03 §5.5).
 */
export async function evictCluster(
  machineName: string,
  options: EvictClusterOptions
): Promise<void> {
  const startTime = Date.now();
  const machine = await configService.getLocalMachine(machineName);
  if (!machine.cluster) {
    throw new Error(`"${machineName}" is not a member of any cluster.`);
  }
  const clusterName = machine.cluster.cluster;

  const held = await attachedDatastoresOn(machineName);
  if (held.length > 0) {
    // Single-mounter safety (spec 03 §5.5): refuse a node that still mounts a
    // named datastore, unless --force — the honest path for a DEAD node whose
    // datastore must be recovered/fenced separately (it will not detach cleanly).
    if (options.force) {
      outputService.warn(
        `--force: evicting "${machineName}" despite held datastore(s) ${held.join(', ')}. ` +
          `They must be moved/fenced separately (rdc datastore attach <ds> --to <other> --force).`
      );
    } else {
      throw new Error(
        `"${machineName}" still mounts datastore(s) ${held.join(', ')}. Move them first: ` +
          `rdc datastore attach ${held[0]} --to <other-machine>, then evict (or --force for a dead node).`
      );
    }
  }

  const cluster = await getCluster(clusterName);
  const control = controlMember(clusterName, cluster);
  const controlMount = controlDatastoreMount(clusterName);

  outputService.info(`Evicting "${machineName}" (${machine.ip}) from cluster "${clusterName}"...`);

  // Drain + delete the Node object on the control plane, resolving the node by
  // its InternalIP (k3s names nodes by hostname, not the config name). renet's
  // kube_node_remove already force-drains (--force --delete-emptydir-data), so a
  // reachable node always drains; an unreachable one is deleted regardless.
  await dispatch(
    'kube_node_remove',
    control.name,
    { mount_path: controlMount, node_ip: machine.ip },
    { debug: options.debug }
  );

  // ★ #20: the control plane forgetting the Node is only HALF an eviction. The
  // evicted machine still runs its own k3s agent (systemd unit, kubelet, its
  // containers) against a cluster that no longer knows it, and it would try to
  // rejoin on reboot. Uninstall the node-side k3s ON THE EVICTED MACHINE, against
  // its own cluster image mount. Best-effort: a DEAD node cannot be reached, and
  // refusing to finish the eviction because the corpse will not answer is exactly
  // the failure --force exists for. The control-plane half already succeeded, so
  // the machine is out of the cluster either way.
  try {
    await dispatch(
      'kube_uninstall',
      machineName,
      { mount_path: clusterMount(clusterName) },
      { debug: options.debug }
    );
  } catch (err) {
    outputService.warn(
      `Node-side k3s uninstall on "${machineName}" failed (continuing): ${err}. ` +
        `The node is out of the cluster, but it may still run a stale k3s agent; ` +
        `re-adopting it with "rdc cluster join" needs that cleaned up first.`
    );
  }

  // Deregister: clear the membership backref.
  await configService.updateMachine(machineName, { cluster: undefined });

  auditService.recordOperation({
    functionName: 'cluster_evict',
    machineName,
    success: true,
    exitCode: 0,
    durationMs: Date.now() - startTime,
  });
  outputService.success(`"${machineName}" evicted from cluster "${clusterName}".`);
}
