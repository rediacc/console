/* eslint-disable max-lines */
// BridgeTestRunner contains extensive delegation methods for backward compatibility.
// The actual implementations are in separate module files (methods/*.ts, helpers/*.ts).
import { exec } from 'node:child_process';
import { promisify } from 'node:util';
import { DEFAULT_NETWORK_ID } from '../../constants';
import { RepositoryHelpers } from './helpers/RepositoryHelpers';
import { SqlHelpers } from './helpers/SqlHelpers';
import { TestHelpers } from './helpers/TestHelpers';
import { BackupMethods } from './methods/BackupMethods';
import { CephMethods } from './methods/CephMethods';
import { ContainerMethods } from './methods/ContainerMethods';
import { DaemonMethods } from './methods/DaemonMethods';
import { DatastoreMethods } from './methods/DatastoreMethods';
import { RepositoryMethods } from './methods/RepositoryMethods';
import { SetupMethods } from './methods/SetupMethods';
import { SystemCheckMethods } from './methods/SystemCheckMethods';
import { getOpsManager, OpsManager } from './OpsManager';
import type { ExecResult, RunnerConfig, TestFunctionOptions, VMTarget } from './types';
import type { VaultBuilder } from '../vault/VaultBuilder';

const execAsync = promisify(exec);
const DEFAULT_DATASTORE_PATH = '/mnt/rediacc';

