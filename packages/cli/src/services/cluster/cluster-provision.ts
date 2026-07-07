/**
 * Cluster provisioning lifecycle.
 *
 * createCluster mirrors createCloudMachine but for a set of pool members on a
 * private LAN. The cloud (OpenTofu) path is complete; KVM routes to the
 * wave-8 ops seam. Component install (ceph/k8s) and scale are gated seams: the
 * renet contract functions they dispatch land in later waves (see the
 * per-callsite TODOs). Members materialize into resources.machines so every
 * existing `-m` command works on them.
 */

import { homedir } from 'node:os';
import { join } from 'node:path';
import { readFile } from 'node:fs/promises';
import { DEFAULTS } from '@rediacc/shared/config';
import type { ClusterConfig, ClusterPool } from '../../types/index.js';
import { configService } from '../config/config-resources.js';
import { localExecutorService } from '../executor/local-executor.js';
import {
  getCluster,
  materializeClusterMachines,
  resolveControlNode,
} from '../config/config-cluster-ops.js';
import { outputService } from '../core/output.js';
import { auditService } from '../core/audit.js';
import {
  ensureClusterDnsRecords,
  pushInfraConfig,
  removeClusterDnsRecords,
} from '../provision/infra-provision.js';
import { installK8s, scaleK8sPool } from './cluster-kube.js';
import { bootstrapMachine, scanHostKeys, waitForSSH } from '../renet/machine-bootstrap.js';
import { TofuExecutor } from '../tofu/executor.js';
import { isKvmProvider, resolveProviderMapping } from '../tofu/provider-resolver.js';
import { generateClusterTfJson } from '../tofu/cluster-tf-generator.js';
import { provisionKvmCluster } from './kvm-provisioner.js';

const TOFU_CLUSTER_DIR = join(homedir(), '.config', 'rediacc', 'tofu', 'clusters');

export interface CreateClusterOptions {
  sshUser?: string;
  /** Base domain for the cluster's public DNS (else inherited from a sibling machine). */
  baseDomain?: string;
  debug?: boolean;
}

interface ResolvedMember {
  pool: string;
  index: number;
  ip: string;
}

function clusterTofuDir(clusterName: string): string {
  return join(TOFU_CLUSTER_DIR, clusterName);
}

async function loadSSHPublicKey(): Promise<string> {
  const localConfig = await configService.getLocalConfig();
  let sshPublicKey = localConfig.sshPublicKey;
  if (!sshPublicKey && localConfig.ssh.publicKeyPath) {
    sshPublicKey = (await readFile(localConfig.ssh.publicKeyPath, 'utf-8')).trim();
  }
  if (!sshPublicKey) {
    throw new Error(
      'SSH public key required for cluster provisioning. Set with: rdc config init --name <name> --ssh-key <path>'
    );
  }
  return sshPublicKey;
}

/** Provision pool members on a cloud provider via OpenTofu; return their IPs. */
async function provisionCloud(
  clusterName: string,
  cluster: ClusterConfig,
  debug?: boolean
): Promise<ResolvedMember[]> {
  const current = await configService.getCurrent();
  const providerConfig = current?.resources?.cloudProviders?.[cluster.provider];
  if (!providerConfig) {
    throw new Error(
      `Cluster "${clusterName}" references cloud provider "${cluster.provider}", which is not configured. Add it with: rdc config cloud-provider add`
    );
  }

  const mapping = resolveProviderMapping(providerConfig);
  const sshPublicKey = await loadSSHPublicKey();
  await TofuExecutor.resolveBinary();

  const tfConfig = generateClusterTfJson({
    clusterName,
    mapping,
    apiToken: providerConfig.apiToken,
    sshPublicKey,
    network: cluster.network,
    pools: cluster.pools,
  });

  const executor = new TofuExecutor(clusterTofuDir(clusterName));
  await executor.writeConfig(tfConfig);
  outputService.info(`Provisioning cluster "${clusterName}" on ${cluster.provider}...`);
  await executor.init({ debug });
  await executor.apply({ debug });

  // Widen to `| undefined` so the per-member lookup below is legitimately
  // guarded (a missing output means tofu produced no IP for that member).
  const outputs: Record<string, { value: unknown } | undefined> = await executor.getOutputs();
  const members: ResolvedMember[] = [];
  for (const pool of cluster.pools) {
    for (let i = 1; i <= pool.count; i++) {
      const ip = String(outputs[`ipv4_${pool.name}_${i}`]?.value ?? '');
      if (!ip) {
        throw new Error(`OpenTofu apply produced no IPv4 for member ${pool.name}-${i}`);
      }
      members.push({ pool: pool.name, index: i, ip });
    }
  }
  return members;
}

