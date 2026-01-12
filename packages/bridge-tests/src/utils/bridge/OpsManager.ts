import * as path from 'node:path';
import { OpsCephManager } from './OpsCephManager';
import { OpsCommandRunner } from './OpsCommandRunner';
import { OpsRustFSManager } from './OpsRustFSManager';
import { OpsVMExecutor } from './OpsVMExecutor';
import { OpsVMLifecycle } from './OpsVMLifecycle';
import { DEFAULT_DATASTORE_PATH } from '../../constants';

/**
 * VM Network Configuration
 * Matches ops/scripts/init.sh configuration pattern
 */
export interface VMNetworkConfig {
  netBase: string; // VM_NET_BASE - Network prefix (e.g., "192.168.111")
  netOffset: number; // VM_NET_OFFSET - Offset added to VM ID
  bridgeId: number; // VM_BRIDGE - Bridge VM ID
  workerIds: number[]; // VM_WORKERS - Worker VM IDs
  cephIds: number[]; // VM_CEPH_NODES - Ceph node IDs (optional)
}

/**
 * OpsManager - Manages VMs via renet ops commands
 *
 * Provides methods to:
 * - Calculate VM IPs dynamically (matches renet/pkg/infra/config pattern)
 * - Check if VMs are running
 * - Start VMs if needed
 * - Wait for VMs to be ready
 * - Stop VMs
 *
 * IP Calculation: VM_NET_BASE + "." + (VM_NET_OFFSET + VM_ID)
 * Example: 192.168.111 + "." + (0 + 11) = 192.168.111.11
 *
 * NOTE: This version uses 'renet ops' Go commands instead of bash scripts.
 */
export class OpsManager {
  private readonly config: VMNetworkConfig;
  private readonly vmExecutor: OpsVMExecutor;
  private readonly rustfsManager: OpsRustFSManager;
  private readonly cephManager: OpsCephManager;
  private readonly commandRunner: OpsCommandRunner;
  private readonly vmLifecycle: OpsVMLifecycle;

  constructor() {
    // Auto-detect renet root: use RENET_ROOT env var or resolve from current location
    const renetRoot = process.env.RENET_ROOT ?? path.resolve(__dirname, '../../../../../..');
    const renetBin = `${renetRoot}/bin/renet`;

    // Load configuration from environment
    this.config = this.loadConfig();

    // Initialize helper modules
    this.commandRunner = new OpsCommandRunner(renetBin, renetRoot);
    this.vmExecutor = new OpsVMExecutor();
    this.vmLifecycle = new OpsVMLifecycle(
      this.commandRunner,
      this.vmExecutor,
      this.getAllVMIps.bind(this),
      this.getWorkerVMIps.bind(this),
      this.getCephVMIps.bind(this)
    );
    this.rustfsManager = new OpsRustFSManager(
      this.vmExecutor,
      this.getBridgeVMIp(),
      this.commandRunner.run.bind(this.commandRunner)
    );
    this.cephManager = new OpsCephManager(
      this.getCephVMIps(),
      this.commandRunner.runWithEnv.bind(this.commandRunner)
    );
  }

  /**
   * Load VM network configuration from environment variables.
   * Matches the pattern in ops/scripts/init.sh
   * STRICT: All environment variables are required, no defaults.
   */
  private loadConfig(): VMNetworkConfig {
    const netBase = process.env.VM_NET_BASE;
    if (!netBase) {
      throw new Error('VM_NET_BASE environment variable is required');
    }

    const netOffsetStr = process.env.VM_NET_OFFSET;
    if (netOffsetStr === undefined) {
      throw new Error('VM_NET_OFFSET environment variable is required');
    }
    const netOffset = Number.parseInt(netOffsetStr, 10);

    const bridgeIdStr = process.env.VM_BRIDGE;
    if (!bridgeIdStr) {
      throw new Error('VM_BRIDGE environment variable is required');
    }
    const bridgeId = Number.parseInt(bridgeIdStr, 10);

    // Parse worker IDs from space-separated string
    const workersStr = process.env.VM_WORKERS;
    if (!workersStr) {
      throw new Error('VM_WORKERS environment variable is required');
    }
    const workerIds = workersStr
      .split(/\s+/)
      .map((id) => Number.parseInt(id, 10))
      .filter((id) => !Number.isNaN(id));
    if (workerIds.length === 0) {
      throw new Error('VM_WORKERS must contain at least one worker ID');
    }

    // Parse ceph node IDs (optional - empty means Ceph disabled)
    const cephStr = process.env.VM_CEPH_NODES ?? '';
    const cephIds = cephStr
      .split(/\s+/)
      .map((id) => Number.parseInt(id, 10))
      .filter((id) => !Number.isNaN(id));
    // No error if empty - Ceph is optional for faster test cycles

    return { netBase, netOffset, bridgeId, workerIds, cephIds };
  }

