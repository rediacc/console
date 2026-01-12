import { exec } from "child_process";
import * as fs from "fs";
import * as path from "path";
import { promisify } from "util";
import { getOpsManager, OpsManager } from "./OpsManager";
import {
  DEFAULT_CEPH_POOL_PG_NUM,
  DEFAULT_DATASTORE_PATH,
  DEFAULT_NETWORK_ID,
} from "../../constants";
import type { VaultBuilder } from "../vault/VaultBuilder";

const execAsync = promisify(exec);

export interface QueueTaskOptions {
  function: string;
  machine: string;
  team: string;
  priority?: number;
}

export interface QueueTaskResult {
  taskId: string;
}

export interface ExecResult {
  stdout: string;
  stderr: string;
  code: number;
}

export interface TestFunctionOptions {
  function: string;
  datastorePath?: string;
  repository?: string;
  networkId?: string;
  password?: string;
  size?: string;
  newSize?: string;
  pool?: string;
  pgNum?: string;
  image?: string;
  snapshot?: string;
  clone?: string;
  mountPoint?: string;
  cowSize?: string;
  keepCow?: boolean;
  container?: string;
  command?: string;
  checkpointName?: string;
  sourceMachine?: string;
  destMachine?: string;
  format?: string;
  force?: boolean;
  timeout?: number;
  uid?: string;
  // Filesystem formatting parameters
  filesystem?: string;
  label?: string;
  // backup_push parameters
  destinationType?: "machine" | "storage";
  to?: string;
  machines?: string[];
  storages?: string[];
  dest?: string;
  tag?: string;
  state?: "online" | "offline";
  checkpoint?: boolean;
  override?: boolean;
  grand?: string;
  // backup_pull parameters
  sourceType?: "machine" | "storage";
  from?: string;
  // Setup installation parameters (new vault param fixes)
  installSource?: "apt-repo" | "tar-static" | "deb-local";
  rcloneSource?: "install-script" | "package-manager" | "manual";
  dockerSource?: "docker-repo" | "package-manager" | "snap" | "manual";
  installAmdDriver?: "auto" | "true" | "false";
  installNvidiaDriver?: "auto" | "true" | "false";
  installCriu?: "auto" | "true" | "false" | "manual";
  // Repository prep-only option
  prepOnly?: boolean;
}

/**
 * VM target types for test execution.
 * Tests execute on these VMs via two-hop SSH: Host → Bridge → Target
 */
export type VMTarget = "worker1" | "worker2" | "ceph1" | "ceph2" | "ceph3" | string;

/**
 * Configuration for BridgeTestRunner.
 * targetVM is REQUIRED - no default execution target.
 */
export interface RunnerConfig {
  targetVM: VMTarget;
  timeout?: number;
}

/**
 * Bridge test runner for executing renet commands on VMs via SSH.
 *
 * EXECUTION MODEL:
 * Host Machine → SSH → Bridge VM → SSH → Target VM → renet command
 *
 * All commands execute on the target VM, never locally.
 * Uses: renet bridge once --test-mode --function <name>
 *
 * VM IPs are calculated dynamically via OpsManager:
 * - VM_NET_BASE (required)
 * - VM_NET_OFFSET (required)
 * - VM_BRIDGE (required)
 * - VM_WORKERS (required)
 * - VM_CEPH_NODES (required)
 */
export class BridgeTestRunner {
  private defaultTimeout: number;
  private opsManager: OpsManager;
  private bridgeVM: string;
  private targetVM: string;

  constructor(config: RunnerConfig) {
    if (!config.targetVM) {
      throw new Error("targetVM is required - no default execution target");
    }

    this.opsManager = getOpsManager();
    this.bridgeVM = this.opsManager.getBridgeVMIp();
    this.targetVM = this.resolveTargetVM(config.targetVM);

    const timeoutStr = process.env.BRIDGE_TIMEOUT;
    if (!timeoutStr) {
      throw new Error("BRIDGE_TIMEOUT environment variable is required");
    }
    this.defaultTimeout = parseInt(timeoutStr, 10);
  }

  /**
   * Resolve VM target name to IP address.
   */
  private resolveTargetVM(target: VMTarget): string {
    switch (target) {
      case "worker1":
        return this.opsManager.getWorkerVMIps()[0];
      case "worker2":
        return this.opsManager.getWorkerVMIps()[1];
      case "ceph1":
        return this.opsManager.getCephVMIps()[0];
      case "ceph2":
        return this.opsManager.getCephVMIps()[1];
      case "ceph3":
        return this.opsManager.getCephVMIps()[2];
      default:
        // Assume it's an IP address
        return target;
    }
  }

  /**
   * Factory method to create a runner for worker VMs.
   */
  static forWorker(num: 1 | 2 = 1): BridgeTestRunner {
    return new BridgeTestRunner({ targetVM: `worker${num}` });
  }

  /**
   * Factory method to create a runner for Ceph VMs.
   */
  static forCeph(num: 1 | 2 | 3 = 1): BridgeTestRunner {
    return new BridgeTestRunner({ targetVM: `ceph${num}` });
  }

  /**
   * Get the OpsManager for VM operations.
   */
  getOpsManager(): OpsManager {
    return this.opsManager;
  }

  /**
   * Get the current target VM IP.
   */
  getTargetVM(): string {
    return this.targetVM;
  }

  /**
   * Get bridge VM IP (calculated from ops config).
   */
  getBridgeVM(): string {
    return this.bridgeVM;
  }

  /**
   * Get first worker VM IP (calculated from ops config).
   */
  getWorkerVM(): string {
    return this.opsManager.getWorkerVMIps()[0];
  }

  /**
   * Get second worker VM IP (calculated from ops config).
   */
  getWorkerVM2(): string {
    return this.opsManager.getWorkerVMIps()[1];
  }

  /**
   * Get all worker VM IPs (calculated from ops config).
   */
  getWorkerVMs(): string[] {
    return this.opsManager.getWorkerVMIps();
  }

  /**
   * Get all VM IPs including bridge (calculated from ops config).
   */
  getAllVMs(): string[] {
    return this.opsManager.getVMIps();
  }

  /**
   * Check if a VM is reachable (ping + SSH).
   */
  async isVMReachable(ip: string): Promise<boolean> {
    const reachable = await this.opsManager.isVMReachable(ip);
    if (!reachable) return false;
    return this.opsManager.isSSHReady(ip);
  }

  /**
   * Ensure VMs are running (starts them if not).
   * Uses ops scripts to manage VMs.
   */
  async ensureVMsRunning(
    options: { basic?: boolean } = {},
  ): Promise<{ success: boolean; message: string }> {
    return this.opsManager.ensureVMsRunning(options);
  }

