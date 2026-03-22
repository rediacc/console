import { OpsManager } from '../bridge/OpsManager';
export interface InfrastructureConfig {
    bridgeVM: string;
    workerVM: string | undefined;
    defaultTimeout: number;
}
/**
 * InfrastructureManager for bridge tests.
 *
 * Always runs in full VM mode:
 * - Automatically starts VMs using renet ops commands if not running
 * - Verifies renet is installed on all VMs
 * - No middleware or Docker containers required - renet runs in local/test mode
 *
 * DELEGATES TO SSHExecutor:
 * All SSH operations are delegated to the centralized SSHExecutor to ensure
 * consistent behavior and avoid code duplication.
 */
export declare class InfrastructureManager {
    private readonly config;
    private readonly opsManager;
    private readonly resolver;
    private readonly sshExecutor;
    constructor();
    /**
     * Get the path to renet binary (from resolver).
     */
    getRenetPath(): string;
    /**
     * Check if renet binary is available locally.
     * Uses RenetResolver which handles all resolution and auto-build logic.
     */
    isRenetAvailable(): Promise<{
        available: boolean;
        path: string;
    }>;
    /**
     * Check if bridge VM is reachable via SSH.
     * Delegates to SSHExecutor for consistent behavior.
     */
    isBridgeVMReachable(): Promise<boolean>;
    /**
     * Check if worker VM is reachable via SSH.
     * Delegates to SSHExecutor for consistent behavior.
     * Returns true if no worker VMs are configured (Ceph-only mode).
     */
    isWorkerVMReachable(): Promise<boolean>;
    /**
     * Get current infrastructure status.
     */
    getStatus(): Promise<{
        renet: {
            available: boolean;
            path: string;
        };
        bridgeVM: boolean;
        workerVM: boolean;
    }>;
    /**
     * Ensure infrastructure is ready for tests.
     * - Verifies renet binary is available
     * - Starts VMs if not running
     * - Deploys renet to VMs if outdated
     */
    ensureInfrastructure(): Promise<void>;
    /**
     * Check if workers are configured (not Ceph-only mode).
     */
    private hasWorkerVMs;
    /**
     * Check if worker VMs are ready, accounting for Ceph-only mode.
     */
    private isWorkerVMStatusReady;
    /**
     * Log worker VM status with Ceph-only mode support.
     */
    private logWorkerStatus;
    /**
     * Ensure VMs are running and ready.
     */
    private ensureVMsRunning;
    /**
     * Get MD5 hash of renet binary on a remote VM.
     */
    private getRemoteRenetMD5;
    /**
     * Deploy renet binary to a VM if it's different from the local version.
     * Verifies the deployment by checking MD5 after copy.
     */
    private deployRenetToVM;
    /**
     * Verify renet is installed and up-to-date on all VMs (bridge, workers, ceph).
     * Deploys the local version if VMs have outdated binary.
     */
    ensureRenetOnVMs(): Promise<void>;
    /**
     * Get the OpsManager instance for direct VM operations.
     */
    getOpsManager(): OpsManager;
    /**
     * Deploy CRIU to all worker VMs.
     *
     * Strategy:
     * 1. Try to extract CRIU from bridge container (pre-built, fast)
     * 2. Fall back to building from source if container not available
     *
     * CRIU is required for container checkpointing tests.
     */
    deployCRIUToAllVMs(): Promise<void>;
    /**
     * Check if any worker VM needs CRIU installation.
     */
    private checkIfCriuNeeded;
    /**
     * Try to extract CRIU from bridge container.
     */
    private extractCriuFromContainer;
    /**
     * Deploy CRIU to worker VMs.
     */
    private deployCriuToWorkers;
    /**
     * Copy CRIU from bridge VM to worker VM.
     * Uses SSHExecutor for consistent SSH options in nested commands.
     */
    private copyCriuFromBridge;
    /**
     * Build CRIU from source on a worker VM.
     */
    private buildCriuFromSource;
}
//# sourceMappingURL=InfrastructureManager.d.ts.map
