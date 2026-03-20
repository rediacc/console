import type { VaultBuilder } from '../vault/VaultBuilder';
import { BackupMethods } from './methods/BackupMethods';
import { SetupMethods } from './methods/SetupMethods';
import { OpsManager } from './OpsManager';
import type { ExecResult, RunnerConfig, TestFunctionOptions } from './types';
export type { ExecResult };
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
export declare class BridgeTestRunner {
    private readonly defaultTimeout;
    private readonly opsManager;
    private readonly bridgeVM;
    private readonly targetVM;
    private readonly sshExecutor;
    private readonly systemCheckMethods;
    private readonly setupMethods;
    private readonly datastoreMethods;
    private readonly repositoryMethods;
    private readonly cephMethods;
    private readonly containerMethods;
    private readonly daemonMethods;
    private readonly backupMethods;
    private readonly testHelpers;
    private readonly repositoryHelpers;
    private readonly sqlHelpers;
    constructor(config: RunnerConfig);
    /**
     * Resolve VM target name to IP address.
     */
    private resolveTargetVM;
    /**
     * Factory method to create a runner for worker VMs.
     */
    static forWorker(num?: 1 | 2): BridgeTestRunner;
    /**
     * Factory method to create a runner for Ceph VMs.
     */
    static forCeph(num?: 1 | 2 | 3): BridgeTestRunner;
    /**
     * Get the OpsManager for VM operations.
     */
    getOpsManager(): OpsManager;
    /**
     * Get the current target VM IP.
     */
    getTargetVM(): string;
    /**
     * Get bridge VM IP (calculated from ops config).
     */
    getBridgeVM(): string;
    /**
     * Get first worker VM IP (calculated from ops config).
     * Throws if no worker VMs are configured (Ceph-only mode).
     */
    getWorkerVM(): string;
    /**
     * Get second worker VM IP (calculated from ops config).
     * Throws if less than 2 worker VMs are configured.
     */
    getWorkerVM2(): string;
    /**
     * Get all worker VM IPs (calculated from ops config).
     */
    getWorkerVMs(): string[];
    /**
     * Get all Ceph VM IPs.
     */
    getCephVMs(): string[];
    /**
     * Get all VM IPs including bridge (calculated from ops config).
     */
    getAllVMs(): string[];
    /**
     * Check if a VM is reachable (ping + SSH).
     */
    isVMReachable(ip: string): Promise<boolean>;
    /**
     * Ensure VMs are running (starts them if not).
     * Uses ops scripts to manage VMs.
     */
    ensureVMsRunning(options?: {
        basic?: boolean;
    }): Promise<{
        success: boolean;
        message: string;
    }>;
    /**
     * Log command execution outputs for Playwright capture.
     */
    private logExecutionResult;
    /**
     * Execute a command on target VM via Bridge VM (two-hop SSH).
     * Pattern: Host → SSH → Bridge → SSH → Target → command
     * Outputs are logged to console so Playwright can capture them.
     */
    executeViaBridge(command: string, timeout?: number): Promise<ExecResult>;
    /**
     * Execute a command on a remote VM via SSH.
     * Outputs are logged to console so Playwright can capture them.
     */
    executeOnVM(host: string, command: string, timeout?: number): Promise<ExecResult>;
    /**
     * Execute on bridge VM via SSH.
     */
    executeOnBridge(command: string, timeout?: number): Promise<ExecResult>;
    /**
     * Execute on worker VM via SSH.
     */
    executeOnWorker(command: string, timeout?: number): Promise<ExecResult>;
    /**
     * Execute on second worker VM via SSH.
     */
    executeOnWorker2(command: string, timeout?: number): Promise<ExecResult>;
    /**
     * Execute a command on the target Ceph VM.
     * Alias for executeViaBridge for clarity in Ceph-specific tests.
     */
    executeOnCeph(command: string, timeout?: number): Promise<ExecResult>;
    /**
     * Execute a command on all worker VMs in parallel.
     */
    executeOnAllWorkers(command: string, timeout?: number): Promise<Map<string, ExecResult>>;
    /**
     * Build common renet command flags for test functions.
     */
    private buildCommonFlags;
    /**
     * Build Ceph-related command flags.
     */
    private buildCephFlags;
    /**
     * Build container and checkpoint flags.
     */
    private buildContainerFlags;
    /**
     * Build filesystem flags.
     */
    private buildFilesystemFlags;
    /**
     * Build installation flags.
     */
    private buildInstallationFlags;
    /**
     * Test a bridge function on target VM via two-hop SSH.
     * Uses: renet bridge once --test-mode --function <name>
     * Executes: Host → Bridge → Target VM
     */
    testFunction(opts: TestFunctionOptions): Promise<ExecResult>;
    /**
     * Test a simple function (ping, nop, hello) with minimal options.
     */
    testSimpleFunction(functionName: string): Promise<ExecResult>;
    /**
     * Get renet version on target VM to verify it's working.
     */
    getRenetVersion(): Promise<ExecResult>;
    /**
     * Check if renet is available and working on target VM.
     */
    isRenetAvailable(): Promise<boolean>;
    /**
     * Test a bridge function on a specific machine via SSH.
     * Uses `renet` directly (assumes it's in PATH on the VM).
     */
    testFunctionOnMachine(host: string, opts: TestFunctionOptions): Promise<ExecResult>;
    /**
     * Execute a direct renet CLI command on a specific machine via SSH.
     * For commands that aren't available through bridge once (e.g., setup, datastore).
     */
    executeRenetOnMachine(host: string, renetCommand: string, timeout?: number): Promise<ExecResult>;
    /**
     * Check setup status on a specific machine.
     */
    checkSetupOnMachine(host: string): Promise<ExecResult>;
    /**
     * Check datastore status on a specific machine.
     */
    checkDatastoreOnMachine(host: string, datastorePath: string): Promise<ExecResult>;
    /**
     * List repositories on a specific machine.
     */
    listRepositoriesOnMachine(host: string, datastorePath: string): Promise<ExecResult>;
    /**
     * Test a function with a full vault configuration.
     * Uses --vault-file flag for complete parameter testing.
     *
     * This enables testing ALL backup_push/pull parameters that aren't
     * available as CLI flags in test mode. The vault simulates what
     * middleware would construct for queue items.
     */
    private testFunctionWithVault;
    /**
     * Execute any function with vault configuration.
     */
    executeWithVault(functionName: string, vault: VaultBuilder, timeout?: number): Promise<ExecResult>;
    /**
     * Reset worker VM to clean state for test isolation.
     * Tears down daemon, unmounts datastore, removes backing file.
     * Call in test.beforeAll() for groups that need fresh datastore.
     */
    resetWorkerState(datastorePath?: string): Promise<void>;
    ping: () => Promise<ExecResult>;
    nop: () => Promise<ExecResult>;
    hello: () => Promise<ExecResult>;
    sshTest: () => Promise<ExecResult>;
    checkKernelCompatibility: () => Promise<ExecResult>;
    checkSetup: () => Promise<ExecResult>;
    checkMemory: () => Promise<ExecResult>;
    checkSudo: () => Promise<ExecResult>;
    checkTools: () => Promise<ExecResult>;
    checkRenet: () => Promise<ExecResult>;
    checkCriu: () => Promise<ExecResult>;
    checkBtrfs: () => Promise<ExecResult>;
    checkDrivers: () => Promise<ExecResult>;
    checkSystem: () => Promise<ExecResult>;
    checkUsers: () => Promise<ExecResult>;
    checkRediaccCli: () => Promise<ExecResult>;
    checkDatastore: (datastorePath?: string) => Promise<ExecResult>;
    setup: (datastorePath?: string, uid?: string) => Promise<ExecResult>;
    osSetup: (datastorePath?: string, uid?: string) => Promise<ExecResult>;
    setupWithOptions: (options: Parameters<SetupMethods["setupWithOptions"]>[0]) => Promise<ExecResult>;
    fixUserGroups: (uid?: string) => Promise<ExecResult>;
    datastoreInit: (size: string, datastorePath?: string, force?: boolean) => Promise<ExecResult>;
    datastoreMount: (datastorePath?: string) => Promise<ExecResult>;
    datastoreUnmount: (datastorePath?: string) => Promise<ExecResult>;
    datastoreExpand: (newSize: string, datastorePath?: string) => Promise<ExecResult>;
    datastoreResize: (newSize: string, datastorePath?: string) => Promise<ExecResult>;
    datastoreValidate: (datastorePath?: string) => Promise<ExecResult>;
    repositoryNew: (name: string, size: string, password?: string, datastorePath?: string) => Promise<ExecResult>;
    repositoryRm: (name: string, datastorePath?: string) => Promise<ExecResult>;
    repositoryMount: (name: string, password?: string, datastorePath?: string) => Promise<ExecResult>;
    repositoryUnmount: (name: string, datastorePath?: string) => Promise<ExecResult>;
    repositoryUp: (name: string, datastorePath?: string, networkId?: string) => Promise<ExecResult>;
    repositoryUpPrepOnly: (name: string, datastorePath?: string, networkId?: string) => any;
    repositoryDown: (name: string, datastorePath?: string, networkId?: string) => Promise<ExecResult>;
    repositoryList: (datastorePath?: string) => Promise<ExecResult>;
    repositoryResize: (name: string, newSize: string, password?: string, datastorePath?: string) => Promise<ExecResult>;
    repositoryInfo: (name: string, datastorePath?: string) => Promise<ExecResult>;
    repositoryStatus: (name: string, datastorePath?: string) => Promise<ExecResult>;
    repositoryValidate: (name: string, datastorePath?: string) => Promise<ExecResult>;
    repositoryGrow: (name: string, newSize: string, password?: string, datastorePath?: string) => Promise<ExecResult>;
    cephHealth: () => Promise<ExecResult>;
    cephPoolCreate: (pool: string, pgNum?: string) => Promise<ExecResult>;
    cephPoolDelete: (pool: string) => Promise<ExecResult>;
    cephPoolList: () => Promise<ExecResult>;
    cephPoolInfo: (pool: string) => Promise<ExecResult>;
    cephPoolStats: (pool: string) => Promise<ExecResult>;
    cephImageCreate: (pool: string, image: string, size: string) => Promise<ExecResult>;
    cephImageDelete: (pool: string, image: string) => Promise<ExecResult>;
    cephImageList: (pool: string) => Promise<ExecResult>;
    cephImageInfo: (pool: string, image: string) => Promise<ExecResult>;
    cephImageResize: (pool: string, image: string, newSize: string) => Promise<ExecResult>;
    cephImageMap: (pool: string, image: string) => Promise<ExecResult>;
    cephImageUnmap: (pool: string, image: string) => Promise<ExecResult>;
    cephImageFormat: (pool: string, image: string, filesystem?: string, label?: string) => Promise<ExecResult>;
    cephSnapshotCreate: (pool: string, image: string, snapshot: string) => Promise<ExecResult>;
    cephSnapshotDelete: (pool: string, image: string, snapshot: string) => Promise<ExecResult>;
    cephSnapshotList: (pool: string, image: string) => Promise<ExecResult>;
    cephSnapshotProtect: (pool: string, image: string, snapshot: string) => Promise<ExecResult>;
    cephSnapshotUnprotect: (pool: string, image: string, snapshot: string) => Promise<ExecResult>;
    cephSnapshotRollback: (pool: string, image: string, snapshot: string) => Promise<ExecResult>;
    cephCloneCreate: (pool: string, image: string, snapshot: string, clone: string) => Promise<ExecResult>;
    cephCloneDelete: (pool: string, clone: string) => Promise<ExecResult>;
    cephCloneList: (pool: string, image: string, snapshot: string) => Promise<ExecResult>;
    cephCloneFlatten: (pool: string, clone: string) => Promise<ExecResult>;
    cephCloneMount: (clone: string, mountPoint: string, cowSize?: string, pool?: string) => Promise<ExecResult>;
    cephCloneUnmount: (clone: string, keepCow?: boolean, pool?: string, force?: boolean) => Promise<ExecResult>;
    containerStart: (name: string, repository?: string, datastorePath?: string, networkId?: string) => Promise<ExecResult>;
    containerStop: (name: string, repository?: string, datastorePath?: string, networkId?: string) => Promise<ExecResult>;
    containerRestart: (name: string, repository?: string, datastorePath?: string, networkId?: string) => Promise<ExecResult>;
    containerLogs: (name: string, repository?: string, datastorePath?: string, networkId?: string) => Promise<ExecResult>;
    containerExec: (name: string, command: string, repository?: string, datastorePath?: string, networkId?: string) => Promise<ExecResult>;
    containerInspect: (name: string, repository?: string, datastorePath?: string, networkId?: string) => Promise<ExecResult>;
    containerStats: (name: string, repository?: string, datastorePath?: string, networkId?: string) => Promise<ExecResult>;
    containerList: (repository?: string, datastorePath?: string, networkId?: string) => Promise<ExecResult>;
    containerKill: (name: string, repository?: string, datastorePath?: string, networkId?: string) => Promise<ExecResult>;
    containerPause: (name: string, repository?: string, datastorePath?: string, networkId?: string) => Promise<ExecResult>;
    containerUnpause: (name: string, repository?: string, datastorePath?: string, networkId?: string) => Promise<ExecResult>;
    daemonSetup: (networkId?: string) => Promise<ExecResult>;
    daemonTeardown: (networkId?: string) => Promise<ExecResult>;
    daemonStart: (repository?: string, datastorePath?: string, networkId?: string) => Promise<ExecResult>;
    daemonStop: (repository?: string, datastorePath?: string, networkId?: string) => Promise<ExecResult>;
    daemonStatus: (repository?: string, datastorePath?: string, networkId?: string) => Promise<ExecResult>;
    daemonRestart: (repository?: string, datastorePath?: string, networkId?: string) => Promise<ExecResult>;
    daemonLogs: (repository?: string, datastorePath?: string, networkId?: string) => Promise<ExecResult>;
    renetStart: (networkId?: string) => Promise<ExecResult>;
    renetStop: (networkId?: string) => Promise<ExecResult>;
    renetStatus: (networkId?: string) => Promise<ExecResult>;
    push: (repository: string, destMachine: string, datastorePath?: string) => Promise<ExecResult>;
    pull: (repository: string, sourceMachine: string, datastorePath?: string) => Promise<ExecResult>;
    pushWithOptions: (repository: string, options: Parameters<BackupMethods["pushWithOptions"]>[1]) => Promise<ExecResult>;
    pullWithOptions: (repository: string, options: Parameters<BackupMethods["pullWithOptions"]>[1]) => Promise<ExecResult>;
    backup: (repository: string, datastorePath?: string, storageName?: string) => Promise<ExecResult>;
    deploy: (repository: string, destMachine: string, datastorePath?: string) => Promise<ExecResult>;
    checkpointCreate: (repository: string, checkpointName: string, datastorePath?: string, networkId?: string | number) => Promise<ExecResult>;
    checkpointRestore: (repository: string, checkpointName: string, datastorePath?: string, networkId?: string | number) => Promise<ExecResult>;
    pushWithVault: (vault: VaultBuilder, timeout?: number) => Promise<ExecResult>;
    pullWithVault: (vault: VaultBuilder, timeout?: number) => Promise<ExecResult>;
    getCombinedOutput: (result: ExecResult) => string;
    hasNoSyntaxErrors: (result: ExecResult) => boolean;
    hasValidCommandSyntax: (result: ExecResult) => boolean;
    isSuccess: (result: ExecResult) => boolean;
    isNotImplemented: (result: ExecResult) => boolean;
    getErrorMessage: (result: ExecResult) => string;
    readFixture: (relativePath: string) => string;
    writeFileToRepository: (repositoryName: string, filePath: string, content: string, datastorePath: string) => Promise<ExecResult>;
    isContainerRunning: (containerName: string, networkId: string) => Promise<boolean>;
    createRepositoryFork: (parentRepo: string, tag: string, datastorePath: string) => Promise<ExecResult>;
    repositoryExists: (repositoryName: string, datastorePath: string) => Promise<boolean>;
    waitForPostgresReady: (containerName: string, networkId: string, maxAttempts?: number, intervalMs?: number) => Promise<boolean>;
    executeSql: (containerName: string, sql: string, networkId: string) => Promise<string>;
    insertUserRecord: (containerName: string, username: string, origin: string, networkId: string) => Promise<void>;
    recordExistsByOrigin: (containerName: string, origin: string, networkId: string) => Promise<boolean>;
    getUserRecordCount: (containerName: string, networkId: string) => Promise<number>;
    getUsersDataHash: (containerName: string, networkId: string) => Promise<string>;
    insertBulkUserRecords: (containerName: string, count: number, origin: string, networkId: string) => Promise<void>;
}
//# sourceMappingURL=BridgeTestRunner.d.ts.map
