/**
 * KVM (local libvirt) cluster provisioning.
 *
 * KVM is a pseudo-provider that never goes through OpenTofu; it boots VMs via
 * `renet ops`, threading a per-cluster group env so two clusters on one host
 * cannot address each other's VMs. It returns the same member shape the tofu path
 * produces, so createCluster stays provider-agnostic downstream.
 */

import { dirname } from 'node:path';
import { OpsManager, buildGroupEnv } from '@rediacc/provisioning';
import type { ClusterConfig, ClusterKvm } from '../../types/index.js';
import { outputService } from '../core/output.js';
import { opsExecutorService } from '../executor/ops-executor.js';
import { type KvmTopology, resolveKvmTopology } from './kvm-topology.js';

interface ProvisionedMember {
  pool: string;
  index: number;
  ip: string;
}

export interface KvmProvisionResult {
  members: ProvisionedMember[];
  /** The kvm block to persist, carrying the id allocation destroy/scale reuse. */
  kvm: ClusterKvm;
}

/** How long a freshly booted fleet gets to answer SSH before we give up. */
const VM_READY_TIMEOUT_MS = 300_000;

/** renet writes its diagnostics to stderr, falling back to stdout when it is quiet. */
function failureDetail(result: { stdout: string; stderr: string }): string {
  return result.stderr.trim() === '' ? result.stdout : result.stderr;
}

/**
 * Resolve renet the way every other CLI command does. The provisioning package's
 * own resolver walks up from __dirname, which is meaningless once the CLI is a
 * bundled single-file executable.
 */
async function opsManagerFor(topology: KvmTopology): Promise<OpsManager> {
  const binaryPath = await opsExecutorService.getRenetPath();
  return new OpsManager({
    network: topology.network,
    renet: { binaryPath, rootPath: dirname(binaryPath) },
    groupEnv: buildGroupEnv(topology.network),
  });
}

/**
 * Boot a cluster's pool members on local KVM and return their private IPs.
 */
export async function provisionKvmCluster(
  clusterName: string,
  config: ClusterConfig
): Promise<KvmProvisionResult> {
  const topology = resolveKvmTopology(clusterName, config);
  const ops = await opsManagerFor(topology);

  outputService.info(
    `Provisioning ${topology.members.length} KVM VM(s) for "${clusterName}" on ${topology.network.netName}...`
  );
  const started = await ops.startVMs({ force: true, parallel: true });
  if (!started.success) {
    throw new Error(`renet ops up failed for cluster "${clusterName}": ${failureDetail(started)}`);
  }

  if (!(await ops.waitForAllVMs(VM_READY_TIMEOUT_MS))) {
    throw new Error(
      `Cluster "${clusterName}" VMs did not become SSH-reachable within ${VM_READY_TIMEOUT_MS / 1000}s.`
    );
  }

  return {
    members: topology.members.map((m) => ({ pool: m.pool, index: m.index, ip: m.ip })),
    kvm: { ...topology.kvm, memberIds: topology.memberIds },
  };
}

/**
 * Destroy a cluster's KVM VMs. `ops down` addresses them by the ids in the group
 * env, which is why the allocation is persisted rather than recomputed.
 */
export async function teardownKvmCluster(
  clusterName: string,
  config: ClusterConfig
): Promise<void> {
  const topology = resolveKvmTopology(clusterName, config);
  const ops = await opsManagerFor(topology);

  const stopped = await ops.stopVMs();
  if (!stopped.success) {
    throw new Error(
      `renet ops down failed for cluster "${clusterName}": ${failureDetail(stopped)}`
    );
  }
}
