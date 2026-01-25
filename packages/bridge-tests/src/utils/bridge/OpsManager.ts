import {
  OpsManager as BaseOpsManager,
  loadConfigFromEnv,
  type VMNetworkConfig,
  type ProvisioningConfig,
} from '@rediacc/provisioning';
import { OpsCephManager } from './OpsCephManager';
import { OpsRustFSManager } from './OpsRustFSManager';
import { DEFAULT_DATASTORE_PATH } from '../../constants';

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
export class OpsManager extends BaseOpsManager {
  private readonly rustfsManager: OpsRustFSManager;
  private readonly cephManager: OpsCephManager;

  /**
   * Create an OpsManager with explicit configuration.
   *
   * @param provisioningConfig - Complete provisioning configuration
   */
  constructor(provisioningConfig: ProvisioningConfig) {
    super(provisioningConfig);

    // Initialize domain-specific managers
    this.rustfsManager = new OpsRustFSManager(
      this.getVMExecutor(),
      this.getBridgeVMIp(),
      this.runOpsCommand.bind(this)
    );
    this.cephManager = new OpsCephManager(
      this.getCephVMIps(),
      this.runOpsCommandWithEnv.bind(this)
    );
  }

  /**
   * Start RustFS S3-compatible storage on the bridge VM.
   */
  async startRustFS(): Promise<{ success: boolean; message: string }> {
    return this.rustfsManager.start();
  }

  /**
   * Check if RustFS is running on the bridge VM.
   */
  async isRustFSRunning(): Promise<boolean> {
    return this.rustfsManager.isRunning();
  }

  /**
   * Stop RustFS S3-compatible storage on the bridge VM.
   */
  async stopRustFS(): Promise<{ success: boolean; message: string }> {
    return this.rustfsManager.stop();
  }

  /**
   * Create a bucket in RustFS.
   */
  async createRustFSBucket(bucket?: string): Promise<{ success: boolean; message: string }> {
    return this.rustfsManager.createBucket(bucket);
  }

  /**
   * List contents of a RustFS bucket.
   */
  async listRustFSBucket(
    bucket?: string
  ): Promise<{ success: boolean; contents: string; message: string }> {
    return this.rustfsManager.listBucket(bucket);
  }

  /**
   * Configure rclone on a worker VM to access RustFS.
   */
  async configureRustFSWorker(vmId: number): Promise<{ success: boolean; message: string }> {
    return this.rustfsManager.configureWorker(vmId);
  }

  /**
   * Configure rclone on all worker VMs to access RustFS.
   */
  async configureRustFSWorkers(): Promise<{ success: boolean; message: string }> {
    return this.rustfsManager.configureAllWorkers();
  }

  /**
   * Verify RustFS access from a worker VM using rclone.
   */
  async verifyRustFSAccessFromWorker(
    vmId: number,
    bucket?: string
  ): Promise<{ success: boolean; message: string }> {
    return this.rustfsManager.verifyAccessFromWorker(vmId, this.calculateVMIp.bind(this), bucket);
  }

  /**
   * Initialize datastores on all worker VMs.
   * This ensures /mnt/rediacc is mounted with BTRFS filesystem.
   * Should be called during global setup, not in individual tests.
   */
  async initializeAllDatastores(
    size = '10G',
    datastorePath = DEFAULT_DATASTORE_PATH
  ): Promise<void> {
    console.warn('[OpsManager] Initializing datastores on all worker VMs...');

    const workerIPs = this.getWorkerVMIps();

    for (const ip of workerIPs) {
      console.warn(`  Initializing datastore on ${ip}...`);

      // Run datastore_init via renet bridge once --test-mode
      const result = await this.executeOnVM(
        ip,
        `renet bridge once --test-mode --function datastore_init --datastore-path ${datastorePath} --size ${size} --force`,
        120000 // 2 minute timeout for datastore initialization
      );

      if (result.code !== 0) {
        throw new Error(`Failed to initialize datastore on ${ip}: ${result.stderr}`);
      }

      console.warn(`  ✓ Datastore initialized on ${ip}`);
    }

    console.warn('[OpsManager] All datastores initialized');
  }

  /**
   * Provision Ceph cluster on Ceph VMs.
   * This runs the OPS provisioning scripts to set up a full Ceph cluster.
   * Should be called after VM reset and before running Ceph-related tests.
   */
  async provisionCeph(): Promise<{ success: boolean; message: string }> {
    return this.cephManager.provision();
  }
}

// Singleton instance for shared state across tests
let opsManagerInstance: OpsManager | null = null;

/**
 * Get the singleton OpsManager instance using environment configuration.
 *
 * @throws Error if required environment variables are missing
 */
export function getOpsManager(): OpsManager {
  opsManagerInstance ??= new OpsManager(loadConfigFromEnv());
  return opsManagerInstance;
}

/**
 * Create an OpsManager using environment variables for configuration.
 *
 * @throws Error if required environment variables are missing
 */
export function createOpsManagerFromEnv(): OpsManager {
  return new OpsManager(loadConfigFromEnv());
}

/**
 * Reset the singleton OpsManager instance.
 * Useful for testing or when configuration changes.
 */
export function resetOpsManager(): void {
  opsManagerInstance = null;
}