  /**
   * Calculate VM IP address from VM ID.
   * Formula: VM_NET_BASE + "." + (VM_NET_OFFSET + VM_ID)
   */
  calculateVMIp(vmId: number): string {
    return `${this.config.netBase}.${this.config.netOffset + vmId}`;
  }

  /**
   * Get bridge VM IP
   */
  getBridgeVMIp(): string {
    return this.calculateVMIp(this.config.bridgeId);
  }

  /**
   * Get worker VM IPs
   */
  getWorkerVMIps(): string[] {
    return this.config.workerIds.map((id) => this.calculateVMIp(id));
  }

  /**
   * Get Ceph node IPs
   */
  getCephVMIps(): string[] {
    return this.config.cephIds.map((id) => this.calculateVMIp(id));
  }

  /**
   * Get all VM IPs (bridge + workers)
   */
  getVMIps(): string[] {
    return [this.getBridgeVMIp(), ...this.getWorkerVMIps()];
  }

  /**
   * Get all VM IPs including Ceph nodes
   */
  getAllVMIps(): string[] {
    return [...this.getVMIps(), ...this.getCephVMIps()];
  }

  /**
   * Get VM IDs configuration
   */
  getVMIds(): { bridge: number; workers: number[]; ceph: number[] } {
    return {
      bridge: this.config.bridgeId,
      workers: this.config.workerIds,
      ceph: this.config.cephIds,
    };
  }

  /**
   * Get network configuration
   */
  getNetworkConfig(): VMNetworkConfig {
    return { ...this.config };
  }

  /**
   * Check if a VM is reachable via ping
   */
  async isVMReachable(ip: string, timeoutSeconds = 2): Promise<boolean> {
    return this.vmExecutor.isVMReachable(ip, timeoutSeconds);
  }

  /**
   * Check if SSH is available on a VM
   */
  async isSSHReady(ip: string): Promise<boolean> {
    return this.vmExecutor.isSSHReady(ip);
  }

  /**
   * Check if all VMs are running and reachable
   */
  async areAllVMsReady(): Promise<{
    ready: boolean;
    status: Map<string, { reachable: boolean; sshReady: boolean }>;
  }> {
    const status = new Map<string, { reachable: boolean; sshReady: boolean }>();
    let allReady = true;

    for (const ip of this.getVMIps()) {
      const reachable = await this.isVMReachable(ip);
      const sshReady = reachable ? await this.isSSHReady(ip) : false;
      status.set(ip, { reachable, sshReady });

      if (!reachable || !sshReady) {
        allReady = false;
      }
    }

    return { ready: allReady, status };
  }

  /**
   * Check if worker VMs are ready (bridge not required for some tests)
   */
  async areWorkerVMsReady(): Promise<{
    ready: boolean;
    status: Map<string, { reachable: boolean; sshReady: boolean }>;
  }> {
    const status = new Map<string, { reachable: boolean; sshReady: boolean }>();
    let allReady = true;

    for (const ip of this.getWorkerVMIps()) {
      const reachable = await this.isVMReachable(ip);
      const sshReady = reachable ? await this.isSSHReady(ip) : false;
      status.set(ip, { reachable, sshReady });

      if (!reachable || !sshReady) {
        allReady = false;
      }
    }

    return { ready: allReady, status };
  }

  /**
   * Run a renet ops command
   */
  async runOpsCommand(
    subcommands: string[],
    args: string[] = [],
    timeoutMs = 300000
  ): Promise<{ stdout: string; stderr: string; code: number }> {
    return this.commandRunner.run(subcommands, args, timeoutMs);
  }

  /**
   * Run a renet ops command with additional environment variables
   */
  async runOpsCommandWithEnv(
    subcommands: string[],
    args: string[] = [],
    extraEnv: Record<string, string> = {},
    timeoutMs = 300000
  ): Promise<{ stdout: string; stderr: string; code: number }> {
    return this.commandRunner.runWithEnv(subcommands, args, extraEnv, timeoutMs);
  }

