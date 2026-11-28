/**
 * Cluster provisioning lifecycle.
 *
 * createCluster mirrors createCloudMachine but for a set of pool members on a
 * private LAN. The cloud path provisions via OpenTofu; KVM boots VMs through
 * `renet ops`. Ceph pool growth remains a seam (grow it via cephadm directly).
 * Members materialize into resources.machines so every existing `-m` command
 * works on them.
 */

import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { DEFAULTS } from '@rediacc/shared/config';
import { getConfigDir } from '@rediacc/shared/paths';
import type { ClusterConfig, ClusterPool } from '../../types/index.js';
import { assertMachineSlotsAvailable } from '../account/license-preflight.js';
import {
  getCluster,
  materializeClusterMachines,
  resolveControlNode,
} from '../config/config-cluster-ops.js';
import { configService } from '../config/config-resources.js';
import { auditService } from '../core/audit.js';
import { outputService } from '../core/output.js';
import {
  ensureClusterDnsRecords,
  pushInfraConfig,
  removeClusterDnsRecords,
} from '../provision/infra-provision.js';
import { bootstrapMachine, scanHostKeys, waitForSSH } from '../renet/machine-bootstrap.js';
import { generateClusterTfJson } from '../tofu/cluster-tf-generator.js';
import { TofuExecutor } from '../tofu/executor.js';
import { isKvmProvider, resolveProviderMapping } from '../tofu/provider-resolver.js';
import { distributeCephClientConfig, installCeph } from './cluster-ceph-install.js';
import type { ControlDatastoreOptions } from './cluster-kube.js';
import { installK8s, scaleK8sPool } from './cluster-kube.js';
import { provisionKvmCluster, teardownKvmCluster } from './kvm-provisioner.js';

const TOFU_CLUSTER_DIR = join(getConfigDir(), 'tofu', 'clusters');

export interface CreateClusterOptions {
  sshUser?: string;
  /** Base domain for the cluster's public DNS (else inherited from a sibling machine). */
  baseDomain?: string;
  /** Anchor control datastore knobs (spec 02 §1); backend defaults to the cluster's storage. */
  controlDs?: ControlDatastoreOptions;
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
      'SSH public key required for cluster provisioning. Set with: rdc config init <name> --ssh-key <path>'
    );
  }
  return sshPublicKey;
}

/**
 * Boot the new members of a growing pool and record them. Booting first is what
 * keeps kube_join from binding to an empty address: a materialized member with no
 * IP is worse than a refusal.
 */
async function growPool(
  clusterName: string,
  cluster: ClusterConfig,
  pool: ClusterPool,
  targetCount: number,
  currentCount: number
): Promise<void> {
  if (!isKvmProvider(cluster.provider)) {
    throw new Error(
      `Scaling UP a "${cluster.provider}" pool needs the new instances provisioned first ` +
        `(cloud scale-up provisioning is a follow-up; scale-down works today).`
    );
  }
  const grown: ClusterConfig = {
    ...cluster,
    pools: cluster.pools.map((p) => (p.name === pool.name ? { ...p, count: targetCount } : p)),
  };
  const provisioned = await provisionKvmCluster(clusterName, grown);
  await configService.updateCluster(clusterName, { kvm: provisioned.kvm });
  await materializeClusterMachines(
    clusterName,
    provisioned.members
      .filter((m) => m.pool === pool.name && m.index > currentCount)
      .map((m) => ({ pool: m.pool, index: m.index, ip: m.ip, user: DEFAULTS.CLOUD.SSH_USER }))
  );
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
      `Cluster "${clusterName}" references cloud provider "${cluster.provider}", which is not configured. Add it with: rdc machine provider add`
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

  // Widen to `| undefined` so the per-member lookup below is legitimately guarded (a missing output means tofu produced no IP for that member).
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
    try {
      const keyscan = await scanHostKeys(m.ip, sshPort);
      await configService.updateMachine(machineName, { knownHosts: keyscan });
    } catch (error) {
      outputService.warn(
        `No host key recorded for ${machineName}: ${error instanceof Error ? error.message : String(error)}`
      );
    }
    outputService.info(`Setting up ${machineName}...`);
    await bootstrapMachine(machineName, { debug });
  }
  void sshUser;
}

