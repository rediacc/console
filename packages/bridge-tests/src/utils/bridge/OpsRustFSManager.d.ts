import type { OpsVMExecutor } from '@rediacc/provisioning/ops';
/**
 * OpsRustFSManager - Manages RustFS S3-compatible storage operations
 *
 * Extracted from OpsManager to reduce file size.
 * Provides methods for:
 * - Starting/stopping RustFS
 * - Bucket management
 * - Worker configuration for RustFS access
 * - Access verification
 */
export declare class OpsRustFSManager {
    private readonly vmExecutor;
    private readonly bridgeIp;
    private readonly runOpsCommand;
    constructor(vmExecutor: OpsVMExecutor, bridgeIp: string, runOpsCommand: (subcommands: string[], args?: string[], timeoutMs?: number) => Promise<{
        stdout: string;
        stderr: string;
        code: number;
    }>);
    /**
     * Start RustFS S3-compatible storage on the bridge VM.
     * Uses renet ops rustfs start command.
     */
    start(): Promise<{
        success: boolean;
        message: string;
    }>;
    /**
     * Check if RustFS is running on the bridge VM.
     */
    isRunning(): Promise<boolean>;
    /**
     * Stop RustFS S3-compatible storage on the bridge VM.
     * Uses renet ops rustfs stop command.
     */
    stop(): Promise<{
        success: boolean;
        message: string;
    }>;
    /**
     * Create a bucket in RustFS.
     * Uses renet ops rustfs create-bucket command.
     */
    createBucket(bucket?: string): Promise<{
        success: boolean;
        message: string;
    }>;
    /**
     * List contents of a RustFS bucket.
     * Uses renet ops rustfs list command.
     */
    listBucket(bucket?: string): Promise<{
        success: boolean;
        contents: string;
        message: string;
    }>;
    /**
     * Configure rclone on a worker VM to access RustFS.
     * Uses renet ops rustfs configure-worker command.
     */
    configureWorker(vmId: number): Promise<{
        success: boolean;
        message: string;
    }>;
    /**
     * Configure rclone on all worker VMs to access RustFS.
     * Uses renet ops rustfs configure-workers command.
     */
    configureAllWorkers(): Promise<{
        success: boolean;
        message: string;
    }>;
    /**
     * Verify RustFS access from a worker VM using rclone.
     */
    verifyAccessFromWorker(vmId: number, calculateVMIp: (vmId: number) => string, bucket?: string): Promise<{
        success: boolean;
        message: string;
    }>;
}
//# sourceMappingURL=OpsRustFSManager.d.ts.map