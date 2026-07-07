/**
 * KVM (local libvirt) cluster provisioning seam.
 *
 * KVM is a pseudo-provider that never goes through OpenTofu; it provisions via
 * the renet ops path (the same libvirt flow the e2e-tests harness drives).
 * Threading per-group ops env through the provisioning lifecycle is wave 8
 * (dual-KVM-group migration), which owns the ops harness. This module is the
 * seam cluster-provision calls; it returns the same member shape the tofu path
 * produces so createCluster is provider-agnostic downstream.
 */

import type { ClusterConfig } from '../../types/index.js';

interface ProvisionedMember {
  pool: string;
  index: number;
  ip: string;
}

export interface KvmProvisionResult {
  members: ProvisionedMember[];
}

/**
 * Provision a cluster's pool members on local KVM.
 *
 * TODO(wave-8): drive `renet ops` with per-group env (VM_NET/VM_NET_BASE,
 * disjoint VM IDs, DOCKER_REGISTRY override) to boot the pool members and return
 * their private IPs. Blocked here so the cloud (tofu) path lands independently
 * and the ops-harness env-threading is done once, in the wave that owns it.
 */
export function provisionKvmCluster(
  clusterName: string,
  _config: ClusterConfig
): Promise<KvmProvisionResult> {
  return Promise.reject(
    new Error(
      `KVM cluster provisioning for '${clusterName}' is wired in wave 8 (dual-KVM-group migration), which owns the renet ops harness. Use a cloud provider for now.`
    )
  );
}