/**
 * Install cluster components in dependency order: CEPH POOL FIRST (storage sits
 * below the k8s control plane), then k8s pools.
 *
 * Ceph install dispatches the internal ceph_* renet functions to the ceph-pool
 * members. The k8s branch remains the wave-5 seam (pending the renet kube
 * contract); it reports the pending work rather than pretending to install.
 */
async function installComponents(
  clusterName: string,
  cluster: ClusterConfig,
  options: { debug?: boolean; controlDs?: ControlDatastoreOptions } = {}
): Promise<void> {
  const cephPools = cluster.pools.filter((p) => p.role === 'ceph');
  const k8sPools = cluster.pools.filter(
    (p) => p.role === 'k8s-server' || p.role === 'k8s-agent' || p.role === 'hyperconverged'
  );
  if (cephPools.length > 0) {
    await installCeph(clusterName, cephPools, cluster, options.debug);
    // Before k8s bring-up: give the k8s nodes ceph client access so the control node can create the rbd ds-control and peers can attach fork clones.
    if (k8sPools.length > 0) {
      await distributeCephClientConfig(clusterName, cephPools, k8sPools, options.debug);
    }
  }
  if (k8sPools.length > 0) {
    await installK8s(clusterName, cluster, k8sPools, {
      debug: options.debug,
      controlDs: options.controlDs,
    });
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

  // Slots are claimed per machine at the first repo issuance, so a cluster whose node count exceeds the ceiling provisions fine and then fails one repo at a time, after the VMs exist. Ask before spending anything.
  await assertMachineSlotsAvailable({
    machineCount: cluster.pools.reduce((total, pool) => total + pool.count, 0),
  });

  let members: ResolvedMember[];
  if (isKvmProvider(cluster.provider)) {
    const provisioned = await provisionKvmCluster(clusterName, cluster);
    members = provisioned.members;
    // Persist the id allocation before anything else can fail: destroy and scale address these VMs by id, so losing it strands them.
    await configService.updateCluster(clusterName, {
      kvm: provisioned.kvm,
    });
  } else {
    members = await provisionCloud(clusterName, cluster, options.debug);
  }

  await materializeClusterMachines(
    clusterName,
    members.map((m) => ({ pool: m.pool, index: m.index, ip: m.ip, user: sshUser }))
  );

  await bootstrapMembers(clusterName, members, sshUser, options.debug);
  await configureControlNodeDns(clusterName, cluster, options);
  await installComponents(clusterName, cluster, {
    debug: options.debug,
    controlDs: options.controlDs,
  });

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

/** Run a destroy step, letting --force downgrade its failure to a warning. */
async function destroyStep(step: () => Promise<void>, force: boolean | undefined): Promise<void> {
  try {
    await step();
  } catch (error) {
    if (!force) throw error;
    outputService.warn(
      `Cluster destroy failed but continuing (--force): ${
        error instanceof Error ? error.message : String(error)
      }`
    );
  }
}

/** Tear down provisioned infrastructure for a cluster (cloud via tofu, KVM via renet ops). */
async function teardownInfra(
  clusterName: string,
  cluster: ClusterConfig,
  options: DestroyClusterOptions
): Promise<void> {
  if (isKvmProvider(cluster.provider)) {
    await destroyStep(() => teardownKvmCluster(clusterName, cluster), options.force);
    return;
  }
  const executor = new TofuExecutor(clusterTofuDir(clusterName));
  await destroyStep(() => executor.destroy({ debug: options.debug }), options.force);
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

  // Remove DNS before the machines (removeClusterDnsRecords reads the control node's infra, which disappears with the machine records).
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

  // Materialize new member machine records before joining (scale-up), or leave records for the operator to prune after draining (scale-down).
  if (targetCount > currentCount) {
    // Only the added nodes cost slots; the existing ones already hold theirs.
    await assertMachineSlotsAvailable({ machineCount: targetCount - currentCount });
    await growPool(clusterName, cluster, pool, targetCount, currentCount);
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
