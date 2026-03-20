import { OpsManager as BaseOpsManager, type ProvisioningConfig, type VMNetworkConfig } from '@rediacc/provisioning';
/**
 * Re-export VMNetworkConfig for backward compatibility
 */
export type { VMNetworkConfig };
/**
 * OpsManager - Extended manager for bridge tests
 *
 * Extends the base OpsManager from @rediacc/provisioning with:
 * - RustFS S3-compatible storage management
 * - Ceph cluster management
 * - Datastore initialization
 *
 * Uses environment variables for configuration by default.
 * For explicit configuration, pass a ProvisioningConfig to the constructor.
 */
export declare class OpsManager extends BaseOpsManager {
    private readonly rustfsManager;
    private readonly cephManager;
    /**
     * Create an OpsManager with explicit configuration.
     *
     * @param provisioningConfig - Complete provisioning configuration
     */
    constructor(provisioningConfig: ProvisioningConfig);
    /**
     * Start RustFS S3-compatible storage on the bridge VM.
     */
    startRustFS(): Promise<{
        success: boolean;
        message: string;
    }>;
    /**
     * Check if RustFS is running on the bridge VM.
     */
    isRustFSRunning(): Promise<boolean>;
    /**
     * Stop RustFS S3-compatible storage on the bridge VM.
     */
    stopRustFS(): Promise<{
        success: boolean;
        message: string;
    }>;
    /**
     * Create a bucket in RustFS.
     */
    createRustFSBucket(bucket?: string): Promise<{
        success: boolean;
        message: string;
    }>;
    /**
     * List contents of a RustFS bucket.
     */
    listRustFSBucket(bucket?: string): Promise<{
        success: boolean;
        contents: string;
        message: string;
    }>;
    /**
     * Configure rclone on a worker VM to access RustFS.
     */
    configureRustFSWorker(vmId: number): Promise<{
        success: boolean;
        message: string;
    }>;
    /**
     * Configure rclone on all worker VMs to access RustFS.
     */
    configureRustFSWorkers(): Promise<{
        success: boolean;
        message: string;
    }>;
    /**
     * Verify RustFS access from a worker VM using rclone.
     */
    verifyRustFSAccessFromWorker(vmId: number, bucket?: string): Promise<{
        success: boolean;
        message: string;
    }>;
    /**
     * Initialize datastores on all worker VMs.
     * This ensures /mnt/rediacc is mounted with BTRFS filesystem.
     * Should be called during global setup, not in individual tests.
     */
    initializeAllDatastores(size?: string, datastorePath?: "/mnt/rediacc"): Promise<void>;
    /**
     * Provision Ceph cluster on Ceph VMs.
     * This runs the OPS provisioning scripts to set up a full Ceph cluster.
     * Should be called after VM reset and before running Ceph-related tests.
     */
    provisionCeph(): Promise<{
        success: boolean;
        message: string;
    }>;
}
/**
 * Get the singleton OpsManager instance using environment configuration.
 *
 * @throws Error if required environment variables are missing
 */
export declare function getOpsManager(): OpsManager;
//# sourceMappingURL=OpsManager.d.ts.map