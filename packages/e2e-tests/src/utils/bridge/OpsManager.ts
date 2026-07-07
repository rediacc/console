import {
  OpsManager as BaseOpsManager,
  buildGroupEnv,
  getRenetBinaryPath,
  getRenetRoot,
  loadConfigFromEnv,
  type ProvisioningConfig,
  type VMNetworkConfig,
} from '@rediacc/provisioning';
import { DEFAULT_DATASTORE_PATH } from '../../constants';
import { OpsCephManager } from './OpsCephManager';
import { OpsRustFSManager } from './OpsRustFSManager';

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

      // Run datastore_init via renet functions once --test-mode
      const result = await this.executeOnVM(
        ip,
        `renet functions once --test-mode --function datastore_init --datastore-path ${datastorePath} --size ${size} --force`,
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
 * Descriptor for a second, concurrent KVM group (the `renet12`/192.168.112 fleet
 * suite 18 migrates onto). VM IDs MUST be disjoint from the ambient group's, or
 * `ops down` — which destroys `rediacc<id>` domains by ID, not by network —
 * would tear the other group's VMs down.
 */
export interface GroupConfig {
  /** libvirt network / host-bridge name, e.g. "renet12". */
  netName: string;
  /** Network prefix, e.g. "192.168.112". */
  netBase: string;
  /** Offset added to VM IDs (default 0). */
  netOffset?: number;
  /** Bridge (control-node) VM ID — disjoint from every other group. */
  bridgeId: number;
  /** Worker VM IDs — disjoint from every other group. */
  workerIds: number[];
  /** Ceph node VM IDs (default none — a minimal group runs no Ceph). */
  cephIds?: number[];
  /** In-VM registry endpoint; when unset renet derives it from the bridge IP. */
  dockerRegistry?: string;
}

/**
 * Build a NON-singleton OpsManager for an explicit VM group.
 *
 * Each call returns a fresh manager carrying the group's own {@link buildGroupEnv}
 * so its `renet ops` subprocesses never inherit the ambient group's VM_NET /
 * DOCKER_REGISTRY. This is what lets one harness drive two groups at once
 * without env-bleed (the singleton {@link getOpsManager} stays for single-group
 * suites).
 */
export function getOpsManagerForGroup(group: GroupConfig): OpsManager {
  const network: VMNetworkConfig = {
    netBase: group.netBase,
    netOffset: group.netOffset ?? 0,
    bridgeId: group.bridgeId,
    workerIds: group.workerIds,
    cephIds: group.cephIds ?? [],
    netName: group.netName,
    dockerRegistry: group.dockerRegistry,
  };
  const config: ProvisioningConfig = {
    network,
    renet: { binaryPath: getRenetBinaryPath(), rootPath: getRenetRoot() },
    groupEnv: buildGroupEnv(network),
  };
  return new OpsManager(config);
}
