/**
 * OpsCephManager - Manages Ceph cluster operations
 *
 * Extracted from OpsManager to reduce file size.
 * Provides methods for:
 * - Ceph cluster provisioning
 */
export declare class OpsCephManager {
    private readonly cephIPs;
    private readonly runOpsCommandWithEnv;
    constructor(cephIPs: string[], runOpsCommandWithEnv: (subcommands: string[], args: string[], extraEnv: Record<string, string>, timeoutMs: number) => Promise<{
        stdout: string;
        stderr: string;
        code: number;
    }>);
    /**
     * Provision Ceph cluster on Ceph VMs.
     * This runs the OPS provisioning scripts to set up a full Ceph cluster.
     * Should be called after VM reset and before running Ceph-related tests.
     */
    provision(): Promise<{
        success: boolean;
        message: string;
    }>;
}
//# sourceMappingURL=OpsCephManager.d.ts.map