// Re-export types for backwards compatibility
export type { ExecResult, RunnerConfig, TestFunctionOptions, VMTarget };

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
  private readonly defaultTimeout: number;
  private readonly opsManager: OpsManager;
  private readonly bridgeVM: string;
  private readonly targetVM: string;

  // Method groups
  private readonly systemCheckMethods: SystemCheckMethods;
  private readonly setupMethods: SetupMethods;
  private readonly datastoreMethods: DatastoreMethods;
  private readonly repositoryMethods: RepositoryMethods;
  private readonly cephMethods: CephMethods;
  private readonly containerMethods: ContainerMethods;
  private readonly daemonMethods: DaemonMethods;
  private readonly backupMethods: BackupMethods;

  // Helper utilities
  private readonly testHelpers: TestHelpers;
  private readonly repositoryHelpers: RepositoryHelpers;
  private readonly sqlHelpers: SqlHelpers;

  constructor(config: RunnerConfig) {
    if (!config.targetVM) {
      throw new Error('targetVM is required - no default execution target');
    }

    this.opsManager = getOpsManager();
    this.bridgeVM = this.opsManager.getBridgeVMIp();
    this.targetVM = this.resolveTargetVM(config.targetVM);

    const timeoutStr = process.env.BRIDGE_TIMEOUT;
    if (!timeoutStr) {
      throw new Error('BRIDGE_TIMEOUT environment variable is required');
    }
    this.defaultTimeout = Number.parseInt(timeoutStr, 10);

    // Initialize method groups
    this.systemCheckMethods = new SystemCheckMethods(this.testFunction.bind(this));
    this.setupMethods = new SetupMethods(this.testFunction.bind(this));
    this.datastoreMethods = new DatastoreMethods(this.testFunction.bind(this));
    this.repositoryMethods = new RepositoryMethods(this.testFunction.bind(this));
    this.cephMethods = new CephMethods(this.testFunction.bind(this));
    this.containerMethods = new ContainerMethods(this.testFunction.bind(this));
    this.daemonMethods = new DaemonMethods(this.testFunction.bind(this));
    this.backupMethods = new BackupMethods(
      this.testFunction.bind(this),
      this.testFunctionWithVault.bind(this)
    );

    // Initialize helpers
    this.testHelpers = new TestHelpers();
    this.repositoryHelpers = new RepositoryHelpers(this.executeViaBridge.bind(this));
    this.sqlHelpers = new SqlHelpers(this.executeViaBridge.bind(this));
  }

  /**
   * Resolve VM target name to IP address.
   */
  private resolveTargetVM(target: VMTarget): string {
    switch (target) {
      case 'worker1':
        return this.opsManager.getWorkerVMIps()[0];
      case 'worker2':
        return this.opsManager.getWorkerVMIps()[1];
      case 'ceph1':
        return this.opsManager.getCephVMIps()[0];
      case 'ceph2':
        return this.opsManager.getCephVMIps()[1];
      case 'ceph3':
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

  // ===========================================================================
  // VM Information & Management
  // ===========================================================================

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
   * Get all Ceph VM IPs.
   */
  getCephVMs(): string[] {
    return this.opsManager.getCephVMIps();
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
    options: { basic?: boolean } = {}
  ): Promise<{ success: boolean; message: string }> {
    return this.opsManager.ensureVMsRunning(options);
  }

  // ===========================================================================
  // Command Execution
  // ===========================================================================

  /**
   * Escape command for nested SSH execution.
   */
  private escapeForNestedSSH(command: string): string {
    // First escape for the inner SSH (target), then for outer SSH (bridge)
    const escapedForTarget = command.replaceAll('\\', '\\\\').replaceAll('"', '\\"');
    return escapedForTarget.replaceAll('\\', '\\\\').replaceAll('"', '\\"');
  }

  /**
   * Log command execution outputs for Playwright capture.
   */
  private logExecutionResult(stdout: string, stderr: string, code: number): void {
    if (stdout.trim()) {
      // eslint-disable-next-line no-console
      console.log(`[STDOUT]\n${stdout}`);
    }
    if (stderr.trim()) {
      // eslint-disable-next-line no-console
      console.log(`[STDERR]\n${stderr}`);
    }
    // eslint-disable-next-line no-console
    console.log(`[EXIT] ${code}`);
  }

  /**
   * Execute a command on target VM via Bridge VM (two-hop SSH).
   * Pattern: Host → SSH → Bridge → SSH → Target → command
   * Outputs are logged to console so Playwright can capture them.
   */
  async executeViaBridge(command: string, timeout?: number): Promise<ExecResult> {
    const cmdTimeout = timeout ?? this.defaultTimeout;
    const escapedForBridge = this.escapeForNestedSSH(command);

    // Two-hop SSH command: Host → Bridge → Target
    const sshCmd = `ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=10 ${this.bridgeVM} "ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=10 ${this.targetVM} \\"${escapedForBridge}\\""`;

    // Log the command being executed
    // eslint-disable-next-line no-console
    console.log(`\n[SSH ${this.bridgeVM} → ${this.targetVM}] ${command}`);

    const fallbackDirect = async (reason: string): Promise<ExecResult> => {
      // eslint-disable-next-line no-console
      console.log(`[BridgeTestRunner] Falling back to direct SSH to ${this.targetVM}: ${reason}`);
      return this.executeOnVM(this.targetVM, command, timeout);
    };

    try {
      const { stdout, stderr } = await execAsync(sshCmd, { timeout: cmdTimeout });
      this.logExecutionResult(stdout, stderr, 0);
      return { stdout, stderr, code: 0 };
    } catch (error: unknown) {
      const err = error as Error & {
        stdout?: string;
        stderr?: string;
        code?: number;
        killed?: boolean;
      };
      const stdout = err.stdout ?? '';
      const stderrPrefix = err.killed ? `Command timed out after ${cmdTimeout}ms\n` : '';
      const stderr = stderrPrefix + (err.stderr ?? '');
      const code = err.killed ? 124 : (err.code ?? 1);

      this.logExecutionResult(stdout, stderr, code);

      if (/renet: command not found|No such file or directory/.test(stderr)) {
        return fallbackDirect('renet not found on target via bridge');
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
    const sshCmd = `ssh -o ConnectTimeout=10 -o BatchMode=yes -o StrictHostKeyChecking=no ${host} "${command.replaceAll('"', '\\"')}"`;

    // Log the command being executed
    // eslint-disable-next-line no-console
    console.log(`\n[SSH ${host}] ${command}`);

    try {
      const { stdout, stderr } = await execAsync(sshCmd, { timeout: cmdTimeout });
      this.logExecutionResult(stdout, stderr, 0);
      return { stdout, stderr, code: 0 };
    } catch (error: unknown) {
      const err = error as Error & {
        stdout?: string;
        stderr?: string;
        code?: number;
        killed?: boolean;
      };
      const stdout = err.stdout ?? '';
      const stderrPrefix = err.killed ? `Command timed out after ${cmdTimeout}ms\n` : '';
      const stderr = stderrPrefix + (err.stderr ?? '');
      const code = err.killed ? 124 : (err.code ?? 1);

      this.logExecutionResult(stdout, stderr, code);
      return { stdout, stderr, code };
    }
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
   * Execute a command on the target Ceph VM.
   * Alias for executeViaBridge for clarity in Ceph-specific tests.
   */
  async executeOnCeph(command: string, timeout?: number): Promise<ExecResult> {
    return this.executeViaBridge(command, timeout);
  }

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

  // ===========================================================================
  // Test Function Execution
  // ===========================================================================

  /**
   * Build common renet command flags for test functions.
   */
  private buildCommonFlags(opts: TestFunctionOptions): string {
    let flags = '';

    if (opts.datastorePath) {
      flags += ` --datastore-path ${opts.datastorePath}`;
    }
    if (opts.repository) {
      flags += ` --repository ${opts.repository}`;
    }
    const networkId = opts.networkId ?? DEFAULT_NETWORK_ID;
    if (networkId) {
      flags += ` --network-id ${networkId}`;
    }
    if (opts.password) {
      flags += ` --password '${opts.password}'`;
    }
    if (opts.size) {
      flags += ` --size ${opts.size}`;
    }
    if (opts.newSize) {
      flags += ` --new-size ${opts.newSize}`;
    }

    return flags;
  }

  /**
   * Build Ceph-related command flags.
   */
  private buildCephFlags(opts: TestFunctionOptions): string {
    let flags = '';

    if (opts.pool) {
      flags += ` --pool ${opts.pool}`;
    }
    if (opts.pgNum) {
      flags += ` --pg-num ${opts.pgNum}`;
    }
    if (opts.image) {
      flags += ` --image ${opts.image}`;
    }
    if (opts.snapshot) {
      flags += ` --snapshot ${opts.snapshot}`;
    }
    if (opts.clone) {
      flags += ` --clone ${opts.clone}`;
    }
    if (opts.mountPoint) {
      flags += ` --mount-point ${opts.mountPoint}`;
    }
    if (opts.cowSize) {
      flags += ` --cow-size ${opts.cowSize}`;
    }
    if (opts.keepCow) {
      flags += ` --keep-cow`;
    }

    return flags;
  }

  /**
   * Build container and checkpoint flags.
   */
  private buildContainerFlags(opts: TestFunctionOptions): string {
    let flags = '';

    if (opts.container) {
      flags += ` --container ${opts.container}`;
    }
    if (opts.command) {
      flags += ` --command '${opts.command}'`;
    }
    if (opts.checkpointName) {
      flags += ` --checkpoint-name ${opts.checkpointName}`;
    }
    if (opts.sourceMachine) {
      flags += ` --source-machine ${opts.sourceMachine}`;
    }
    if (opts.destMachine) {
      flags += ` --dest-machine ${opts.destMachine}`;
    }

    return flags;
  }

  /**
   * Build filesystem flags.
   */
  private buildFilesystemFlags(opts: TestFunctionOptions): string {
    let flags = '';

    if (opts.format) {
      flags += ` --format ${opts.format}`;
    }
    if (opts.filesystem) {
      flags += ` --filesystem ${opts.filesystem}`;
    }
    if (opts.label) {
      flags += ` --label ${opts.label}`;
    }
    if (opts.force) {
      flags += ` --force`;
    }
    if (opts.uid) {
      flags += ` --uid ${opts.uid}`;
    }
    if (opts.prepOnly) {
      flags += ` --prep-only`;
    }

    return flags;
  }

  /**
   * Build installation flags.
   */
  private buildInstallationFlags(opts: TestFunctionOptions): string {
    let flags = '';

    if (opts.installSource) {
      flags += ` --install-source ${opts.installSource}`;
    }
    if (opts.rcloneSource) {
      flags += ` --rclone-source ${opts.rcloneSource}`;
    }
    if (opts.dockerSource) {
      flags += ` --docker-source ${opts.dockerSource}`;
    }
    if (opts.installAmdDriver) {
      flags += ` --install-amd-driver ${opts.installAmdDriver}`;
    }
    if (opts.installNvidiaDriver) {
      flags += ` --install-nvidia-driver ${opts.installNvidiaDriver}`;
    }
    if (opts.installCriu) {
      flags += ` --install-criu ${opts.installCriu}`;
    }

    return flags;
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

    cmd += this.buildCommonFlags(opts);
    cmd += this.buildCephFlags(opts);
    cmd += this.buildContainerFlags(opts);
    cmd += this.buildFilesystemFlags(opts);
    cmd += this.buildInstallationFlags(opts);

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
    return this.executeViaBridge('renet version');
  }

  /**
   * Check if renet is available and working on target VM.
   */
  async isRenetAvailable(): Promise<boolean> {
    const result = await this.getRenetVersion();
    return result.code === 0;
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
    timeout?: number
  ): Promise<ExecResult> {
    return this.executeOnVM(host, `renet ${renetCommand}`, timeout);
  }

  /**
   * Check setup status on a specific machine.
   */
  async checkSetupOnMachine(host: string): Promise<ExecResult> {
    // machine_check_system is available through bridge once
    return this.executeOnVM(host, 'renet bridge once --test-mode --function machine_check_system');
  }

  /**
   * Check datastore status on a specific machine.
   */
  async checkDatastoreOnMachine(host: string, datastorePath: string): Promise<ExecResult> {
    // check_datastore may need direct CLI call
    return this.executeOnVM(
      host,
      `renet datastore status --path ${datastorePath} 2>&1 || echo "datastore check completed"`
    );
  }

  /**
   * List repositories on a specific machine.
   */
  async listRepositoriesOnMachine(host: string, datastorePath: string): Promise<ExecResult> {
    return this.executeOnVM(
      host,
      `renet repository list --datastore ${datastorePath} 2>&1 || echo "list completed"`
    );
  }

  // ===========================================================================
  // Vault-Based Testing
  // ===========================================================================

  /**
   * Test a function with a full vault configuration.
   * Uses --vault-file flag for complete parameter testing.
   *
   * This enables testing ALL backup_push/pull parameters that aren't
   * available as CLI flags in test mode. The vault simulates what
   * middleware would construct for queue items.
   */
  private async testFunctionWithVault(
    functionName: string,
    vault: VaultBuilder,
    timeout?: number
  ): Promise<ExecResult> {
    // Write vault to temp file on TARGET VM (where renet runs)
    const vaultPath = `/tmp/e2e-vault-${Date.now()}.json`;
    const vaultJSON = vault.toJSON();

    // Use base64 encoding to avoid complex escaping through nested SSH
    const base64JSON = Buffer.from(vaultJSON).toString('base64');
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
   * Execute any function with vault configuration.
   */
  async executeWithVault(
    functionName: string,
    vault: VaultBuilder,
    timeout?: number
  ): Promise<ExecResult> {
    return this.testFunctionWithVault(functionName, vault, timeout);
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
    // eslint-disable-next-line no-console
    console.log(`\n[Reset] Cleaning worker state at ${datastorePath}...`);

    // 1. Force teardown daemon (stops containers, unmounts repos)
    await this.executeViaBridge(
      `sudo renet daemon teardown --network-id ${DEFAULT_NETWORK_ID} --force 2>/dev/null || true`
    );

    // 2. Kill any processes using the datastore (prevents busy mount)
    await this.executeViaBridge(
      `sudo lsof +D ${datastorePath} 2>/dev/null | awk 'NR>1 {print $2}' | xargs -r sudo kill 2>/dev/null || true`
    );

    // 3. Sync filesystem before unmount
    await this.executeViaBridge('sync');

    // 4. Unmount datastore - try normal first, then lazy unmount as fallback
    await this.executeViaBridge(
      `mountpoint -q ${datastorePath} && (sudo umount ${datastorePath} 2>/dev/null || sudo umount -l ${datastorePath}) || true`
    );

    // 5. Detach any loop devices associated with the backing file
    await this.executeViaBridge(
      `losetup -j ${datastorePath}.img 2>/dev/null | cut -d: -f1 | xargs -r sudo losetup -d 2>/dev/null || true`
    );

    // 6. Remove datastore backing file
    await this.executeViaBridge(`sudo rm -f ${datastorePath}.img`);

    // 7. Clean up any leftover files in datastore directory (including hidden files)
    await this.executeViaBridge(
      `sudo rm -rf ${datastorePath}/* ${datastorePath}/.* 2>/dev/null || true`
    );

    // 8. Remove datastore marker/metadata if any
    await this.executeViaBridge(`sudo rm -f ${datastorePath}/.datastore 2>/dev/null || true`);

    // eslint-disable-next-line no-console
    console.log('[Reset] Worker state cleaned');
  }

  // ===========================================================================
  // Method Group Delegations (for backwards compatibility)
  // ===========================================================================

  // System Check Methods
  ping = () => this.systemCheckMethods.ping();
  nop = () => this.systemCheckMethods.nop();
  hello = () => this.systemCheckMethods.hello();
  sshTest = () => this.systemCheckMethods.sshTest();
  checkKernelCompatibility = () => this.systemCheckMethods.checkKernelCompatibility();
  checkSetup = () => this.systemCheckMethods.checkSetup();
  checkMemory = () => this.systemCheckMethods.checkMemory();
  checkSudo = () => this.systemCheckMethods.checkSudo();
  checkTools = () => this.systemCheckMethods.checkTools();
  checkRenet = () => this.systemCheckMethods.checkRenet();
  checkCriu = () => this.systemCheckMethods.checkCriu();
  checkBtrfs = () => this.systemCheckMethods.checkBtrfs();
  checkDrivers = () => this.systemCheckMethods.checkDrivers();
  checkSystem = () => this.systemCheckMethods.checkSystem();
  checkUsers = () => this.systemCheckMethods.checkUsers();
  checkRediaccCli = () => this.systemCheckMethods.checkRediaccCli();
  checkDatastore = (datastorePath?: string) =>
    this.systemCheckMethods.checkDatastore(datastorePath);

  // Setup Methods
  setup = (datastorePath?: string, uid?: string) => this.setupMethods.setup(datastorePath, uid);
  osSetup = (datastorePath?: string, uid?: string) => this.setupMethods.osSetup(datastorePath, uid);
  setupWithOptions = (options: Parameters<SetupMethods['setupWithOptions']>[0]) =>
    this.setupMethods.setupWithOptions(options);
  fixUserGroups = (uid?: string) => this.setupMethods.fixUserGroups(uid);

  // Datastore Methods
  datastoreInit = (size: string, datastorePath?: string, force?: boolean) =>
    this.datastoreMethods.datastoreInit(size, datastorePath, force);
  datastoreMount = (datastorePath?: string) => this.datastoreMethods.datastoreMount(datastorePath);
  datastoreUnmount = (datastorePath?: string) =>
    this.datastoreMethods.datastoreUnmount(datastorePath);
  datastoreExpand = (newSize: string, datastorePath?: string) =>
    this.datastoreMethods.datastoreExpand(newSize, datastorePath);
  datastoreResize = (newSize: string, datastorePath?: string) =>
    this.datastoreMethods.datastoreResize(newSize, datastorePath);
  datastoreValidate = (datastorePath?: string) =>
    this.datastoreMethods.datastoreValidate(datastorePath);

  // Repository Methods
  repositoryNew = (name: string, size: string, password?: string, datastorePath?: string) =>
    this.repositoryMethods.repositoryNew(name, size, password, datastorePath);
  repositoryRm = (name: string, datastorePath?: string) =>
    this.repositoryMethods.repositoryRm(name, datastorePath);
  repositoryMount = (name: string, password?: string, datastorePath?: string) =>
    this.repositoryMethods.repositoryMount(name, password, datastorePath);
  repositoryUnmount = (name: string, datastorePath?: string) =>
    this.repositoryMethods.repositoryUnmount(name, datastorePath);
  repositoryUp = (name: string, datastorePath?: string, networkId?: string) =>
    this.repositoryMethods.repositoryUp(name, datastorePath, networkId);
  repositoryUpPrepOnly = (name: string, datastorePath?: string, networkId?: string) =>
    this.repositoryMethods.repositoryUpPrepOnly(name, datastorePath, networkId);
  repositoryDown = (name: string, datastorePath?: string, networkId?: string) =>
    this.repositoryMethods.repositoryDown(name, datastorePath, networkId);
  repositoryList = (datastorePath?: string) => this.repositoryMethods.repositoryList(datastorePath);
  repositoryResize = (name: string, newSize: string, password?: string, datastorePath?: string) =>
    this.repositoryMethods.repositoryResize(name, newSize, password, datastorePath);
  repositoryInfo = (name: string, datastorePath?: string) =>
    this.repositoryMethods.repositoryInfo(name, datastorePath);
  repositoryStatus = (name: string, datastorePath?: string) =>
    this.repositoryMethods.repositoryStatus(name, datastorePath);
  repositoryValidate = (name: string, datastorePath?: string) =>
    this.repositoryMethods.repositoryValidate(name, datastorePath);
  repositoryGrow = (name: string, newSize: string, password?: string, datastorePath?: string) =>
    this.repositoryMethods.repositoryGrow(name, newSize, password, datastorePath);

  // Ceph Methods
  cephHealth = () => this.cephMethods.cephHealth();
  cephPoolCreate = (pool: string, pgNum?: string) => this.cephMethods.cephPoolCreate(pool, pgNum);
  cephPoolDelete = (pool: string) => this.cephMethods.cephPoolDelete(pool);
  cephPoolList = () => this.cephMethods.cephPoolList();
  cephPoolInfo = (pool: string) => this.cephMethods.cephPoolInfo(pool);
  cephPoolStats = (pool: string) => this.cephMethods.cephPoolStats(pool);
  cephImageCreate = (pool: string, image: string, size: string) =>
    this.cephMethods.cephImageCreate(pool, image, size);
  cephImageDelete = (pool: string, image: string) => this.cephMethods.cephImageDelete(pool, image);
  cephImageList = (pool: string) => this.cephMethods.cephImageList(pool);
  cephImageInfo = (pool: string, image: string) => this.cephMethods.cephImageInfo(pool, image);
  cephImageResize = (pool: string, image: string, newSize: string) =>
    this.cephMethods.cephImageResize(pool, image, newSize);
  cephImageMap = (pool: string, image: string) => this.cephMethods.cephImageMap(pool, image);
  cephImageUnmap = (pool: string, image: string) => this.cephMethods.cephImageUnmap(pool, image);
  cephImageFormat = (pool: string, image: string, filesystem?: string, label?: string) =>
    this.cephMethods.cephImageFormat(pool, image, filesystem, label);
  cephSnapshotCreate = (pool: string, image: string, snapshot: string) =>
    this.cephMethods.cephSnapshotCreate(pool, image, snapshot);
  cephSnapshotDelete = (pool: string, image: string, snapshot: string) =>
    this.cephMethods.cephSnapshotDelete(pool, image, snapshot);
  cephSnapshotList = (pool: string, image: string) =>
    this.cephMethods.cephSnapshotList(pool, image);
  cephSnapshotProtect = (pool: string, image: string, snapshot: string) =>
    this.cephMethods.cephSnapshotProtect(pool, image, snapshot);
  cephSnapshotUnprotect = (pool: string, image: string, snapshot: string) =>
    this.cephMethods.cephSnapshotUnprotect(pool, image, snapshot);
  cephSnapshotRollback = (pool: string, image: string, snapshot: string) =>
    this.cephMethods.cephSnapshotRollback(pool, image, snapshot);
  cephCloneCreate = (pool: string, image: string, snapshot: string, clone: string) =>
    this.cephMethods.cephCloneCreate(pool, image, snapshot, clone);
  cephCloneDelete = (pool: string, clone: string) => this.cephMethods.cephCloneDelete(pool, clone);
  cephCloneList = (pool: string, image: string, snapshot: string) =>
    this.cephMethods.cephCloneList(pool, image, snapshot);
  cephCloneFlatten = (pool: string, clone: string) =>
    this.cephMethods.cephCloneFlatten(pool, clone);
  cephCloneMount = (clone: string, mountPoint: string, cowSize?: string, pool?: string) =>
    this.cephMethods.cephCloneMount(clone, mountPoint, cowSize, pool);
  cephCloneUnmount = (clone: string, keepCow?: boolean, pool?: string, force?: boolean) =>
    this.cephMethods.cephCloneUnmount(clone, keepCow, pool, force);

  // Container Methods
  containerStart = (
    name: string,
    repository?: string,
    datastorePath?: string,
    networkId?: string
  ) => this.containerMethods.containerStart(name, repository, datastorePath, networkId);
  containerStop = (name: string, repository?: string, datastorePath?: string, networkId?: string) =>
    this.containerMethods.containerStop(name, repository, datastorePath, networkId);
  containerRestart = (
    name: string,
    repository?: string,
    datastorePath?: string,
    networkId?: string
  ) => this.containerMethods.containerRestart(name, repository, datastorePath, networkId);
  containerLogs = (name: string, repository?: string, datastorePath?: string, networkId?: string) =>
    this.containerMethods.containerLogs(name, repository, datastorePath, networkId);
  containerExec = (
    name: string,
    command: string,
    repository?: string,
    datastorePath?: string,
    networkId?: string
  ) => this.containerMethods.containerExec(name, command, repository, datastorePath, networkId);
  containerInspect = (
    name: string,
    repository?: string,
    datastorePath?: string,
    networkId?: string
  ) => this.containerMethods.containerInspect(name, repository, datastorePath, networkId);
  containerStats = (
    name: string,
    repository?: string,
    datastorePath?: string,
    networkId?: string
  ) => this.containerMethods.containerStats(name, repository, datastorePath, networkId);
  containerList = (repository?: string, datastorePath?: string, networkId?: string) =>
    this.containerMethods.containerList(repository, datastorePath, networkId);
  containerKill = (name: string, repository?: string, datastorePath?: string, networkId?: string) =>
    this.containerMethods.containerKill(name, repository, datastorePath, networkId);
  containerPause = (
    name: string,
    repository?: string,
    datastorePath?: string,
    networkId?: string
  ) => this.containerMethods.containerPause(name, repository, datastorePath, networkId);
  containerUnpause = (
    name: string,
    repository?: string,
    datastorePath?: string,
    networkId?: string
  ) => this.containerMethods.containerUnpause(name, repository, datastorePath, networkId);

  // Daemon Methods
  daemonSetup = (networkId?: string) => this.daemonMethods.daemonSetup(networkId);
  daemonTeardown = (networkId?: string) => this.daemonMethods.daemonTeardown(networkId);
  daemonStart = (repository?: string, datastorePath?: string, networkId?: string) =>
    this.daemonMethods.daemonStart(repository, datastorePath, networkId);
  daemonStop = (repository?: string, datastorePath?: string, networkId?: string) =>
    this.daemonMethods.daemonStop(repository, datastorePath, networkId);
  daemonStatus = (repository?: string, datastorePath?: string, networkId?: string) =>
    this.daemonMethods.daemonStatus(repository, datastorePath, networkId);
  daemonRestart = (repository?: string, datastorePath?: string, networkId?: string) =>
    this.daemonMethods.daemonRestart(repository, datastorePath, networkId);
  daemonLogs = (repository?: string, datastorePath?: string, networkId?: string) =>
    this.daemonMethods.daemonLogs(repository, datastorePath, networkId);
  renetStart = (networkId?: string) => this.daemonMethods.renetStart(networkId);
  renetStop = (networkId?: string) => this.daemonMethods.renetStop(networkId);
  renetStatus = (networkId?: string) => this.daemonMethods.renetStatus(networkId);

  // Backup Methods
  push = (repository: string, destMachine: string, datastorePath?: string) =>
    this.backupMethods.push(repository, destMachine, datastorePath);
  pull = (repository: string, sourceMachine: string, datastorePath?: string) =>
    this.backupMethods.pull(repository, sourceMachine, datastorePath);
  pushWithOptions = (
    repository: string,
    options: Parameters<BackupMethods['pushWithOptions']>[1]
  ) => this.backupMethods.pushWithOptions(repository, options);
  pullWithOptions = (
    repository: string,
    options: Parameters<BackupMethods['pullWithOptions']>[1]
  ) => this.backupMethods.pullWithOptions(repository, options);

  // Deprecated methods kept for backward compatibility
  /* eslint-disable @typescript-eslint/no-deprecated */
  backup = (repository: string, datastorePath?: string, storageName?: string) =>
    this.backupMethods.backup(repository, datastorePath, storageName);
  deploy = (repository: string, destMachine: string, datastorePath?: string) =>
    this.backupMethods.deploy(repository, destMachine, datastorePath);
  /* eslint-enable @typescript-eslint/no-deprecated */
  checkpointCreate = (
    repository: string,
    checkpointName: string,
    datastorePath?: string,
    networkId?: string | number
  ) => this.backupMethods.checkpointCreate(repository, checkpointName, datastorePath, networkId);
  checkpointRestore = (
    repository: string,
    checkpointName: string,
    datastorePath?: string,
    networkId?: string | number
  ) => this.backupMethods.checkpointRestore(repository, checkpointName, datastorePath, networkId);
  pushWithVault = (vault: VaultBuilder, timeout?: number) =>
    this.backupMethods.pushWithVault(vault, timeout);
  pullWithVault = (vault: VaultBuilder, timeout?: number) =>
    this.backupMethods.pullWithVault(vault, timeout);

  // Helper Methods
  getCombinedOutput = (result: ExecResult) => this.testHelpers.getCombinedOutput(result);
  // eslint-disable-next-line @typescript-eslint/no-deprecated
  hasNoSyntaxErrors = (result: ExecResult) => this.testHelpers.hasNoSyntaxErrors(result);
  hasValidCommandSyntax = (result: ExecResult) => this.testHelpers.hasValidCommandSyntax(result);
  isSuccess = (result: ExecResult) => this.testHelpers.isSuccess(result);
  isNotImplemented = (result: ExecResult) => this.testHelpers.isNotImplemented(result);
  getErrorMessage = (result: ExecResult) => this.testHelpers.getErrorMessage(result);
  readFixture = (relativePath: string) => this.testHelpers.readFixture(relativePath);

  // Repository Helper Methods
  writeFileToRepository = (
    repositoryName: string,
    filePath: string,
    content: string,
    datastorePath: string
  ) =>
    this.repositoryHelpers.writeFileToRepository(repositoryName, filePath, content, datastorePath);
  isContainerRunning = (containerName: string, networkId: string) =>
    this.repositoryHelpers.isContainerRunning(containerName, networkId);
  createRepositoryFork = (parentRepo: string, tag: string, datastorePath: string) =>
    this.repositoryHelpers.createRepositoryFork(parentRepo, tag, datastorePath);
  repositoryExists = (repositoryName: string, datastorePath: string) =>
    this.repositoryHelpers.repositoryExists(repositoryName, datastorePath);
  waitForPostgresReady = (
    containerName: string,
    networkId: string,
    maxAttempts?: number,
    intervalMs?: number
  ) =>
    this.repositoryHelpers.waitForPostgresReady(containerName, networkId, maxAttempts, intervalMs);

  // SQL Helper Methods
  executeSql = (containerName: string, sql: string, networkId: string) =>
    this.sqlHelpers.executeSql(containerName, sql, networkId);
  insertUserRecord = (containerName: string, username: string, origin: string, networkId: string) =>
    this.sqlHelpers.insertUserRecord(containerName, username, origin, networkId);
  recordExistsByOrigin = (containerName: string, origin: string, networkId: string) =>
    this.sqlHelpers.recordExistsByOrigin(containerName, origin, networkId);
  getUserRecordCount = (containerName: string, networkId: string) =>
    this.sqlHelpers.getUserRecordCount(containerName, networkId);
  getUsersDataHash = (containerName: string, networkId: string) =>
    this.sqlHelpers.getUsersDataHash(containerName, networkId);
  insertBulkUserRecords = (
    containerName: string,
    count: number,
    origin: string,
    networkId: string
  ) => this.sqlHelpers.insertBulkUserRecords(containerName, count, origin, networkId);
}