/** Wait for SSH, record host keys, and run renet setup on every member. */
async function bootstrapMembers(
  clusterName: string,
  members: ResolvedMember[],
  sshUser: string,
  debug?: boolean
): Promise<void> {
  const sshPort = DEFAULTS.SSH.PORT;
  for (const m of members) {
    const machineName = `${clusterName}-${m.pool}-${m.index}`;
    outputService.info(`Waiting for SSH on ${machineName} (${m.ip})...`);
    await waitForSSH(m.ip, sshPort);
    const keyscan = scanHostKeys(m.ip, sshPort);
    if (keyscan) await configService.updateMachine(machineName, { knownHosts: keyscan });
    outputService.info(`Setting up ${machineName}...`);
    await bootstrapMachine(machineName, { debug });
  }
  void sshUser;
}

/**
 * The Ceph cluster name is a fixed identity ("ceph") that is distinct from the
 * rediacc cluster name: renet's ceph_* functions default it to "rediacc", but
 * the datastore/CSI paths assume "ceph", so we pass it explicitly.
 */
const CEPH_CLUSTER_NAME = 'ceph';

/** A materialized ceph-pool member: its config machine name and private IP. */
interface CephMember {
  name: string;
  ip: string;
}

/**
 * Dispatch one internal ceph_* bridge function to a member machine. Throws a
 * clear error (including renet's own failure message) on any non-success so a
 * failed ceph install surfaces instead of silently warning.
 */
async function dispatchCeph(
  functionName: string,
  machineName: string,
  params: Record<string, unknown>,
  debug?: boolean
): Promise<void> {
  const result = await localExecutorService.execute({ functionName, machineName, params, debug });
  if (!result.success) {
    throw new Error(
      `Ceph install step "${functionName}" failed on ${machineName}: ${
        result.error ?? DEFAULTS.CLOUD.UNKNOWN_ERROR
      }`
    );
  }
}

/** Resolve every ceph-pool member (name + IP) in pool/index order. */
async function resolveCephMembers(
  clusterName: string,
  cephPools: ClusterPool[]
): Promise<CephMember[]> {
  const members: CephMember[] = [];
  for (const pool of cephPools) {
    for (let i = 1; i <= pool.count; i++) {
      const name = `${clusterName}-${pool.name}-${i}`;
      const machine = await configService.getLocalMachine(name);
      members.push({ name, ip: machine.ip });
    }
  }
  return members;
}

/**
 * Install Ceph on the cluster's ceph-pool members, ceph-first:
 *   1. ceph_install_prerequisites on EVERY member,
 *   2. ceph_bootstrap_cluster on the first member (monitor = its IP),
 *   3. ceph_cluster_create once from the first member (all member IPs as nodes),
 *   4. ceph_pool_create for the application pool.
 * A non-success at any step throws (via dispatchCeph) so the install fails loud.
 */
