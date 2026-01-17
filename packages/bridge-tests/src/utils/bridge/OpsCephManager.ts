/**
 * OpsCephManager - Manages Ceph cluster operations
 *
 * Extracted from OpsManager to reduce file size.
 * Provides methods for:
 * - Ceph cluster provisioning
 */
export class OpsCephManager {
  constructor(
    private readonly cephIPs: string[],
    private readonly runOpsCommandWithEnv: (
      subcommands: string[],
      args: string[],
      extraEnv: Record<string, string>,
      timeoutMs: number
    ) => Promise<{ stdout: string; stderr: string; code: number }>
  ) {}

  /**
   * Provision Ceph cluster on Ceph VMs.
   * This runs the OPS provisioning scripts to set up a full Ceph cluster.
   * Should be called after VM reset and before running Ceph-related tests.
   */
  async provision(): Promise<{ success: boolean; message: string }> {
    if (this.cephIPs.length === 0) {
      return { success: true, message: 'No Ceph nodes configured, skipping' };
    }

    console.warn('[OpsCephManager] Provisioning Ceph cluster...');

    // Run provisioning via OPS command (provision_ceph_cluster)
    // Set PROVISION_CEPH_CLUSTER=true to ensure provisioning runs
    const result = await this.runOpsCommandWithEnv(
      ['ceph', 'provision'],
      [],
      { PROVISION_CEPH_CLUSTER: 'true' },
      600000 // 10 minute timeout
    );

    if (result.code !== 0) {
      console.error('[OpsCephManager] Ceph provisioning failed');
      return { success: false, message: `Ceph provisioning failed: ${result.stderr}` };
    }

    console.warn('[OpsCephManager] Ceph cluster provisioned successfully');
    return { success: true, message: 'Ceph cluster provisioned' };
  }
}