  /**
   * Get ops status
   */
  async getStatus(): Promise<{ stdout: string; stderr: string; code: number }> {
    return this.vmLifecycle.getStatus();
  }

  /**
   * Start VMs using ops scripts
   */
  async startVMs(
    options: { force?: boolean; basic?: boolean; parallel?: boolean } = {}
  ): Promise<{ success: boolean; stdout: string; stderr: string }> {
    return this.vmLifecycle.startVMs(options);
  }

  /**
   * Stop all VMs
   */
  async stopVMs(): Promise<{ success: boolean; stdout: string; stderr: string }> {
    return this.vmLifecycle.stopVMs();
  }

  /**
   * Wait for a VM to be ready (ping + SSH)
   */
  async waitForVM(ip: string, timeoutMs = 120000): Promise<boolean> {
    return this.vmExecutor.waitForVM(ip, timeoutMs);
  }

  /**
   * Wait for all VMs to be ready
   */
  async waitForAllVMs(timeoutMs = 180000): Promise<boolean> {
    return this.vmLifecycle.waitForAllVMs(timeoutMs);
  }

  /**
   * Wait for worker VMs to be ready
   */
  async waitForWorkerVMs(timeoutMs = 180000): Promise<boolean> {
    return this.vmLifecycle.waitForWorkerVMs(timeoutMs);
  }

  /**
   * Ensure VMs are running - start them if not
   */
  async ensureVMsRunning(
    options: { basic?: boolean } = {}
  ): Promise<{ success: boolean; wasStarted: boolean; message: string }> {
    return this.vmLifecycle.ensureVMsRunning(options, this.areAllVMsReady.bind(this));
  }

  /**
   * Execute a command on a remote VM via SSH
   */
  async executeOnVM(
    ip: string,
    command: string,
    timeoutMs = 60000
  ): Promise<{ stdout: string; stderr: string; code: number }> {
    return this.vmExecutor.executeOnVM(ip, command, timeoutMs);
  }

  /**
   * Execute a command on all worker VMs in parallel
   */
  async executeOnAllWorkers(
    command: string,
    timeoutMs = 60000
  ): Promise<Map<string, { stdout: string; stderr: string; code: number }>> {
    return this.vmExecutor.executeOnMultipleVMs(this.getWorkerVMIps(), command, timeoutMs);
  }

  /**
   * Check if renet is installed on a VM
   */
  async isRenetInstalledOnVM(ip: string): Promise<boolean> {
    return this.vmExecutor.isRenetInstalledOnVM(ip);
  }

  /**
   * Get renet version on a VM
   */
  async getRenetVersionOnVM(ip: string): Promise<string | null> {
    return this.vmExecutor.getRenetVersionOnVM(ip);
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
   * Soft reset VMs by force restarting them.
   */
  async resetVMs(): Promise<{ success: boolean; duration: number }> {
    return this.vmLifecycle.resetVMs();
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

  /**
   * Verify all VMs (bridge + workers + ceph) are ready.
   * Throws an error if any VM is not reachable or SSH is not available.
   * STRICT: No graceful fallback, tests cannot proceed if VMs are not ready.
   */
  async verifyAllVMsReady(): Promise<void> {
    const allIPs = this.getAllVMIps();
    const notReady: string[] = [];

    console.warn('[OpsManager] Verifying all VMs are ready...');

    for (const ip of allIPs) {
      const reachable = await this.isVMReachable(ip);
      if (!reachable) {
        notReady.push(`${ip} (not reachable)`);
        continue;
      }

      const sshReady = await this.isSSHReady(ip);
      if (!sshReady) {
        notReady.push(`${ip} (SSH not ready)`);
        continue;
      }

      // Check renet is installed
      const renetInstalled = await this.isRenetInstalledOnVM(ip);
      if (!renetInstalled) {
        notReady.push(`${ip} (renet not installed)`);
        continue;
      }

      const version = await this.getRenetVersionOnVM(ip);
      console.warn(`  ✓ ${ip}: renet ${version}`);
    }

    if (notReady.length > 0) {
      throw new Error(`VMs not ready: ${notReady.join(', ')}`);
    }

    console.warn('[OpsManager] All VMs verified and ready');
  }
}

// Singleton instance for shared state across tests
let opsManagerInstance: OpsManager | null = null;

export function getOpsManager(): OpsManager {
  opsManagerInstance ??= new OpsManager();
  return opsManagerInstance;
}
