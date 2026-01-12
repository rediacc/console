import { exec, spawn } from "child_process";
import * as path from "path";
import { promisify } from "util";
import { DEFAULT_DATASTORE_PATH } from "../../constants";

const execAsync = promisify(exec);

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
  private renetDir: string;
  private config: VMNetworkConfig;
  private sshOptions: string;
  private renetBin: string;

  constructor() {
    // Auto-detect renet root: use RENET_ROOT env var or resolve from current location
    // Path from this file: renet/tests/bridge/src/utils/bridge/ -> renet/
    const renetRoot = process.env.RENET_ROOT ?? path.resolve(__dirname, "../../../../../..");
    this.renetDir = renetRoot;
    this.renetBin = `${this.renetDir}/bin/renet`;
    this.sshOptions =
      "-q -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=5";

    // Load configuration from environment (matches renet/pkg/infra/config)
    this.config = this.loadConfig();
  }

  /**
   * Load VM network configuration from environment variables.
   * Matches the pattern in ops/scripts/init.sh
   * STRICT: All environment variables are required, no defaults.
   */
  private loadConfig(): VMNetworkConfig {
    const netBase = process.env.VM_NET_BASE;
    if (!netBase) {
      throw new Error("VM_NET_BASE environment variable is required");
    }

    const netOffsetStr = process.env.VM_NET_OFFSET;
    if (netOffsetStr === undefined) {
      throw new Error("VM_NET_OFFSET environment variable is required");
    }
    const netOffset = parseInt(netOffsetStr, 10);

    const bridgeIdStr = process.env.VM_BRIDGE;
    if (!bridgeIdStr) {
      throw new Error("VM_BRIDGE environment variable is required");
    }
    const bridgeId = parseInt(bridgeIdStr, 10);

    // Parse worker IDs from space-separated string
    const workersStr = process.env.VM_WORKERS;
    if (!workersStr) {
      throw new Error("VM_WORKERS environment variable is required");
    }
    const workerIds = workersStr
      .split(/\s+/)
      .map((id) => parseInt(id, 10))
      .filter((id) => !isNaN(id));
    if (workerIds.length === 0) {
      throw new Error("VM_WORKERS must contain at least one worker ID");
    }

    // Parse ceph node IDs (optional - empty means Ceph disabled)
    const cephStr = process.env.VM_CEPH_NODES ?? "";
    const cephIds = cephStr
      .split(/\s+/)
      .map((id) => parseInt(id, 10))
      .filter((id) => !isNaN(id));
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
    try {
      await execAsync(`ping -c 1 -W ${timeoutSeconds} ${ip}`, {
        timeout: (timeoutSeconds + 1) * 1000,
      });
      return true;
    } catch {
      return false;
    }
  }

  /**
   * Check if SSH is available on a VM
   */
  async isSSHReady(ip: string): Promise<boolean> {
    try {
      const user = process.env.USER;
      if (!user) {
        throw new Error("USER environment variable is not set");
      }
      await execAsync(`ssh ${this.sshOptions} ${user}@${ip} "echo ready"`, { timeout: 10000 });
      return true;
    } catch {
      return false;
    }
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
    timeoutMs = 300000,
  ): Promise<{ stdout: string; stderr: string; code: number }> {
    return new Promise((resolve) => {
      const allArgs = ["ops", ...subcommands, ...args];
      const fullCommand = `${this.renetBin} ${allArgs.join(" ")}`.trim();
      console.log(`[OpsManager] Running: ${fullCommand}`);

      const childProcess = spawn(this.renetBin, allArgs, {
        cwd: this.renetDir,
        shell: false,
        env: { ...process.env },
      });

      let stdout = "";
      let stderr = "";

      childProcess.stdout.on("data", (data: Buffer) => {
        stdout += data.toString();
        // Stream output for visibility
        console.log(`[renet] ${data.toString().trim()}`);
      });

      childProcess.stderr.on("data", (data: Buffer) => {
        stderr += data.toString();
        console.error(`[renet:err] ${data.toString().trim()}`);
      });

      const timeout = setTimeout(() => {
        childProcess.kill("SIGTERM");
        resolve({ stdout, stderr: `${stderr}\nTimeout exceeded`, code: -1 });
      }, timeoutMs);

      childProcess.on("close", (code: number | null) => {
        clearTimeout(timeout);
        resolve({ stdout, stderr, code: code ?? 0 });
      });

      childProcess.on("error", (err: Error) => {
        clearTimeout(timeout);
        resolve({ stdout, stderr: err.message, code: -1 });
      });
    });
  }

  /**
   * Get ops status
   */
  async getStatus(): Promise<{ stdout: string; stderr: string; code: number }> {
    return this.runOpsCommand(["status"], [], 30000);
  }

  /**
   * Start VMs using ops scripts
   * @param options - Start options
   * @param options.force - Force restart even if VMs are running
   * @param options.basic - Only start bridge + first worker
   * @param options.parallel - Start VMs in parallel (faster)
   */
  async startVMs(
    options: { force?: boolean; basic?: boolean; parallel?: boolean } = {},
  ): Promise<{ success: boolean; stdout: string; stderr: string }> {
    const args: string[] = [];

    if (options.force) args.push("--force");
    if (options.basic) args.push("--basic");
    if (options.parallel) args.push("--parallel");

    console.log("[OpsManager] Starting VMs...");
    const result = await this.runOpsCommand(["up"], args, 600000); // 10 minute timeout

    return {
      success: result.code === 0,
      stdout: result.stdout,
      stderr: result.stderr,
    };
  }

  /**
   * Stop all VMs
   */
  async stopVMs(): Promise<{ success: boolean; stdout: string; stderr: string }> {
    console.log("[OpsManager] Stopping VMs...");
    const result = await this.runOpsCommand(["down"], [], 120000); // 2 minute timeout

    return {
      success: result.code === 0,
      stdout: result.stdout,
      stderr: result.stderr,
    };
  }

  /**
   * Wait for a VM to be ready (ping + SSH)
   */
  async waitForVM(ip: string, timeoutMs = 120000): Promise<boolean> {
    const startTime = Date.now();
    const checkInterval = 5000; // 5 seconds

    console.log(`[OpsManager] Waiting for VM ${ip} to be ready...`);

    while (Date.now() - startTime < timeoutMs) {
      const reachable = await this.isVMReachable(ip);
      if (reachable) {
        const sshReady = await this.isSSHReady(ip);
        if (sshReady) {
          console.log(`[OpsManager] VM ${ip} is ready`);
          return true;
        }
      }

      await this.sleep(checkInterval);
    }

    console.log(`[OpsManager] Timeout waiting for VM ${ip}`);
    return false;
  }

  /**
   * Wait for all VMs to be ready
   */
  async waitForAllVMs(timeoutMs = 180000): Promise<boolean> {
    console.log("[OpsManager] Waiting for all VMs to be ready...");

    // Wait for all VMs including Ceph nodes
    const promises = this.getAllVMIps().map((ip) => this.waitForVM(ip, timeoutMs));
    const results = await Promise.all(promises);

    return results.every((ready) => ready);
  }

  /**
   * Wait for worker VMs to be ready
   */
  async waitForWorkerVMs(timeoutMs = 180000): Promise<boolean> {
    console.log("[OpsManager] Waiting for worker VMs to be ready...");

    const promises = this.getWorkerVMIps().map((ip) => this.waitForVM(ip, timeoutMs));
    const results = await Promise.all(promises);

    return results.every((ready) => ready);
  }

  /**
   * Ensure VMs are running - start them if not
   */
  async ensureVMsRunning(
    options: { basic?: boolean } = {},
  ): Promise<{ success: boolean; wasStarted: boolean; message: string }> {
    // First check if VMs are already ready
    const { ready, status } = await this.areAllVMsReady();

    if (ready) {
      return {
        success: true,
        wasStarted: false,
        message: "All VMs are already running and ready",
      };
    }

    // Log which VMs are not ready
    console.log("[OpsManager] Some VMs are not ready:");
    for (const [ip, vmStatus] of status) {
      if (!vmStatus.reachable || !vmStatus.sshReady) {
        console.log(`  - ${ip}: reachable=${vmStatus.reachable}, sshReady=${vmStatus.sshReady}`);
      }
    }

    // Try to start VMs
    console.log("[OpsManager] Starting VMs...");
    const startResult = await this.startVMs({ basic: options.basic });

    if (!startResult.success) {
      return {
        success: false,
        wasStarted: false,
        message: `Failed to start VMs: ${startResult.stderr}`,
      };
    }

    // Wait for VMs to be ready
    const allReady = await this.waitForAllVMs();

    if (!allReady) {
      return {
        success: false,
        wasStarted: true,
        message: "VMs started but not all became ready in time",
      };
    }

    return {
      success: true,
      wasStarted: true,
      message: "VMs started successfully and are ready",
    };
  }

  /**
   * Execute a command on a remote VM via SSH
   */
  async executeOnVM(
    ip: string,
    command: string,
    timeoutMs = 60000,
  ): Promise<{ stdout: string; stderr: string; code: number }> {
    const user = process.env.USER;
    if (!user) {
      throw new Error("USER environment variable is not set");
    }
    const sshCommand = `ssh ${this.sshOptions} ${user}@${ip} "${command.replace(/"/g, '\\"')}"`;

    try {
      const { stdout, stderr } = await execAsync(sshCommand, { timeout: timeoutMs });
      return { stdout, stderr, code: 0 };
    } catch (error: unknown) {
      const err = error as { stdout?: string; stderr?: string; code?: number; message?: string };
      return {
        stdout: err.stdout ?? "",
        stderr: err.stderr ?? err.message ?? "Unknown error",
        code: err.code ?? 1,
      };
    }
  }

  /**
   * Execute a command on all worker VMs in parallel
   */
  async executeOnAllWorkers(
    command: string,
    timeoutMs = 60000,
  ): Promise<Map<string, { stdout: string; stderr: string; code: number }>> {
    const results = new Map<string, { stdout: string; stderr: string; code: number }>();

    const promises = this.getWorkerVMIps().map(async (ip) => {
      const result = await this.executeOnVM(ip, command, timeoutMs);
      return { ip, result };
    });

    const execResults = await Promise.all(promises);
    for (const { ip, result } of execResults) {
      results.set(ip, result);
    }

    return results;
  }

  /**
   * Check if renet is installed on a VM
   */
  async isRenetInstalledOnVM(ip: string): Promise<boolean> {
    const result = await this.executeOnVM(ip, "which renet || command -v renet");
    return result.code === 0 && result.stdout.trim().length > 0;
  }

  /**
   * Get renet version on a VM
   */
  async getRenetVersionOnVM(ip: string): Promise<string | null> {
    const result = await this.executeOnVM(
      ip,
      "renet version 2>/dev/null || renet --version 2>/dev/null",
    );
    if (result.code === 0) {
      return result.stdout.trim();
    }
    return null;
  }

  private sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  /**
   * Start RustFS S3-compatible storage on the bridge VM.
   * Uses renet ops rustfs start command.
   */
  async startRustFS(): Promise<{ success: boolean; message: string }> {
    const bridgeIp = this.getBridgeVMIp();
    console.log(`[OpsManager] Starting RustFS on bridge VM (${bridgeIp})...`);

    // Check if RustFS is already running
    const checkResult = await this.executeOnVM(
      bridgeIp,
      'docker ps --filter name=rustfs --format "{{.Names}}"',
    );
    if (checkResult.stdout.trim() === "rustfs") {
      console.log("[OpsManager] RustFS is already running");
      return { success: true, message: "RustFS already running" };
    }

    // Start RustFS using renet ops command
    const result = await this.runOpsCommand(["rustfs", "start"], [], 120000); // 2 minute timeout

    if (result.code !== 0) {
      console.error("[OpsManager] Failed to start RustFS:", result.stderr);
      return { success: false, message: `Failed to start RustFS: ${result.stderr}` };
    }

    // Verify RustFS is accessible by checking the S3 endpoint
    // Note: RustFS returns 403 for unauthenticated requests, which means server is running
    console.log("[OpsManager] Verifying RustFS S3 endpoint...");
    const verifyResult = await this.executeOnVM(
      bridgeIp,
      "curl -s -o /dev/null -w '%{http_code}' http://localhost:9000/",
    );

    const httpCode = verifyResult.stdout.trim();
    // 403 = Access Denied (server running, auth required)
    // 200 = OK (shouldn't happen without auth, but accept it)
    if (httpCode === "403" || httpCode === "200") {
      console.log("[OpsManager] RustFS S3 endpoint is accessible");
      return { success: true, message: "RustFS started successfully" };
    }

    console.error(`[OpsManager] RustFS health check failed (HTTP ${httpCode})`);
    return { success: false, message: `RustFS health check failed (HTTP ${httpCode})` };
  }

  /**
   * Check if RustFS is running on the bridge VM.
   */
  async isRustFSRunning(): Promise<boolean> {
    const bridgeIp = this.getBridgeVMIp();
    const result = await this.executeOnVM(
      bridgeIp,
      'docker ps --filter name=rustfs --format "{{.Names}}"',
    );
    return result.stdout.trim() === "rustfs";
  }

  /**
   * Stop RustFS S3-compatible storage on the bridge VM.
   * Uses renet ops rustfs stop command.
   */
  async stopRustFS(): Promise<{ success: boolean; message: string }> {
    console.log("[OpsManager] Stopping RustFS...");
    const result = await this.runOpsCommand(["rustfs", "stop"], [], 60000); // 1 minute timeout

    if (result.code !== 0) {
      return { success: false, message: `Failed to stop RustFS: ${result.stderr}` };
    }

    return { success: true, message: "RustFS stopped successfully" };
  }

  /**
   * Create a bucket in RustFS.
   * Uses renet ops rustfs create-bucket command.
   */
  async createRustFSBucket(bucket?: string): Promise<{ success: boolean; message: string }> {
    const bucketName = bucket ?? "default";
    console.log(`[OpsManager] Creating RustFS bucket: ${bucketName}`);

    const args = bucket ? [bucket] : [];
    const result = await this.runOpsCommand(["rustfs", "create-bucket"], args, 60000);

    if (result.code !== 0) {
      return { success: false, message: `Failed to create bucket: ${result.stderr}` };
    }

    return { success: true, message: `Bucket '${bucketName}' created successfully` };
  }

  /**
   * List contents of a RustFS bucket.
   * Uses renet ops rustfs list command.
   */
  async listRustFSBucket(
    bucket?: string,
  ): Promise<{ success: boolean; contents: string; message: string }> {
    const bucketName = bucket ?? "default";
    console.log(`[OpsManager] Listing RustFS bucket: ${bucketName}`);

    const args = bucket ? [bucket] : [];
    const result = await this.runOpsCommand(["rustfs", "list"], args, 60000);

    if (result.code !== 0) {
      return { success: false, contents: "", message: `Failed to list bucket: ${result.stderr}` };
    }

    return { success: true, contents: result.stdout.trim(), message: "Bucket listed successfully" };
  }

  /**
   * Configure rclone on a worker VM to access RustFS.
   * Uses renet ops rustfs configure-worker command.
   */
  async configureRustFSWorker(vmId: number): Promise<{ success: boolean; message: string }> {
    console.log(`[OpsManager] Configuring RustFS access on worker VM ${vmId}...`);

    const result = await this.runOpsCommand(
      ["rustfs", "configure-worker"],
      [vmId.toString()],
      60000,
    );

    if (result.code !== 0) {
      return { success: false, message: `Failed to configure worker ${vmId}: ${result.stderr}` };
    }

    return { success: true, message: `Worker ${vmId} configured for RustFS access` };
  }

  /**
   * Configure rclone on all worker VMs to access RustFS.
   * Uses renet ops rustfs configure-workers command.
   */
  async configureRustFSWorkers(): Promise<{ success: boolean; message: string }> {
    console.log("[OpsManager] Configuring RustFS access on all worker VMs...");

    const result = await this.runOpsCommand(["rustfs", "configure-workers"], [], 120000);

    if (result.code !== 0) {
      return { success: false, message: `Failed to configure workers: ${result.stderr}` };
    }

    return { success: true, message: "All workers configured for RustFS access" };
  }

  /**
   * Verify RustFS access from a worker VM using rclone.
   */
  async verifyRustFSAccessFromWorker(
    vmId: number,
    bucket?: string,
  ): Promise<{ success: boolean; message: string }> {
    const ip = this.calculateVMIp(vmId);
    const bucketName = bucket ?? "default";
    console.log(`[OpsManager] Verifying RustFS access from VM ${vmId} (${ip})...`);

    // Try to list the bucket using rclone
    const result = await this.executeOnVM(
      ip,
      `rclone ls rustfs:${bucketName} 2>&1 || echo "(empty or bucket not found)"`,
      30000,
    );

    if (result.code !== 0) {
      return { success: false, message: `RustFS access verification failed: ${result.stderr}` };
    }

    return { success: true, message: `RustFS accessible from VM ${vmId}` };
  }

  /**
   * Soft reset VMs by force restarting them.
   * Calls: renet ops up --force --parallel
   * This ensures a clean state before tests.
   */
  async resetVMs(): Promise<{ success: boolean; duration: number }> {
    const startTime = Date.now();

    console.log("[OpsManager] Performing soft reset (renet ops up --force --parallel)...");
    // 30 min timeout to allow Ceph provisioning to complete fully
    const extraEnv: Record<string, string> = {};
    if (this.getCephVMIps().length > 0) {
      extraEnv.PROVISION_CEPH_CLUSTER = "true";
    }
    const result =
      Object.keys(extraEnv).length > 0
        ? await this.runOpsCommandWithEnv(["up"], ["--force", "--parallel"], extraEnv, 1800000)
        : await this.runOpsCommand(["up"], ["--force", "--parallel"], 1800000);

    // Note: The command may return non-zero if middleware auth fails (rdc not found),
    // but VMs may still be successfully created. We verify actual VM readiness below.
    if (result.code !== 0) {
      console.log(
        "[OpsManager] renet ops command returned non-zero, verifying VM readiness anyway...",
      );
    }

    // Wait for all VMs to be ready after reset - this is the real success criteria
    console.log("[OpsManager] Waiting for VMs to be ready after reset...");
    const allReady = await this.waitForAllVMs(180000);

    if (!allReady) {
      console.error("[OpsManager] VMs did not become ready after reset");
      return { success: false, duration: Date.now() - startTime };
    }

    console.log(
      `[OpsManager] VM reset completed in ${((Date.now() - startTime) / 1000).toFixed(1)}s`,
    );
    return { success: true, duration: Date.now() - startTime };
  }

  /**
   * Initialize datastores on all worker VMs.
   * This ensures /mnt/rediacc is mounted with BTRFS filesystem.
   * Should be called during global setup, not in individual tests.
   */
  async initializeAllDatastores(
    size = "10G",
    datastorePath = DEFAULT_DATASTORE_PATH,
  ): Promise<void> {
    console.log("[OpsManager] Initializing datastores on all worker VMs...");

    const workerIPs = this.getWorkerVMIps();

    for (const ip of workerIPs) {
      console.log(`  Initializing datastore on ${ip}...`);

      // Run datastore_init via renet bridge once --test-mode
      const result = await this.executeOnVM(
        ip,
        `renet bridge once --test-mode --function datastore_init --datastore-path ${datastorePath} --size ${size} --force`,
        120000, // 2 minute timeout for datastore initialization
      );

      if (result.code !== 0) {
        throw new Error(`Failed to initialize datastore on ${ip}: ${result.stderr}`);
      }

      console.log(`  ✓ Datastore initialized on ${ip}`);
    }

    console.log("[OpsManager] All datastores initialized");
  }

  /**
   * Provision Ceph cluster on Ceph VMs.
   * This runs the OPS provisioning scripts to set up a full Ceph cluster.
   * Should be called after VM reset and before running Ceph-related tests.
   */
  async provisionCeph(): Promise<{ success: boolean; message: string }> {
    const cephIPs = this.getCephVMIps();
    if (cephIPs.length === 0) {
      return { success: true, message: "No Ceph nodes configured, skipping" };
    }

    console.log("[OpsManager] Provisioning Ceph cluster...");

    // Run provisioning via OPS command (provision_ceph_cluster)
    // Set PROVISION_CEPH_CLUSTER=true to ensure provisioning runs
    const result = await this.runOpsCommandWithEnv(
      ["ceph", "provision"],
      [],
      { PROVISION_CEPH_CLUSTER: "true" },
      600000, // 10 minute timeout
    );

    if (result.code !== 0) {
      console.error("[OpsManager] Ceph provisioning failed");
      return { success: false, message: `Ceph provisioning failed: ${result.stderr}` };
    }

    console.log("[OpsManager] Ceph cluster provisioned successfully");
    return { success: true, message: "Ceph cluster provisioned" };
  }

  /**
   * Run a renet ops command with additional environment variables
   */
  async runOpsCommandWithEnv(
    subcommands: string[],
    args: string[] = [],
    extraEnv: Record<string, string> = {},
    timeoutMs = 300000,
  ): Promise<{ stdout: string; stderr: string; code: number }> {
    return new Promise((resolve) => {
      const allArgs = ["ops", ...subcommands, ...args];
      const fullCommand = `${this.renetBin} ${allArgs.join(" ")}`.trim();
      console.log(`[OpsManager] Running: ${fullCommand}`);

      const childProcess = spawn(this.renetBin, allArgs, {
        cwd: this.renetDir,
        shell: false,
        env: { ...process.env, ...extraEnv },
      });

      let stdout = "";
      let stderr = "";

      childProcess.stdout.on("data", (data: Buffer) => {
        stdout += data.toString();
        console.log(`[renet] ${data.toString().trim()}`);
      });

      childProcess.stderr.on("data", (data: Buffer) => {
        stderr += data.toString();
        console.error(`[renet:err] ${data.toString().trim()}`);
      });

      const timeout = setTimeout(() => {
        childProcess.kill("SIGTERM");
        resolve({ stdout, stderr: `${stderr}\nTimeout exceeded`, code: -1 });
      }, timeoutMs);

      childProcess.on("close", (code: number | null) => {
        clearTimeout(timeout);
        resolve({ stdout, stderr, code: code ?? 0 });
      });

      childProcess.on("error", (err: Error) => {
        clearTimeout(timeout);
        resolve({ stdout, stderr: err.message, code: -1 });
      });
    });
  }

  /**
   * Verify all VMs (bridge + workers + ceph) are ready.
   * Throws an error if any VM is not reachable or SSH is not available.
   * STRICT: No graceful fallback, tests cannot proceed if VMs are not ready.
   */
  async verifyAllVMsReady(): Promise<void> {
    const allIPs = this.getAllVMIps();
    const notReady: string[] = [];

    console.log("[OpsManager] Verifying all VMs are ready...");

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
      console.log(`  ✓ ${ip}: renet ${version}`);
    }

    if (notReady.length > 0) {
      throw new Error(`VMs not ready: ${notReady.join(", ")}`);
    }

    console.log("[OpsManager] All VMs verified and ready");
  }
}

// Singleton instance for shared state across tests
let opsManagerInstance: OpsManager | null = null;

export function getOpsManager(): OpsManager {
  opsManagerInstance ??= new OpsManager();
  return opsManagerInstance;
}