async function installCeph(
  clusterName: string,
  cephPools: ClusterPool[],
  cluster: ClusterConfig,
  debug?: boolean
): Promise<void> {
  const members = await resolveCephMembers(clusterName, cephPools);
  if (members.length === 0) return; // count>=1 guarantees a member; guard for safety.
  const first = members[0];

  outputService.info(
    `Cluster "${clusterName}": installing Ceph on ${members.length} member(s) as "${CEPH_CLUSTER_NAME}"...`
  );

  // 1. Prerequisites on every ceph member.
  for (const m of members) {
    outputService.info(`  ceph_install_prerequisites on ${m.name}...`);
    await dispatchCeph('ceph_install_prerequisites', m.name, {}, debug);
  }

  // 2. Bootstrap the monitor on the first member.
  outputService.info(`  ceph_bootstrap_cluster (monitor ${first.ip}) on ${first.name}...`);
  await dispatchCeph(
    'ceph_bootstrap_cluster',
    first.name,
    { cluster: CEPH_CLUSTER_NAME, monitor: first.ip },
    debug
  );

  // 3. Create the cluster + OSDs from the first member. The disk's `purpose`
  // field carries the OSD device path; default to /dev/sdb when unspecified.
  const osdDevice = cephPools[0]?.disks?.[0]?.purpose ?? DEFAULTS.CEPH.OSD_DEVICE;
  const nodes = members.map((m) => m.ip).join(',');
  outputService.info(
    `  ceph_cluster_create (nodes ${nodes}, osd ${osdDevice}) on ${first.name}...`
  );
  await dispatchCeph(
    'ceph_cluster_create',
    first.name,
    { cluster: CEPH_CLUSTER_NAME, nodes, osd_device: osdDevice },
    debug
  );

  // 4. Create the application pool (pg_num omitted — let renet default it).
  const pool = cluster.ceph?.pool ?? DEFAULTS.CEPH.POOL;
  outputService.info(`  ceph_pool_create (pool ${pool}) on ${first.name}...`);
  await dispatchCeph('ceph_pool_create', first.name, { pool, cluster: CEPH_CLUSTER_NAME }, debug);

  outputService.success(`Cluster "${clusterName}": Ceph pool "${pool}" ready.`);
}

/**
 * Install cluster components in dependency order: CEPH POOL FIRST (storage sits
 * below the k8s control plane), then k8s pools.
 *
 * Ceph install dispatches the internal ceph_* bridge functions to the ceph-pool
 * members. The k8s branch remains the wave-5 seam (pending the renet kube
 * contract); it reports the pending work rather than pretending to install.
 */
async function installComponents(
  clusterName: string,
  cluster: ClusterConfig,
  debug?: boolean
): Promise<void> {
  const cephPools = cluster.pools.filter((p) => p.role === 'ceph');
  const k8sPools = cluster.pools.filter(
    (p) => p.role === 'k8s-server' || p.role === 'k8s-agent' || p.role === 'hyperconverged'
  );
  if (cephPools.length > 0) {
    await installCeph(clusterName, cephPools, cluster, debug);
  }
  if (k8sPools.length > 0) {
    await installK8s(clusterName, k8sPools, debug);
  }
}

/** Install cluster components (ceph first) on an already-provisioned cluster. */
export async function installCluster(clusterName: string): Promise<void> {
  const cluster = await getCluster(clusterName);
  await installComponents(clusterName, cluster);
}

/** Base domain from a non-cluster-member machine, for public DNS inheritance. */
async function findSiblingBaseDomain(excludeControlNode: string): Promise<string | undefined> {
  const machines = await configService.listMachines();
  for (const m of machines) {
    if (m.name !== excludeControlNode && m.config.infra?.baseDomain) {
      return m.config.infra.baseDomain;
    }
  }
  return undefined;
}

/**
 * Push infra to the control node and publish the cluster's wildcard DNS
 * (`*.{cluster}.{controlNode}.{base}`) so k8s-repo URLs resolve. Best-effort and
 * cloud-only: KVM control nodes sit on a private LAN with no public DNS. The
 * DNS calls are the wave-4 seam (ensureClusterDnsRecords).
 */
