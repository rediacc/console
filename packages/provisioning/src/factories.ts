import { OpsManager } from './ops';
import { getRenetBinaryPath, getRenetRoot } from './renet';
import type { ProvisioningConfig, VMNetworkConfig } from './types';

/**
 * Load VM network configuration from environment variables.
 * Matches the pattern in ops/scripts/init.sh
 *
 * Required environment variables:
 * - VM_NET_BASE: Network prefix (e.g., "192.168.111")
 * - VM_NET_OFFSET: Offset added to VM ID
 * - VM_CONTROL: Control-node VM ID (VM_BRIDGE is a kept alias)
 * - VM_WORKERS: Space-separated worker VM IDs (can be empty in Ceph-only mode)
 * - VM_CEPH_NODES: Space-separated Ceph node IDs (optional)
 *
 * @throws Error if required environment variables are missing
 */
export function loadNetworkConfigFromEnv(): VMNetworkConfig {
  const netBase = process.env.VM_NET_BASE;
  if (!netBase) {
    throw new Error('VM_NET_BASE environment variable is required');
  }

  const netOffsetStr = process.env.VM_NET_OFFSET;
  if (netOffsetStr === undefined) {
    throw new Error('VM_NET_OFFSET environment variable is required');
  }
  const netOffset = Number.parseInt(netOffsetStr, 10);

  // VM_CONTROL is canonical; VM_BRIDGE stays as a kept alias.
  const bridgeIdStr = process.env.VM_CONTROL ?? process.env.VM_BRIDGE;
  if (!bridgeIdStr) {
    throw new Error('VM_CONTROL (or VM_BRIDGE) environment variable is required');
  }
  const bridgeId = Number.parseInt(bridgeIdStr, 10);

  // Parse worker IDs from space-separated string (can be empty in Ceph-only mode)
  const workersStr = process.env.VM_WORKERS ?? '';
  const workerIds = workersStr
    .split(/\s+/)
    .map((id) => Number.parseInt(id, 10))
    .filter((id) => !Number.isNaN(id));

  // Parse ceph node IDs (optional - empty means Ceph disabled)
  const cephStr = process.env.VM_CEPH_NODES ?? '';
  const cephIds = cephStr
    .split(/\s+/)
    .map((id) => Number.parseInt(id, 10))
    .filter((id) => !Number.isNaN(id));

  // Allow empty workers if Ceph nodes are configured (Ceph-only mode)
  if (workerIds.length === 0 && cephIds.length === 0) {
    throw new Error(
      'VM_WORKERS must contain at least one worker ID (or configure VM_CEPH_NODES for Ceph-only mode)'
    );
  }

  // VM_NET / DOCKER_REGISTRY are optional. An empty or absent value is treated as
  // "unset" downstream (buildGroupEnv only emits them when truthy), so renet
  // applies its own default / bridge-IP derivation.
  return {
    netBase,
    netOffset,
    bridgeId,
    workerIds,
    cephIds,
    netName: process.env.VM_NET,
    dockerRegistry: process.env.DOCKER_REGISTRY,
  };
}

/**
 * Build the `renet ops` environment for a VM group from its network config.
 *
 * A second concurrent KVM group must not inherit the ambient group's VM_NET /
 * DOCKER_REGISTRY: passing this map as {@link ProvisioningConfig.groupEnv} makes
 * every ops subprocess this group spawns see its own network, disjoint VM IDs,
 * and (optionally) its own registry. VM_NET / DOCKER_REGISTRY are only emitted
 * when the config carries them, so a single-group caller keeps ambient defaults.
 */
export function buildGroupEnv(network: VMNetworkConfig): Record<string, string> {
  const env: Record<string, string> = {
    VM_NET_BASE: network.netBase,
    VM_NET_OFFSET: String(network.netOffset),
    // Emit canonical VM_CONTROL plus the kept VM_BRIDGE alias.
    VM_CONTROL: String(network.bridgeId),
    VM_BRIDGE: String(network.bridgeId),
    VM_WORKERS: network.workerIds.join(' '),
    VM_CEPH_NODES: network.cephIds.join(' '),
  };
  if (network.netName) env.VM_NET = network.netName;
  if (network.dockerRegistry) env.DOCKER_REGISTRY = network.dockerRegistry;
  return env;
}

/**
 * Load complete provisioning configuration from environment variables.
 *
 * Uses:
 * - loadNetworkConfigFromEnv() for VM network config
 * - getRenetBinaryPath() and getRenetRoot() for renet config
 *
 * @throws Error if required environment variables are missing
 */
export function loadConfigFromEnv(): ProvisioningConfig {
  return {
    network: loadNetworkConfigFromEnv(),
    renet: {
      binaryPath: getRenetBinaryPath(),
      rootPath: getRenetRoot(),
    },
  };
}

/**
 * Create an OpsManager using environment variables for configuration.
 *
 * This is a convenience factory for backward compatibility with code
 * that expects configuration to be loaded from environment.
 *
 * @throws Error if required environment variables are missing
 */
export function createOpsManagerFromEnv(): OpsManager {
  return new OpsManager(loadConfigFromEnv());
}

// Singleton instance for backward compatibility
let opsManagerInstance: OpsManager | null = null;

/**
 * Get a singleton OpsManager instance using environment configuration.
 *
 * This maintains backward compatibility with code that uses getOpsManager().
 * The singleton is created lazily on first call.
 *
 * @throws Error if required environment variables are missing
 */
export function getOpsManager(): OpsManager {
  opsManagerInstance ??= createOpsManagerFromEnv();
  return opsManagerInstance;
}

/**
 * Reset the singleton OpsManager instance.
 * Useful for testing or when configuration changes.
 */
export function resetOpsManager(): void {
  opsManagerInstance = null;
}