  /**
   * Execute a command on target VM via Bridge VM (two-hop SSH).
   * Pattern: Host → SSH → Bridge → SSH → Target → command
   * Outputs are logged to console so Playwright can capture them.
   */
  async executeViaBridge(command: string, timeout?: number): Promise<ExecResult> {
    const cmdTimeout = timeout ?? this.defaultTimeout;

    // Escape the command for nested SSH
    // First escape for the inner SSH (target), then for outer SSH (bridge)
    const escapedForTarget = command.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
    const escapedForBridge = escapedForTarget.replace(/\\/g, "\\\\").replace(/"/g, '\\"');

    // Two-hop SSH command: Host → Bridge → Target
    const sshCmd = `ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=10 ${this.bridgeVM} "ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=10 ${this.targetVM} \\"${escapedForBridge}\\""`;

    // Log the command being executed
    console.log(`\n[SSH ${this.bridgeVM} → ${this.targetVM}] ${command}`);

    const fallbackDirect = async (reason: string): Promise<ExecResult> => {
      console.log(`[BridgeTestRunner] Falling back to direct SSH to ${this.targetVM}: ${reason}`);
      return this.executeOnVM(this.targetVM, command, timeout);
    };

    try {
      const { stdout, stderr } = await execAsync(sshCmd, { timeout: cmdTimeout });

      // Log outputs for Playwright to capture
      if (stdout.trim()) {
        console.log(`[STDOUT]\n${stdout}`);
      }
      if (stderr.trim()) {
        console.log(`[STDERR]\n${stderr}`);
      }
      console.log(`[EXIT] 0`);

      return { stdout, stderr, code: 0 };
    } catch (error: unknown) {
      const err = error as Error & {
        stdout?: string;
        stderr?: string;
        code?: number;
        killed?: boolean;
      };
      const stdout = err.stdout ?? "";
      const stderr = err.killed
        ? `Command timed out after ${cmdTimeout}ms\n${err.stderr ?? ""}`
        : (err.stderr ?? "");
      const code = err.killed ? 124 : (err.code ?? 1);

      // Log outputs for Playwright to capture
      if (stdout.trim()) {
        console.log(`[STDOUT]\n${stdout}`);
      }
      if (stderr.trim()) {
        console.log(`[STDERR]\n${stderr}`);
      }
      console.log(`[EXIT] ${code}`);

      if (/renet: command not found|No such file or directory/.test(stderr)) {
        return fallbackDirect("renet not found on target via bridge");
      }

      return { stdout, stderr, code };
    }
  }

  /**
   * Execute a command on a remote VM via SSH.
   * Outputs are logged to console so Playwright can capture them.
   */
  async executeOnVM(host: string, command: string, timeout?: number): Promise<ExecResult> {
    const cmdTimeout = timeout ?? this.defaultTimeout;
    const sshCmd = `ssh -o ConnectTimeout=10 -o BatchMode=yes -o StrictHostKeyChecking=no ${host} "${command.replace(/"/g, '\\"')}"`;

    // Log the command being executed
    console.log(`\n[SSH ${host}] ${command}`);

    try {
      const { stdout, stderr } = await execAsync(sshCmd, { timeout: cmdTimeout });

      // Log outputs for Playwright to capture
      if (stdout.trim()) {
        console.log(`[STDOUT]\n${stdout}`);
      }
      if (stderr.trim()) {
        console.log(`[STDERR]\n${stderr}`);
      }
      console.log(`[EXIT] 0`);

      return { stdout, stderr, code: 0 };
    } catch (error: unknown) {
      const err = error as Error & {
        stdout?: string;
        stderr?: string;
        code?: number;
        killed?: boolean;
      };
      const stdout = err.stdout ?? "";
      const stderr = err.killed
        ? `Command timed out after ${cmdTimeout}ms\n${err.stderr ?? ""}`
        : (err.stderr ?? "");
      const code = err.killed ? 124 : (err.code ?? 1);

      // Log outputs for Playwright to capture
      if (stdout.trim()) {
        console.log(`[STDOUT]\n${stdout}`);
      }
      if (stderr.trim()) {
        console.log(`[STDERR]\n${stderr}`);
      }
      console.log(`[EXIT] ${code}`);

      return { stdout, stderr, code };
    }
  }

  /**
   * Test a bridge function on target VM via two-hop SSH.
   * Uses: renet bridge once --test-mode --function <name>
   * Executes: Host → Bridge → Target VM
   */
  async testFunction(opts: TestFunctionOptions): Promise<ExecResult> {
    // Use renet from PATH on the VM (deployed by InfrastructureManager)
    // Always use --debug in e2e tests for full logging visibility
    let cmd = `renet bridge once --test-mode --debug --function ${opts.function}`;

    if (opts.datastorePath) {
      cmd += ` --datastore-path ${opts.datastorePath}`;
    }
    if (opts.repository) {
      cmd += ` --repository ${opts.repository}`;
    }
    const networkId = opts.networkId ?? DEFAULT_NETWORK_ID;
    if (networkId) {
      cmd += ` --network-id ${networkId}`;
    }
    if (opts.password) {
      cmd += ` --password '${opts.password}'`;
    }
    if (opts.size) {
      cmd += ` --size ${opts.size}`;
    }
    if (opts.newSize) {
      cmd += ` --new-size ${opts.newSize}`;
    }
    if (opts.pool) {
      cmd += ` --pool ${opts.pool}`;
    }
    if (opts.pgNum) {
      cmd += ` --pg-num ${opts.pgNum}`;
    }
    if (opts.image) {
      cmd += ` --image ${opts.image}`;
    }
    if (opts.snapshot) {
      cmd += ` --snapshot ${opts.snapshot}`;
    }
    if (opts.clone) {
      cmd += ` --clone ${opts.clone}`;
    }
    if (opts.mountPoint) {
      cmd += ` --mount-point ${opts.mountPoint}`;
    }
    if (opts.cowSize) {
      cmd += ` --cow-size ${opts.cowSize}`;
    }
    if (opts.keepCow) {
      cmd += ` --keep-cow`;
    }
    if (opts.container) {
      cmd += ` --container ${opts.container}`;
    }
    if (opts.command) {
      cmd += ` --command '${opts.command}'`;
    }
    if (opts.checkpointName) {
      cmd += ` --checkpoint-name ${opts.checkpointName}`;
    }
    if (opts.sourceMachine) {
      cmd += ` --source-machine ${opts.sourceMachine}`;
    }
    if (opts.destMachine) {
      cmd += ` --dest-machine ${opts.destMachine}`;
    }
    if (opts.format) {
      cmd += ` --format ${opts.format}`;
    }
    if (opts.filesystem) {
      cmd += ` --filesystem ${opts.filesystem}`;
    }
    if (opts.label) {
      cmd += ` --label ${opts.label}`;
    }
    if (opts.force) {
      cmd += ` --force`;
    }
    if (opts.uid) {
      cmd += ` --uid ${opts.uid}`;
    }
    // Setup installation parameters
    if (opts.installSource) {
      cmd += ` --install-source ${opts.installSource}`;
    }
    if (opts.rcloneSource) {
      cmd += ` --rclone-source ${opts.rcloneSource}`;
    }
    if (opts.dockerSource) {
      cmd += ` --docker-source ${opts.dockerSource}`;
    }
    if (opts.installAmdDriver) {
      cmd += ` --install-amd-driver ${opts.installAmdDriver}`;
    }
    if (opts.installNvidiaDriver) {
      cmd += ` --install-nvidia-driver ${opts.installNvidiaDriver}`;
    }
    if (opts.installCriu) {
      cmd += ` --install-criu ${opts.installCriu}`;
    }
    // Repository prep-only option
    if (opts.prepOnly) {
      cmd += ` --prep-only`;
    }
    // Note: backup_push/pull parameters (destinationType, tag, state, checkpoint, etc.)
    // are passed via vault when queuing tasks, not as CLI flags in test mode.
    // The test mode CLI only supports destMachine and sourceMachine for basic testing.
    // Full parameter testing requires the queue API integration.

    // Execute via two-hop SSH: Host → Bridge → Target
    return this.executeViaBridge(cmd, opts.timeout);
  }

  /**
   * Test a simple function (ping, nop, hello) with minimal options.
   */
  async testSimpleFunction(functionName: string): Promise<ExecResult> {
    return this.testFunction({ function: functionName });
  }

  /**
   * Get renet version on target VM to verify it's working.
   */
  async getRenetVersion(): Promise<ExecResult> {
    return this.executeViaBridge("renet version");
  }

  /**
   * Execute on bridge VM via SSH.
   */
  async executeOnBridge(command: string, timeout?: number): Promise<ExecResult> {
    return this.executeOnVM(this.getBridgeVM(), command, timeout);
  }

  /**
   * Execute on worker VM via SSH.
   */
  async executeOnWorker(command: string, timeout?: number): Promise<ExecResult> {
    return this.executeOnVM(this.getWorkerVM(), command, timeout);
  }

  /**
   * Execute on second worker VM via SSH.
   */
  async executeOnWorker2(command: string, timeout?: number): Promise<ExecResult> {
    return this.executeOnVM(this.getWorkerVM2(), command, timeout);
  }

  /**
   * Check if renet is available and working on target VM.
   */
  async isRenetAvailable(): Promise<boolean> {
    const result = await this.getRenetVersion();
    return result.code === 0;
  }

  /**
   * Get all Ceph VM IPs.
   */
  getCephVMs(): string[] {
    return this.opsManager.getCephVMIps();
  }

  /**
   * Execute a command on the target Ceph VM.
   * Alias for executeViaBridge for clarity in Ceph-specific tests.
   */
  async executeOnCeph(command: string, timeout?: number): Promise<ExecResult> {
    return this.executeViaBridge(command, timeout);
  }

  // ===========================================================================
  // System Check Functions (15+)
  // ===========================================================================

  async ping(): Promise<ExecResult> {
    return this.testSimpleFunction("machine_ping");
  }

  async nop(): Promise<ExecResult> {
    return this.testSimpleFunction("daemon_nop");
  }

  async hello(): Promise<ExecResult> {
    return this.testSimpleFunction("machine_version");
  }

  async sshTest(): Promise<ExecResult> {
    return this.testSimpleFunction("machine_ssh_test");
  }

  async checkKernelCompatibility(): Promise<ExecResult> {
    return this.testSimpleFunction("machine_check_kernel");
  }

  async checkSetup(): Promise<ExecResult> {
    return this.testSimpleFunction("machine_check_setup");
  }

  async checkMemory(): Promise<ExecResult> {
    return this.testSimpleFunction("machine_check_memory");
  }

  async checkSudo(): Promise<ExecResult> {
    return this.testSimpleFunction("machine_check_sudo");
  }

  async checkTools(): Promise<ExecResult> {
    return this.testSimpleFunction("machine_check_tools");
  }

  async checkRenet(): Promise<ExecResult> {
    return this.testSimpleFunction("machine_check_renet");
  }

  async checkCriu(): Promise<ExecResult> {
    return this.testSimpleFunction("machine_check_criu");
  }

  async checkBtrfs(): Promise<ExecResult> {
    return this.testSimpleFunction("machine_check_btrfs");
  }

  async checkDrivers(): Promise<ExecResult> {
    return this.testSimpleFunction("machine_check_drivers");
  }

  async checkSystem(): Promise<ExecResult> {
    return this.testSimpleFunction("machine_check_system");
  }

  async checkUsers(): Promise<ExecResult> {
    return this.testSimpleFunction("machine_check_users");
  }

  async checkRediaccCli(): Promise<ExecResult> {
    return this.testSimpleFunction("machine_check_cli");
  }

  async checkDatastore(datastorePath?: string): Promise<ExecResult> {
    return this.testFunction({
      function: "datastore_status",
      datastorePath,
    });
  }

  // ===========================================================================
  // Machine Setup Functions (4)
  // ===========================================================================

  async setup(datastorePath?: string, uid?: string): Promise<ExecResult> {
    return this.testFunction({
      function: "setup",
      datastorePath,
      uid,
    });
  }

  async osSetup(datastorePath?: string, uid?: string): Promise<ExecResult> {
    // os_setup is now an alias for setup
    return this.testFunction({
      function: "setup",
      datastorePath,
      uid,
    });
  }

  /**
   * Setup with all installation parameters.
   * Tests the 6 new installation params added for vault parameter fixes.
   */
  async setupWithOptions(options: {
    datastorePath?: string;
    uid?: string;
    from?: "apt-repo" | "tar-static" | "deb-local";
    rcloneSource?: "install-script" | "package-manager" | "manual";
    dockerSource?: "docker-repo" | "package-manager" | "snap" | "manual";
    installAmdDriver?: "auto" | "true" | "false";
    installNvidiaDriver?: "auto" | "true" | "false";
    installCriu?: "auto" | "true" | "false" | "manual";
  }): Promise<ExecResult> {
    return this.testFunction({
      function: "setup",
      datastorePath: options.datastorePath,
      uid: options.uid,
      installSource: options.from,
      rcloneSource: options.rcloneSource,
      dockerSource: options.dockerSource,
      installAmdDriver: options.installAmdDriver,
      installNvidiaDriver: options.installNvidiaDriver,
      installCriu: options.installCriu,
    });
  }

  async fixUserGroups(uid?: string): Promise<ExecResult> {
    return this.testFunction({
      function: "machine_fix_groups",
      uid,
    });
  }

  // ===========================================================================
  // Datastore Functions (7)
  // ===========================================================================

  async datastoreInit(size: string, datastorePath?: string, force?: boolean): Promise<ExecResult> {
    return this.testFunction({
      function: "datastore_init",
      size,
      datastorePath,
      force,
    });
  }

  async datastoreMount(datastorePath?: string): Promise<ExecResult> {
    return this.testFunction({
      function: "datastore_mount",
      datastorePath,
    });
  }

  async datastoreUnmount(datastorePath?: string): Promise<ExecResult> {
    return this.testFunction({
      function: "datastore_unmount",
      datastorePath,
    });
  }

  async datastoreExpand(newSize: string, datastorePath?: string): Promise<ExecResult> {
    return this.testFunction({
      function: "datastore_expand",
      newSize,
      datastorePath,
    });
  }

  async datastoreResize(newSize: string, datastorePath?: string): Promise<ExecResult> {
    return this.testFunction({
      function: "datastore_resize",
      newSize,
      datastorePath,
    });
  }

  async datastoreValidate(datastorePath?: string): Promise<ExecResult> {
    return this.testFunction({
      function: "datastore_validate",
      datastorePath,
    });
  }

  // ===========================================================================
  // Repository Functions (12)
  // ===========================================================================

  async repositoryNew(
    name: string,
    size: string,
    password?: string,
    datastorePath?: string,
  ): Promise<ExecResult> {
    return this.testFunction({
      function: "repository_create",
      repository: name,
      size,
      password,
      datastorePath,
    });
  }

  async repositoryRm(name: string, datastorePath?: string): Promise<ExecResult> {
    return this.testFunction({
      function: "repository_delete",
      repository: name,
      datastorePath,
    });
  }

  async repositoryMount(
    name: string,
    password?: string,
    datastorePath?: string,
  ): Promise<ExecResult> {
    return this.testFunction({
      function: "repository_mount",
      repository: name,
      password,
      datastorePath,
    });
  }

  async repositoryUnmount(name: string, datastorePath?: string): Promise<ExecResult> {
    return this.testFunction({
      function: "repository_unmount",
      repository: name,
      datastorePath,
    });
  }

  async repositoryUp(
    name: string,
    datastorePath?: string,
    networkId?: string,
  ): Promise<ExecResult> {
    return this.testFunction({
      function: "repository_up",
      repository: name,
      datastorePath,
      networkId,
    });
  }

  /**
   * Repository up with prep-only option.
   * Prepares the repository without starting services.
   */
  async repositoryUpPrepOnly(
    name: string,
    datastorePath?: string,
    networkId?: string,
  ): Promise<ExecResult> {
    return this.testFunction({
      function: "repository_up",
      repository: name,
      datastorePath,
      networkId,
      prepOnly: true,
    });
  }

  async repositoryDown(
    name: string,
    datastorePath?: string,
    networkId?: string,
  ): Promise<ExecResult> {
    return this.testFunction({
      function: "repository_down",
      repository: name,
      datastorePath,
      networkId,
    });
  }

  async repositoryList(datastorePath?: string): Promise<ExecResult> {
    return this.testFunction({
      function: "repository_list",
      datastorePath,
    });
  }

  async repositoryResize(
    name: string,
    newSize: string,
    password?: string,
    datastorePath?: string,
  ): Promise<ExecResult> {
    return this.testFunction({
      function: "repository_resize",
      repository: name,
      newSize,
      password,
      datastorePath,
    });
  }

  async repositoryInfo(name: string, datastorePath?: string): Promise<ExecResult> {
    return this.testFunction({
      function: "repository_info",
      repository: name,
      datastorePath,
    });
  }

  async repositoryStatus(name: string, datastorePath?: string): Promise<ExecResult> {
    return this.testFunction({
      function: "repository_status",
      repository: name,
      datastorePath,
    });
  }

  async repositoryValidate(name: string, datastorePath?: string): Promise<ExecResult> {
    return this.testFunction({
      function: "repository_validate",
      repository: name,
      datastorePath,
    });
  }

  async repositoryGrow(
    name: string,
    newSize: string,
    password?: string,
    datastorePath?: string,
  ): Promise<ExecResult> {
    return this.testFunction({
      function: "repository_expand",
      repository: name,
      newSize,
      password,
      datastorePath,
    });
  }

  // ===========================================================================
  // Ceph Pool Functions (6)
  // ===========================================================================

  async cephHealth(): Promise<ExecResult> {
    return this.testSimpleFunction("ceph_health");
  }

  async cephPoolCreate(pool: string, pgNum?: string): Promise<ExecResult> {
    const resolvedPgNum = pgNum ?? process.env.CEPH_POOL_PG_NUM ?? DEFAULT_CEPH_POOL_PG_NUM;
    return this.testFunction({
      function: "ceph_pool_create",
      pool,
      pgNum: resolvedPgNum,
    });
  }

  async cephPoolDelete(pool: string): Promise<ExecResult> {
    return this.testFunction({
      function: "ceph_pool_delete",
      pool,
    });
  }

  async cephPoolList(): Promise<ExecResult> {
    return this.testSimpleFunction("ceph_pool_list");
  }

  async cephPoolInfo(pool: string): Promise<ExecResult> {
    return this.testFunction({
      function: "ceph_pool_info",
      pool,
    });
  }

  async cephPoolStats(pool: string): Promise<ExecResult> {
    return this.testFunction({
      function: "ceph_pool_stats",
      pool,
    });
  }

  // ===========================================================================
  // Ceph Image Functions (6)
  // ===========================================================================

  async cephImageCreate(pool: string, image: string, size: string): Promise<ExecResult> {
    return this.testFunction({
      function: "ceph_image_create",
      pool,
      image,
      size,
    });
  }

  async cephImageDelete(pool: string, image: string): Promise<ExecResult> {
    return this.testFunction({
      function: "ceph_image_delete",
      pool,
      image,
    });
  }

  async cephImageList(pool: string): Promise<ExecResult> {
    return this.testFunction({
      function: "ceph_image_list",
      pool,
    });
  }

  async cephImageInfo(pool: string, image: string): Promise<ExecResult> {
    return this.testFunction({
      function: "ceph_image_info",
      pool,
      image,
    });
  }

  async cephImageResize(pool: string, image: string, newSize: string): Promise<ExecResult> {
    return this.testFunction({
      function: "ceph_image_resize",
      pool,
      image,
      newSize,
    });
  }

  async cephImageMap(pool: string, image: string): Promise<ExecResult> {
    return this.testFunction({
      function: "ceph_image_map",
      pool,
      image,
    });
  }

  async cephImageUnmap(pool: string, image: string): Promise<ExecResult> {
    return this.testFunction({
      function: "ceph_image_unmap",
      pool,
      image,
    });
  }

  /**
   * Format an RBD image with a filesystem.
   * Maps the image, formats with specified filesystem, and unmaps.
   * Used to prepare images for COW mount by adding a filesystem.
   */
  async cephImageFormat(
    pool: string,
    image: string,
    filesystem = "btrfs",
    label?: string,
  ): Promise<ExecResult> {
    return this.testFunction({
      function: "ceph_image_format",
      pool,
      image,
      filesystem,
      label,
    });
  }

  // ===========================================================================
  // Ceph Snapshot Functions (6)
  // ===========================================================================

  async cephSnapshotCreate(pool: string, image: string, snapshot: string): Promise<ExecResult> {
    return this.testFunction({
      function: "ceph_snapshot_create",
      pool,
      image,
      snapshot,
    });
  }

  async cephSnapshotDelete(pool: string, image: string, snapshot: string): Promise<ExecResult> {
    return this.testFunction({
      function: "ceph_snapshot_delete",
      pool,
      image,
      snapshot,
    });
  }

  async cephSnapshotList(pool: string, image: string): Promise<ExecResult> {
    return this.testFunction({
      function: "ceph_snapshot_list",
      pool,
      image,
    });
  }

  async cephSnapshotProtect(pool: string, image: string, snapshot: string): Promise<ExecResult> {
    return this.testFunction({
      function: "ceph_snapshot_protect",
      pool,
      image,
      snapshot,
    });
  }

  async cephSnapshotUnprotect(pool: string, image: string, snapshot: string): Promise<ExecResult> {
    return this.testFunction({
      function: "ceph_snapshot_unprotect",
      pool,
      image,
      snapshot,
    });
  }

  async cephSnapshotRollback(pool: string, image: string, snapshot: string): Promise<ExecResult> {
    return this.testFunction({
      function: "ceph_snapshot_rollback",
      pool,
      image,
      snapshot,
    });
  }

  // ===========================================================================
  // Ceph Clone Functions (6)
  // ===========================================================================

  async cephCloneCreate(
    pool: string,
    image: string,
    snapshot: string,
    clone: string,
  ): Promise<ExecResult> {
    return this.testFunction({
      function: "ceph_clone_create",
      pool,
      image,
      snapshot,
      clone,
    });
  }

  async cephCloneDelete(pool: string, clone: string): Promise<ExecResult> {
    return this.testFunction({
      function: "ceph_clone_delete",
      pool,
      clone,
    });
  }

  async cephCloneList(pool: string, image: string, snapshot: string): Promise<ExecResult> {
    return this.testFunction({
      function: "ceph_clone_list",
      pool,
      image,
      snapshot,
    });
  }

  async cephCloneFlatten(pool: string, clone: string): Promise<ExecResult> {
    return this.testFunction({
      function: "ceph_clone_flatten",
      pool,
      clone,
    });
  }

  /**
   * Mount a Ceph clone with Copy-on-Write overlay.
   * This is the CORE Ceph use case for read-write access to immutable clones.
   */
  async cephCloneMount(
    clone: string,
    mountPoint: string,
    cowSize?: string,
    pool?: string,
  ): Promise<ExecResult> {
    return this.testFunction({
      function: "ceph_clone_mount",
      clone,
      mountPoint,
      cowSize: cowSize ?? "10G",
      pool,
    });
  }

  /**
   * Unmount a Ceph clone. CRITICAL: Must follow exact teardown order.
   * 1. sync & umount filesystem
   * 2. dmsetup remove cow device
   * 3. losetup detach loop device
   * 4. rbd unmap device
   * 5. delete COW file (unless keepCow)
   *
   * @param clone - Clone name
   * @param keepCow - Keep COW file after unmount
   * @param pool - Ceph pool name
   * @param force - Force unmount even if busy
   */
  async cephCloneUnmount(
    clone: string,
    keepCow?: boolean,
    pool?: string,
    force?: boolean,
  ): Promise<ExecResult> {
    return this.testFunction({
      function: "ceph_clone_unmount",
      clone,
      keepCow,
      pool,
      force,
    });
  }

  // ===========================================================================
  // Container Functions (11)
  // ===========================================================================

  async containerStart(
    name: string,
    repository?: string,
    datastorePath?: string,
    networkId?: string,
  ): Promise<ExecResult> {
    return this.testFunction({
      function: "container_start",
      container: name,
      repository,
      datastorePath,
      networkId,
    });
  }

  async containerStop(
    name: string,
    repository?: string,
    datastorePath?: string,
    networkId?: string,
  ): Promise<ExecResult> {
    return this.testFunction({
      function: "container_stop",
      container: name,
      repository,
      datastorePath,
      networkId,
    });
  }

  async containerRestart(
    name: string,
    repository?: string,
    datastorePath?: string,
    networkId?: string,
  ): Promise<ExecResult> {
    return this.testFunction({
      function: "container_restart",
      container: name,
      repository,
      datastorePath,
      networkId,
    });
  }

  async containerLogs(
    name: string,
    repository?: string,
    datastorePath?: string,
    networkId?: string,
  ): Promise<ExecResult> {
    return this.testFunction({
      function: "container_logs",
      container: name,
      repository,
      datastorePath,
      networkId,
    });
  }

  async containerExec(
    name: string,
    command: string,
    repository?: string,
    datastorePath?: string,
    networkId?: string,
  ): Promise<ExecResult> {
    return this.testFunction({
      function: "container_exec",
      container: name,
      command,
      repository,
      datastorePath,
      networkId,
    });
  }

  async containerInspect(
    name: string,
    repository?: string,
    datastorePath?: string,
    networkId?: string,
  ): Promise<ExecResult> {
    return this.testFunction({
      function: "container_inspect",
      container: name,
      repository,
      datastorePath,
      networkId,
    });
  }

  async containerStats(
    name: string,
    repository?: string,
    datastorePath?: string,
    networkId?: string,
  ): Promise<ExecResult> {
    return this.testFunction({
      function: "container_stats",
      container: name,
      repository,
      datastorePath,
      networkId,
    });
  }

  async containerList(
    repository?: string,
    datastorePath?: string,
    networkId?: string,
  ): Promise<ExecResult> {
    return this.testFunction({
      function: "container_list",
      repository,
      datastorePath,
      networkId,
    });
  }

  async containerKill(
    name: string,
    repository?: string,
    datastorePath?: string,
    networkId?: string,
  ): Promise<ExecResult> {
    return this.testFunction({
      function: "container_kill",
      container: name,
      repository,
      datastorePath,
      networkId,
    });
  }

  async containerPause(
    name: string,
    repository?: string,
    datastorePath?: string,
    networkId?: string,
  ): Promise<ExecResult> {
    return this.testFunction({
      function: "container_pause",
      container: name,
      repository,
      datastorePath,
      networkId,
    });
  }

  async containerUnpause(
    name: string,
    repository?: string,
    datastorePath?: string,
    networkId?: string,
  ): Promise<ExecResult> {
    return this.testFunction({
      function: "container_unpause",
      container: name,
      repository,
      datastorePath,
      networkId,
    });
  }

  // ===========================================================================
  // Daemon Functions (10)
  // ===========================================================================

  async daemonSetup(networkId?: string): Promise<ExecResult> {
    return this.testFunction({
      function: "daemon_setup",
      networkId,
    });
  }

  async daemonTeardown(networkId?: string): Promise<ExecResult> {
    return this.testFunction({
      function: "daemon_teardown",
      networkId,
    });
  }

  async daemonStart(
    repository?: string,
    datastorePath?: string,
    networkId?: string,
  ): Promise<ExecResult> {
    return this.testFunction({
      function: "daemon_start",
      repository,
      datastorePath,
      networkId,
    });
  }

  async daemonStop(
    repository?: string,
    datastorePath?: string,
    networkId?: string,
  ): Promise<ExecResult> {
    return this.testFunction({
      function: "daemon_stop",
      repository,
      datastorePath,
      networkId,
    });
  }

  async daemonStatus(
    repository?: string,
    datastorePath?: string,
    networkId?: string,
  ): Promise<ExecResult> {
    return this.testFunction({
      function: "daemon_status",
      repository,
      datastorePath,
      networkId,
    });
  }

  async daemonRestart(
    repository?: string,
    datastorePath?: string,
    networkId?: string,
  ): Promise<ExecResult> {
    return this.testFunction({
      function: "daemon_restart",
      repository,
      datastorePath,
      networkId,
    });
  }

  async daemonLogs(
    repository?: string,
    datastorePath?: string,
    networkId?: string,
  ): Promise<ExecResult> {
    return this.testFunction({
      function: "daemon_logs",
      repository,
      datastorePath,
      networkId,
    });
  }

  async renetStart(networkId?: string): Promise<ExecResult> {
    return this.testFunction({ function: "daemon_start", networkId });
  }

  async renetStop(networkId?: string): Promise<ExecResult> {
    return this.testFunction({ function: "daemon_stop", networkId });
  }

  async renetStatus(networkId?: string): Promise<ExecResult> {
    return this.testFunction({ function: "daemon_status", networkId });
  }

  // ===========================================================================
  // Backup/Checkpoint Functions (9)
  // ===========================================================================

  /**
   * Push repository to a destination machine.
   * Uses backup_push with destinationType=machine.
   */
  async push(repository: string, destMachine: string, datastorePath?: string): Promise<ExecResult> {
    return this.testFunction({
      function: "backup_push",
      repository,
      destMachine,
      datastorePath,
      destinationType: "machine",
    });
  }

  /**
   * Pull repository from a source machine.
   * Uses backup_pull with sourceType=machine.
   */
  async pull(
    repository: string,
    sourceMachine: string,
    datastorePath?: string,
  ): Promise<ExecResult> {
    return this.testFunction({
      function: "backup_pull",
      repository,
      sourceMachine,
      datastorePath,
      sourceType: "machine",
    });
  }

  /**
   * Push repository with all available options.
   * Supports both machine and storage destinations.
   */
  async pushWithOptions(
    repository: string,
    options: {
      destinationType?: "machine" | "storage";
      to?: string;
      machines?: string[];
      storages?: string[];
      dest?: string;
      tag?: string;
      state?: "online" | "offline";
      checkpoint?: boolean;
      override?: boolean;
      grand?: string;
      datastorePath?: string;
      destMachine?: string;
    },
  ): Promise<ExecResult> {
    return this.testFunction({
      function: "backup_push",
      repository,
      ...options,
    });
  }

  /**
   * Pull repository with all available options.
   * Supports both machine and storage sources.
   */
  async pullWithOptions(
    repository: string,
    options: {
      sourceType?: "machine" | "storage";
      from?: string;
      grand?: string;
      datastorePath?: string;
      sourceMachine?: string;
    },
  ): Promise<ExecResult> {
    return this.testFunction({
      function: "backup_pull",
      repository,
      ...options,
    });
  }

  /**
   * Backup repository to storage.
   * Uses backup_push with destinationType=storage.
   * @deprecated Legacy wrapper - use pushWithOptions() directly
   */
  async backup(
    repository: string,
    datastorePath?: string,
    storageName?: string,
  ): Promise<ExecResult> {
    return this.testFunction({
      function: "backup_push",
      repository,
      datastorePath,
      destinationType: "storage",
      to: storageName,
    });
  }

  /**
   * Deploy repository to a machine.
   * Uses backup_push with destinationType=machine.
   * @deprecated Legacy wrapper - use pushWithOptions() directly
   */
  async deploy(
    repository: string,
    destMachine: string,
    datastorePath?: string,
  ): Promise<ExecResult> {
    return this.testFunction({
      function: "backup_push",
      repository,
      destMachine,
      datastorePath,
      destinationType: "machine",
    });
  }

  async checkpointCreate(
    repository: string,
    checkpointName: string,
    datastorePath?: string,
    networkId?: string | number,
  ): Promise<ExecResult> {
    return this.testFunction({
      function: "checkpoint_create",
      repository,
      checkpointName,
      datastorePath,
      networkId: networkId !== undefined ? String(networkId) : undefined,
    });
  }

  async checkpointRestore(
    repository: string,
    checkpointName: string,
    datastorePath?: string,
    networkId?: string | number,
  ): Promise<ExecResult> {
    return this.testFunction({
      function: "checkpoint_restore",
      repository,
      checkpointName,
      datastorePath,
      networkId: networkId !== undefined ? String(networkId) : undefined,
    });
  }

  // NOTE: checkpoint_delete, checkpoint_list, checkpoint_info functions do not exist in Go
  // Available checkpoint functions: checkpoint_create, checkpoint_restore, checkpoint_validate, checkpoint_cleanup, checkpoint_check_compat

  // ===========================================================================
  // Multi-Machine Helpers
  // ===========================================================================

  /**
   * Execute a command on all worker VMs in parallel.
   */
  async executeOnAllWorkers(command: string, timeout?: number): Promise<Map<string, ExecResult>> {
    const workers = this.getWorkerVMs();
    const results = new Map<string, ExecResult>();

    const promises = workers.map(async (vm) => {
      const result = await this.executeOnVM(vm, command, timeout);
      results.set(vm, result);
    });

    await Promise.all(promises);
    return results;
  }

  /**
   * Test a bridge function on a specific machine via SSH.
   * Uses `renet` directly (assumes it's in PATH on the VM).
   */
  async testFunctionOnMachine(host: string, opts: TestFunctionOptions): Promise<ExecResult> {
    // Always use --debug in e2e tests for full logging visibility
    let cmd = `renet bridge once --test-mode --debug --function ${opts.function}`;

    if (opts.datastorePath) {
      cmd += ` --datastore-path ${opts.datastorePath}`;
    }
    if (opts.repository) {
      cmd += ` --repository ${opts.repository}`;
    }
    if (opts.networkId) {
      cmd += ` --network-id ${opts.networkId}`;
    }
    if (opts.size) {
      cmd += ` --size ${opts.size}`;
    }
    if (opts.force) {
      cmd += ` --force`;
    }

    return this.executeOnVM(host, cmd, opts.timeout);
  }

  /**
   * Execute a direct renet CLI command on a specific machine via SSH.
   * For commands that aren't available through bridge once (e.g., setup, datastore).
   */
  async executeRenetOnMachine(
    host: string,
    renetCommand: string,
    timeout?: number,
  ): Promise<ExecResult> {
    return this.executeOnVM(host, `renet ${renetCommand}`, timeout);
  }

  /**
   * Check setup status on a specific machine.
   */
  async checkSetupOnMachine(host: string): Promise<ExecResult> {
    // machine_check_system is available through bridge once
    return this.executeOnVM(host, "renet bridge once --test-mode --function machine_check_system");
  }

  /**
   * Check datastore status on a specific machine.
   */
  async checkDatastoreOnMachine(host: string, datastorePath: string): Promise<ExecResult> {
    // check_datastore may need direct CLI call
    return this.executeOnVM(
      host,
      `renet datastore status --path ${datastorePath} 2>&1 || echo "datastore check completed"`,
    );
  }

  /**
   * List repositories on a specific machine.
   */
  async listRepositoriesOnMachine(host: string, datastorePath: string): Promise<ExecResult> {
    return this.executeOnVM(
      host,
      `renet repository list --datastore ${datastorePath} 2>&1 || echo "list completed"`,
    );
  }

  // ===========================================================================
  // Output Helpers
  // ===========================================================================

  /**
   * Get combined output (stdout + stderr) from result.
   * Useful for checking output that may be in either stream.
   */
  getCombinedOutput(result: ExecResult): string {
    return (result.stdout + result.stderr).toLowerCase();
  }

  /**
   * Check if result has no shell syntax errors.
   * @deprecated Use hasValidCommandSyntax() for syntax tests, isSuccess() for execution tests
   */
  hasNoSyntaxErrors(result: ExecResult): boolean {
    const output = this.getCombinedOutput(result);
    return (
      !output.includes("syntax error") &&
      !output.includes("unexpected token") &&
      !output.includes("bash:")
    );
  }

  /**
   * Check if command was built with valid syntax and flags.
   * Use this for "should not have shell syntax errors" tests.
   *
   * Checks for CLI/syntax errors:
   * - Shell syntax errors (bash parsing)
   * - Unknown CLI flags
   * - Missing required CLI flags
   *
   * Does NOT fail on runtime errors like:
   * - "repository not found" (requires actual data)
   * - "network ID not detected" (requires environment)
   */
  hasValidCommandSyntax(result: ExecResult): boolean {
    const output = this.getCombinedOutput(result);
    return (
      !output.includes("syntax error") &&
      !output.includes("unexpected token") &&
      !output.includes("bash:") &&
      !output.includes("unknown flag") &&
      !output.includes("required flag") &&
      !output.includes("unknown function")
    );
  }

  /**
   * Check if command executed successfully.
   * Checks: exit code 0, no "unknown function" error, no fatal errors.
   */
  isSuccess(result: ExecResult): boolean {
    if (result.code !== 0) {
      return false;
    }
    const output = this.getCombinedOutput(result);
    // Match renet-specific error format (starts with time=), not third-party logs like Docker daemon
    const hasRenetError = /^time="[^"]*" level=(error|fatal)/m.test(output);
    return (
      !output.includes("unknown function") &&
      !hasRenetError &&
      !output.includes("syntax error") &&
      !output.includes("unexpected token") &&
      !output.includes("bash:")
    );
  }