async function configureControlNodeDns(
  clusterName: string,
  cluster: ClusterConfig,
  options: CreateClusterOptions
): Promise<void> {
  if (isKvmProvider(cluster.provider)) return;
  try {
    const controlNode = await resolveControlNode(clusterName);
    const machine = await configService.getLocalMachine(controlNode);
    const baseDomain = options.baseDomain ?? (await findSiblingBaseDomain(controlNode));
    if (!baseDomain) {
      outputService.info(
        `Cluster "${clusterName}": no base domain available; skipping public DNS. Set infra on a machine or pass --base-domain to publish cluster URLs.`
      );
      return;
    }
    await configService.setMachineInfra(controlNode, { baseDomain, publicIPv4: machine.ip });
    await pushInfraConfig(controlNode, { debug: options.debug });
    const local = await configService.getLocalConfig();
    const updated = await configService.getLocalMachine(controlNode);
    await ensureClusterDnsRecords(controlNode, clusterName, updated.infra ?? { baseDomain }, {
      cfDnsApiToken: local.cfDnsApiToken,
      cfDnsZoneId: local.cfDnsZoneId,
    });
  } catch (error) {
    outputService.warn(
      `Cluster "${clusterName}" DNS/infra setup skipped: ${
        error instanceof Error ? error.message : String(error)
      }`
    );
  }
}

/** Remove the cluster's public DNS during teardown (best-effort, cloud-only). */
async function removeControlNodeDns(clusterName: string, cluster: ClusterConfig): Promise<void> {
  if (isKvmProvider(cluster.provider)) return;
  try {
    const controlNode = await resolveControlNode(clusterName);
    const machine = await configService.getLocalMachine(controlNode);
    if (!machine.infra) return;
    const local = await configService.getLocalConfig();
    await removeClusterDnsRecords(controlNode, clusterName, machine.infra, {
      cfDnsApiToken: local.cfDnsApiToken,
      cfDnsZoneId: local.cfDnsZoneId,
    });
  } catch {
    // DNS cleanup is best-effort.
  }
}

/**
 * Create a cluster: provision pool members, materialize them into machines,
 * bootstrap renet on each, then install components (ceph first).
 */
export async function createCluster(
  clusterName: string,
  options: CreateClusterOptions = {}
): Promise<void> {
  const startTime = Date.now();
  const cluster = await getCluster(clusterName);
  const sshUser = options.sshUser ?? DEFAULTS.CLOUD.SSH_USER;

  const members = isKvmProvider(cluster.provider)
    ? (await provisionKvmCluster(clusterName, cluster)).members
    : await provisionCloud(clusterName, cluster, options.debug);

  await materializeClusterMachines(
    clusterName,
    members.map((m) => ({ pool: m.pool, index: m.index, ip: m.ip, user: sshUser }))
  );

  await bootstrapMembers(clusterName, members, sshUser, options.debug);
  await configureControlNodeDns(clusterName, cluster, options);
  await installComponents(clusterName, cluster, options.debug);

  auditService.recordOperation({
    functionName: 'cluster_create',
    machineName: clusterName,
    success: true,
    exitCode: 0,
    durationMs: Date.now() - startTime,
  });
  outputService.success(
    `Cluster "${clusterName}" provisioned (${members.length} members). Install components when their wave lands.`
  );
}

export interface DestroyClusterOptions {
  force?: boolean;
  debug?: boolean;
}

/** Tear down provisioned infrastructure for a cluster (cloud via tofu; KVM = wave 8). */
async function teardownInfra(
  clusterName: string,
  cluster: ClusterConfig,
  options: DestroyClusterOptions
): Promise<void> {
  if (isKvmProvider(cluster.provider)) {
    if (!options.force) {
      throw new Error(
        `KVM cluster teardown is wired in wave 8. Re-run with --force to only remove the config records.`
      );
    }
    return;
  }
  const executor = new TofuExecutor(clusterTofuDir(clusterName));
  try {
    await executor.destroy({ debug: options.debug });
  } catch (error) {
    if (!options.force) throw error;
    outputService.warn(
      `Cluster destroy failed but continuing (--force): ${
        error instanceof Error ? error.message : String(error)
      }`
    );
  }
  await executor.cleanup();
}

/** Remove a cluster's materialized member machines (best-effort per member). */
async function removeClusterMachines(clusterName: string, cluster: ClusterConfig): Promise<void> {
  for (const pool of cluster.pools) {
    for (let i = 1; i <= pool.count; i++) {
      try {
        await configService.removeMachine(`${clusterName}-${pool.name}-${i}`);
      } catch {
        // Member may not have been materialized (partial create).
      }
    }
  }
}

/** Destroy a cluster: tofu destroy, remove materialized machines + the record. */
export async function destroyCluster(
  clusterName: string,
  options: DestroyClusterOptions = {}
): Promise<void> {
  const startTime = Date.now();
  const cluster = await getCluster(clusterName);

  // Remove DNS before the machines (removeClusterDnsRecords reads the control
  // node's infra, which disappears with the machine records).
  await removeControlNodeDns(clusterName, cluster);
  await teardownInfra(clusterName, cluster, options);
  await removeClusterMachines(clusterName, cluster);
  await configService.removeCluster(clusterName);

  auditService.recordOperation({
    functionName: 'cluster_destroy',
    machineName: clusterName,
    success: true,
    exitCode: 0,
    durationMs: Date.now() - startTime,
  });
  outputService.success(`Cluster "${clusterName}" destroyed.`);
}

export interface ScaleClusterOptions {
  pool: string;
  count: number;
  debug?: boolean;
}

/**
 * Scale a pool up or down: materialize/remove members, then per pool role add
 * k8s agents (join) or remove them (drain + node remove). Ceph pool scaling
 * (cephadm orch host add/OSD) is reported as a follow-up.
 */
export async function scaleCluster(
  clusterName: string,
  options: ScaleClusterOptions
): Promise<void> {
  const startTime = Date.now();
  const cluster = await getCluster(clusterName);
  const pool = cluster.pools.find((p) => p.name === options.pool);
  if (!pool) {
    throw new Error(`Cluster "${clusterName}" has no pool named "${options.pool}".`);
  }
  const currentCount = pool.count;
  const targetCount = options.count;
  if (targetCount === currentCount) {
    outputService.info(`Pool "${options.pool}" is already at ${targetCount} node(s).`);
    return;
  }

  if (pool.role === 'ceph') {
    throw new Error(
      `Ceph pool scaling (cephadm orch host add / OSD add) is a follow-up. Scale k8s-agent pools now; grow ceph via cephadm directly.`
    );
  }
  if (pool.role !== 'k8s-agent') {
    throw new Error(
      `Only k8s-agent pools scale in place. Pool "${options.pool}" has role "${pool.role}".`
    );
  }

  // Materialize new member machine records before joining (scale-up), or leave
  // records for the operator to prune after draining (scale-down).
  if (targetCount > currentCount) {
    if (cluster.provider !== 'kvm') {
      // Refuse clearly instead of failing later on an empty member IP.
      throw new Error(
        `Scaling UP a "${cluster.provider}" pool needs the new instances provisioned first ` +
          `(cloud scale-up provisioning is a follow-up; scale-down and KVM pools work today).`
      );
    }
    await materializeClusterMachines(
      clusterName,
      Array.from({ length: targetCount - currentCount }, (_, k) => ({
        pool: pool.name,
        index: currentCount + k + 1,
        ip: '', // placeholder for a pre-existing KVM VM (kvm-only path).
        user: DEFAULTS.CLOUD.SSH_USER,
      }))
    );
  }
  await scaleK8sPool(clusterName, pool, targetCount, currentCount, options.debug);

  // Persist the new pool count.
  await configService.updateCluster(clusterName, {
    pools: cluster.pools.map((p) => (p.name === pool.name ? { ...p, count: targetCount } : p)),
  });

  if (targetCount < currentCount) {
    await removeClusterMembersAbove(clusterName, pool.name, targetCount, currentCount);
  }

  auditService.recordOperation({
    functionName: 'cluster_scale',
    machineName: clusterName,
    success: true,
    exitCode: 0,
    durationMs: Date.now() - startTime,
  });
  outputService.success(
    `Cluster "${clusterName}" pool "${options.pool}" scaled ${currentCount} -> ${targetCount}.`
  );
}

/** Remove materialized member records for drained scale-down nodes. */
async function removeClusterMembersAbove(
  clusterName: string,
  poolName: string,
  targetCount: number,
  currentCount: number
): Promise<void> {
  for (let i = currentCount; i > targetCount; i--) {
    try {
      await configService.removeMachine(`${clusterName}-${poolName}-${i}`);
    } catch {
      // Member record may not exist; ignore.
    }
  }
}