  /**
   * Check if function is not implemented (for documenting which functions need work).
   */
  isNotImplemented(result: ExecResult): boolean {
    const output = this.getCombinedOutput(result);
    return output.includes("unknown function") || output.includes("not implemented");
  }

  /**
   * Get error message from result.
   */
  getErrorMessage(result: ExecResult): string {
    const output = result.stdout + result.stderr;
    const fatalMatch = output.match(/level=fatal msg="([^"]+)"/);
    if (fatalMatch) {
      return fatalMatch[1];
    }
    const errorMatch = output.match(/level=error msg="([^"]+)"/);
    if (errorMatch) {
      return errorMatch[1];
    }
    if (result.code !== 0) {
      return `Exit code: ${result.code}`;
    }
    return "";
  }

  // ===========================================================================
  // Test Isolation
  // ===========================================================================

  /**
   * Reset worker VM to clean state for test isolation.
   * Tears down daemon, unmounts datastore, removes backing file.
   * Call in test.beforeAll() for groups that need fresh datastore.
   */
  async resetWorkerState(datastorePath = DEFAULT_DATASTORE_PATH): Promise<void> {
    console.log(`\n[Reset] Cleaning worker state at ${datastorePath}...`);

    // 1. Force teardown daemon (stops containers, unmounts repos)
    // Note: --network-id is required since renet now enforces it
    await this.executeViaBridge(
      `sudo renet daemon teardown --network-id ${DEFAULT_NETWORK_ID} --force 2>/dev/null || true`,
    );

    // 2. Kill any processes using the datastore (prevents busy mount)
    // Note: Don't use -k flag here as it could kill the SSH session itself
    await this.executeViaBridge(
      `sudo lsof +D ${datastorePath} 2>/dev/null | awk 'NR>1 {print $2}' | xargs -r sudo kill 2>/dev/null || true`,
    );

    // 3. Sync filesystem before unmount
    await this.executeViaBridge("sync");

    // 4. Unmount datastore - try normal first, then lazy unmount as fallback
    await this.executeViaBridge(
      `mountpoint -q ${datastorePath} && (sudo umount ${datastorePath} 2>/dev/null || sudo umount -l ${datastorePath}) || true`,
    );

    // 5. Detach any loop devices associated with the backing file
    await this.executeViaBridge(
      `losetup -j ${datastorePath}.img 2>/dev/null | cut -d: -f1 | xargs -r sudo losetup -d 2>/dev/null || true`,
    );

    // 6. Remove datastore backing file
    await this.executeViaBridge(`sudo rm -f ${datastorePath}.img`);

    // 7. Clean up any leftover files in datastore directory (including hidden files)
    await this.executeViaBridge(
      `sudo rm -rf ${datastorePath}/* ${datastorePath}/.* 2>/dev/null || true`,
    );

    // 8. Remove datastore marker/metadata if any
    await this.executeViaBridge(`sudo rm -f ${datastorePath}/.datastore 2>/dev/null || true`);

    console.log("[Reset] Worker state cleaned");
  }

  // ===========================================================================
  // File Operations
  // ===========================================================================

  /**
   * Write a file to a mounted repository.
   * Uses base64 encoding to safely handle special characters.
   * Uses sudo because repository mounts may have restricted permissions.
   *
   * Repository structure:
   * - Datastore: {datastorePath}
   * - Mounts: {datastorePath}/mounts/{repositoryName}  ← where content is accessible
   */
  async writeFileToRepository(
    repositoryName: string,
    filePath: string,
    content: string,
    datastorePath: string,
  ): Promise<ExecResult> {
    const base64Content = Buffer.from(content).toString("base64");
    // Repository content is at {datastore}/mounts/{repositoryName}
    const mountPath = `${datastorePath}/mounts/${repositoryName}`;
    const fullPath = `${mountPath}/${filePath}`;

    return this.executeViaBridge(
      `sudo mkdir -p "$(dirname ${fullPath})" && echo "${base64Content}" | base64 -d | sudo tee ${fullPath} > /dev/null`,
    );
  }

  /**
   * Check if a Docker container is running in a network-isolated docker daemon.
   * Uses sudo because Docker daemon access may require elevated privileges.
   * @param containerName The container name to check
   * @param networkId Network ID for network-isolated docker daemon (uses socket at /var/run/rediacc/docker-{networkId}.sock)
   */
  async isContainerRunning(containerName: string, networkId: string): Promise<boolean> {
    const result = await this.executeViaBridge(
      `sudo docker -H unix:///var/run/rediacc/docker-${networkId}.sock ps --filter "name=^${containerName}$" --format "{{.Names}}" | grep -q "^${containerName}$" && echo "running" || echo "stopped"`,
    );
    return result.stdout.trim() === "running";
  }

  // ===========================================================================
  // Fixture Operations
  // ===========================================================================

  /**
   * Read a fixture file from e2e/fixtures directory.
   * Useful for loading Rediaccfile, docker-compose.yaml, etc.
   */
  readFixture(relativePath: string): string {
    const fixturesPath = path.join(__dirname, "../../..", "fixtures");
    return fs.readFileSync(path.join(fixturesPath, relativePath), "utf-8");
  }

  // ===========================================================================
  // SQL Helper Functions (for PostgreSQL fork tests)
  // ===========================================================================

  /**
   * Execute SQL on a PostgreSQL container using the network-isolated Docker socket.
   * Uses base64 encoding to safely pass SQL through multiple SSH hops.
   * @param containerName The container name (e.g., 'postgres-test-123')
   * @param sql SQL statement to execute
   * @param networkId Network ID for the docker socket
   * @returns Query result as string (trimmed output)
   */
  async executeSql(containerName: string, sql: string, networkId: string): Promise<string> {
    // Use base64 encoding to safely pass SQL through multiple SSH hops
    const base64Sql = Buffer.from(sql).toString("base64");
    const result = await this.executeViaBridge(
      `echo "${base64Sql}" | base64 -d | sudo docker -H unix:///var/run/rediacc/docker-${networkId}.sock exec -i ${containerName} psql -U postgres -d testdb -t`,
    );
    return result.stdout.trim();
  }

  /**
   * Insert a test record into the users table.
   * @param containerName PostgreSQL container name
   * @param username Unique username for the record
   * @param origin Repository origin identifier (e.g., 'parent-only', 'fork-only')
   * @param networkId Network ID for the docker socket
   */
  async insertUserRecord(
    containerName: string,
    username: string,
    origin: string,
    networkId: string,
  ): Promise<void> {
    await this.executeSql(
      containerName,
      `INSERT INTO users (username, email, repo_origin) VALUES ('${username}', '${username}@test.com', '${origin}')`,
      networkId,
    );
  }

  /**
   * Check if a record with the given origin exists in users table.
   * @returns true if at least one record exists with this origin
   */
  async recordExistsByOrigin(
    containerName: string,
    origin: string,
    networkId: string,
  ): Promise<boolean> {
    const count = await this.executeSql(
      containerName,
      `SELECT COUNT(*) FROM users WHERE repo_origin = '${origin}'`,
      networkId,
    );
    return parseInt(count.trim()) > 0;
  }

  /**
   * Get total record count in users table.
   */
  async getUserRecordCount(containerName: string, networkId: string): Promise<number> {
    const count = await this.executeSql(containerName, "SELECT COUNT(*) FROM users", networkId);
    return parseInt(count.trim());
  }

  /**
   * Get MD5 hash of all users data for integrity verification.
   * Orders by id to ensure consistent hash across queries.
   */
  async getUsersDataHash(containerName: string, networkId: string): Promise<string> {
    const hash = await this.executeSql(
      containerName,
      `SELECT MD5(string_agg(id::text || username || email || COALESCE(repo_origin, ''), '' ORDER BY id)) FROM users`,
      networkId,
    );
    return hash.trim();
  }

  /**
   * Insert multiple test records for bulk data testing.
   * @param count Number of records to insert
   * @param origin Repository origin identifier
   */
  async insertBulkUserRecords(
    containerName: string,
    count: number,
    origin: string,
    networkId: string,
  ): Promise<void> {
    // Use a single INSERT with multiple VALUES for efficiency
    const values: string[] = [];
    for (let i = 0; i < count; i++) {
      const username = `bulk_user_${origin}_${i}_${Date.now()}`;
      values.push(`('${username}', '${username}@test.com', '${origin}')`);
    }

    // PostgreSQL can handle large inserts, but we'll batch for safety
    const batchSize = 100;
    for (let i = 0; i < values.length; i += batchSize) {
      const batch = values.slice(i, i + batchSize);
      await this.executeSql(
        containerName,
        `INSERT INTO users (username, email, repo_origin) VALUES ${batch.join(", ")}`,
        networkId,
      );
    }
  }

  // ===========================================================================
  // Repository Fork Helper Functions
  // ===========================================================================

  /**
   * Create a fork of a repository by copying its LUKS image file.
   * This uses the renet repository fork command for proper CoW forking.
   *
   * IMPORTANT: Parent repository MUST be unmounted before forking.
   *
   * Repository structure: ${datastorePath}/repositories/${repositoryName}
   * Each repository is a single LUKS-encrypted image file (not a directory).
   *
   * @param parentRepo Name of the parent repository
   * @param tag Fork tag/name (cannot be 'latest')
   * @param datastorePath Path to the datastore
   */
  async createRepositoryFork(
    parentRepo: string,
    tag: string,
    datastorePath: string,
  ): Promise<ExecResult> {
    // Use renet repository fork command for proper CoW forking
    return this.executeViaBridge(
      `sudo renet repository fork --name "${parentRepo}" --tag "${tag}" --datastore "${datastorePath}"`,
    );
  }

  /**
   * Check if a repository exists in the datastore.
   * Repositories are LUKS image files, not directories.
   */
  async repositoryExists(repositoryName: string, datastorePath: string): Promise<boolean> {
    const result = await this.executeViaBridge(
      `test -f "${datastorePath}/repositories/${repositoryName}" && echo "exists" || echo "not_found"`,
    );
    return result.stdout.trim() === "exists";
  }

  /**
   * Wait for PostgreSQL container to be ready to accept connections.
   * Uses an actual query (SELECT 1) to verify database is fully operational,
   * not just pg_isready which only checks if socket accepts connections.
   *
   * @param containerName PostgreSQL container name
   * @param networkId Network ID for the docker socket
   * @param maxAttempts Maximum number of attempts (default: 30)
   * @param intervalMs Interval between attempts in ms (default: 1000)
   * @returns true if PostgreSQL is ready, false if timed out
   */
  async waitForPostgresReady(
    containerName: string,
    networkId: string,
    maxAttempts = 30,
    intervalMs = 1000,
  ): Promise<boolean> {
    for (let i = 0; i < maxAttempts; i++) {
      // Use actual query instead of pg_isready - this verifies the database
      // is fully operational, not just that the socket accepts connections.
      // This avoids race conditions where pg_isready passes but init scripts
      // are still running or the database is restarting.
      const result = await this.executeViaBridge(
        `sudo docker -H unix:///var/run/rediacc/docker-${networkId}.sock exec ${containerName} psql -U postgres -d testdb -c "SELECT 1" -t -q 2>/dev/null`,
      );
      if (result.code === 0) {
        console.log(`[PostgreSQL] Container ${containerName} is ready after ${i + 1} attempts`);
        return true;
      }
      console.log(`[PostgreSQL] Waiting for ${containerName}... (${i + 1}/${maxAttempts})`);
      await new Promise((resolve) => setTimeout(resolve, intervalMs));
    }
    console.log(
      `[PostgreSQL] Container ${containerName} failed to be ready after ${maxAttempts} attempts`,
    );
    return false;
  }

  // ===========================================================================
  // Vault-Based Testing (for complete parameter testing)
  // ===========================================================================

  /**
   * Test a function with a full vault configuration.
   * Uses --vault-file flag for complete parameter testing.
   *
   * This enables testing ALL backup_push/pull parameters that aren't
   * available as CLI flags in test mode. The vault simulates what
   * middleware would construct for queue items.
   *
   * @param functionName Bridge function to test
   * @param vault VaultBuilder instance with complete configuration
   * @param timeout Optional timeout in milliseconds
   */
  async testFunctionWithVault(
    functionName: string,
    vault: VaultBuilder,
    timeout?: number,
  ): Promise<ExecResult> {
    // Write vault to temp file on TARGET VM (where renet runs)
    const vaultPath = `/tmp/e2e-vault-${Date.now()}.json`;
    const vaultJSON = vault.toJSON();

    // Use base64 encoding to avoid complex escaping through nested SSH
    // This is the safest way to pass arbitrary JSON through multiple shell layers
    const base64JSON = Buffer.from(vaultJSON).toString("base64");
    const uploadCmd = `echo ${base64JSON} | base64 -d > ${vaultPath}`;
    const uploadResult = await this.executeViaBridge(uploadCmd, timeout);

    if (uploadResult.code !== 0) {
      return uploadResult;
    }

    try {
      // Execute function with vault file on target VM
      const cmd = `renet bridge once --test-mode --debug --function ${functionName} --vault-file ${vaultPath}`;
      return await this.executeViaBridge(cmd, timeout);
    } finally {
      // Cleanup vault file on target VM
      await this.executeViaBridge(`rm -f ${vaultPath}`);
    }
  }

  /**
   * Push repository with full vault configuration.
   * Enables testing ALL backup_push parameters including:
   * - destinationType (machine/storage)
   * - machines array (parallel deployment)
   * - storages array (parallel backup)
   * - tag, state, checkpoint, override, grand
   */
  async pushWithVault(vault: VaultBuilder, timeout?: number): Promise<ExecResult> {
    return this.testFunctionWithVault("backup_push", vault, timeout);
  }

  /**
   * Pull repository with full vault configuration.
   * Enables testing ALL backup_pull parameters including:
   * - sourceType (machine/storage)
   * - from (source selection)
   * - grand (CoW pre-seeding)
   */
  async pullWithVault(vault: VaultBuilder, timeout?: number): Promise<ExecResult> {
    return this.testFunctionWithVault("backup_pull", vault, timeout);
  }

  /**
   * Execute any function with vault configuration.
   * For testing functions beyond push/pull that need full vault context.
   */
  async executeWithVault(
    functionName: string,
    vault: VaultBuilder,
    timeout?: number,
  ): Promise<ExecResult> {
    return this.testFunctionWithVault(functionName, vault, timeout);
  }
}
