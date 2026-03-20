// BridgeTestRunner contains extensive delegation methods for backward compatibility.
// The actual implementations are in separate module files (methods/*.ts, helpers/*.ts).
import { exec } from 'node:child_process';
import { promisify } from 'node:util';
import { DEFAULT_NETWORK_ID, FORK_NETWORK_ID_A, FORK_NETWORK_ID_B } from '../../constants';
import { getSSHExecutor } from '../ssh';
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
import { getOpsManager } from './OpsManager';
const execAsync = promisify(exec);
const DEFAULT_DATASTORE_PATH = '/mnt/rediacc';
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
    constructor(config) {
        // ===========================================================================
        // Method Group Delegations (for backwards compatibility)
        // ===========================================================================
        // System Check Methods
        this.ping = () => this.systemCheckMethods.ping();
        this.nop = () => this.systemCheckMethods.nop();
        this.hello = () => this.systemCheckMethods.hello();
        this.sshTest = () => this.systemCheckMethods.sshTest();
        this.checkKernelCompatibility = () => this.systemCheckMethods.checkKernelCompatibility();
        this.checkSetup = () => this.systemCheckMethods.checkSetup();
        this.checkMemory = () => this.systemCheckMethods.checkMemory();
        this.checkSudo = () => this.systemCheckMethods.checkSudo();
        this.checkTools = () => this.systemCheckMethods.checkTools();
        this.checkRenet = () => this.systemCheckMethods.checkRenet();
        this.checkCriu = () => this.systemCheckMethods.checkCriu();
        this.checkBtrfs = () => this.systemCheckMethods.checkBtrfs();
        this.checkDrivers = () => this.systemCheckMethods.checkDrivers();
        this.checkSystem = () => this.systemCheckMethods.checkSystem();
        this.checkUsers = () => this.systemCheckMethods.checkUsers();
        this.checkRediaccCli = () => this.systemCheckMethods.checkRediaccCli();
        this.checkDatastore = (datastorePath) => this.systemCheckMethods.checkDatastore(datastorePath);
        // Setup Methods
        this.setup = (datastorePath, uid) => this.setupMethods.setup(datastorePath, uid);
        this.osSetup = (datastorePath, uid) => this.setupMethods.osSetup(datastorePath, uid);
        this.setupWithOptions = (options) => this.setupMethods.setupWithOptions(options);
        this.fixUserGroups = (uid) => this.setupMethods.fixUserGroups(uid);
        // Datastore Methods
        this.datastoreInit = (size, datastorePath, force) => this.datastoreMethods.datastoreInit(size, datastorePath, force);
        this.datastoreMount = (datastorePath) => this.datastoreMethods.datastoreMount(datastorePath);
        this.datastoreUnmount = (datastorePath) => this.datastoreMethods.datastoreUnmount(datastorePath);
        this.datastoreExpand = (newSize, datastorePath) => this.datastoreMethods.datastoreExpand(newSize, datastorePath);
        this.datastoreResize = (newSize, datastorePath) => this.datastoreMethods.datastoreResize(newSize, datastorePath);
        this.datastoreValidate = (datastorePath) => this.datastoreMethods.datastoreValidate(datastorePath);
        // Repository Methods
        this.repositoryNew = (name, size, password, datastorePath) => this.repositoryMethods.repositoryNew(name, size, password, datastorePath);
        this.repositoryRm = (name, datastorePath) => this.repositoryMethods.repositoryRm(name, datastorePath);
        this.repositoryMount = (name, password, datastorePath) => this.repositoryMethods.repositoryMount(name, password, datastorePath);
        this.repositoryUnmount = (name, datastorePath) => this.repositoryMethods.repositoryUnmount(name, datastorePath);
        this.repositoryUp = (name, datastorePath, networkId) => this.repositoryMethods.repositoryUp(name, datastorePath, networkId);
        this.repositoryUpPrepOnly = (name, datastorePath, networkId) => this.repositoryMethods.repositoryUpPrepOnly(name, datastorePath, networkId);
        this.repositoryDown = (name, datastorePath, networkId) => this.repositoryMethods.repositoryDown(name, datastorePath, networkId);
        this.repositoryList = (datastorePath) => this.repositoryMethods.repositoryList(datastorePath);
        this.repositoryResize = (name, newSize, password, datastorePath) => this.repositoryMethods.repositoryResize(name, newSize, password, datastorePath);
        this.repositoryInfo = (name, datastorePath) => this.repositoryMethods.repositoryInfo(name, datastorePath);
        this.repositoryStatus = (name, datastorePath) => this.repositoryMethods.repositoryStatus(name, datastorePath);
        this.repositoryValidate = (name, datastorePath) => this.repositoryMethods.repositoryValidate(name, datastorePath);
        this.repositoryGrow = (name, newSize, password, datastorePath) => this.repositoryMethods.repositoryGrow(name, newSize, password, datastorePath);
        // Ceph Methods
        this.cephHealth = () => this.cephMethods.cephHealth();
        this.cephPoolCreate = (pool, pgNum) => this.cephMethods.cephPoolCreate(pool, pgNum);
        this.cephPoolDelete = (pool) => this.cephMethods.cephPoolDelete(pool);
        this.cephPoolList = () => this.cephMethods.cephPoolList();
        this.cephPoolInfo = (pool) => this.cephMethods.cephPoolInfo(pool);
        this.cephPoolStats = (pool) => this.cephMethods.cephPoolStats(pool);
        this.cephImageCreate = (pool, image, size) => this.cephMethods.cephImageCreate(pool, image, size);
        this.cephImageDelete = (pool, image) => this.cephMethods.cephImageDelete(pool, image);
        this.cephImageList = (pool) => this.cephMethods.cephImageList(pool);
        this.cephImageInfo = (pool, image) => this.cephMethods.cephImageInfo(pool, image);
        this.cephImageResize = (pool, image, newSize) => this.cephMethods.cephImageResize(pool, image, newSize);
        this.cephImageMap = (pool, image) => this.cephMethods.cephImageMap(pool, image);
        this.cephImageUnmap = (pool, image) => this.cephMethods.cephImageUnmap(pool, image);
        this.cephImageFormat = (pool, image, filesystem, label) => this.cephMethods.cephImageFormat(pool, image, filesystem, label);
        this.cephSnapshotCreate = (pool, image, snapshot) => this.cephMethods.cephSnapshotCreate(pool, image, snapshot);
        this.cephSnapshotDelete = (pool, image, snapshot) => this.cephMethods.cephSnapshotDelete(pool, image, snapshot);
        this.cephSnapshotList = (pool, image) => this.cephMethods.cephSnapshotList(pool, image);
        this.cephSnapshotProtect = (pool, image, snapshot) => this.cephMethods.cephSnapshotProtect(pool, image, snapshot);
        this.cephSnapshotUnprotect = (pool, image, snapshot) => this.cephMethods.cephSnapshotUnprotect(pool, image, snapshot);
        this.cephSnapshotRollback = (pool, image, snapshot) => this.cephMethods.cephSnapshotRollback(pool, image, snapshot);
        this.cephCloneCreate = (pool, image, snapshot, clone) => this.cephMethods.cephCloneCreate(pool, image, snapshot, clone);
        this.cephCloneDelete = (pool, clone) => this.cephMethods.cephCloneDelete(pool, clone);
        this.cephCloneList = (pool, image, snapshot) => this.cephMethods.cephCloneList(pool, image, snapshot);
        this.cephCloneFlatten = (pool, clone) => this.cephMethods.cephCloneFlatten(pool, clone);
        this.cephCloneMount = (clone, mountPoint, cowSize, pool) => this.cephMethods.cephCloneMount(clone, mountPoint, cowSize, pool);
        this.cephCloneUnmount = (clone, keepCow, pool, force) => this.cephMethods.cephCloneUnmount(clone, keepCow, pool, force);
        // Container Methods
        this.containerStart = (name, repository, datastorePath, networkId) => this.containerMethods.containerStart(name, repository, datastorePath, networkId);
        this.containerStop = (name, repository, datastorePath, networkId) => this.containerMethods.containerStop(name, repository, datastorePath, networkId);
        this.containerRestart = (name, repository, datastorePath, networkId) => this.containerMethods.containerRestart(name, repository, datastorePath, networkId);
        this.containerLogs = (name, repository, datastorePath, networkId) => this.containerMethods.containerLogs(name, repository, datastorePath, networkId);
        this.containerExec = (name, command, repository, datastorePath, networkId) => this.containerMethods.containerExec(name, command, repository, datastorePath, networkId);
        this.containerInspect = (name, repository, datastorePath, networkId) => this.containerMethods.containerInspect(name, repository, datastorePath, networkId);
        this.containerStats = (name, repository, datastorePath, networkId) => this.containerMethods.containerStats(name, repository, datastorePath, networkId);
        this.containerList = (repository, datastorePath, networkId) => this.containerMethods.containerList(repository, datastorePath, networkId);
        this.containerKill = (name, repository, datastorePath, networkId) => this.containerMethods.containerKill(name, repository, datastorePath, networkId);
        this.containerPause = (name, repository, datastorePath, networkId) => this.containerMethods.containerPause(name, repository, datastorePath, networkId);
        this.containerUnpause = (name, repository, datastorePath, networkId) => this.containerMethods.containerUnpause(name, repository, datastorePath, networkId);
        // Daemon Methods
        this.daemonSetup = (networkId) => this.daemonMethods.daemonSetup(networkId);
        this.daemonTeardown = (networkId) => this.daemonMethods.daemonTeardown(networkId);
        this.daemonStart = (repository, datastorePath, networkId) => this.daemonMethods.daemonStart(repository, datastorePath, networkId);
        this.daemonStop = (repository, datastorePath, networkId) => this.daemonMethods.daemonStop(repository, datastorePath, networkId);
        this.daemonStatus = (repository, datastorePath, networkId) => this.daemonMethods.daemonStatus(repository, datastorePath, networkId);
        this.daemonRestart = (repository, datastorePath, networkId) => this.daemonMethods.daemonRestart(repository, datastorePath, networkId);
        this.daemonLogs = (repository, datastorePath, networkId) => this.daemonMethods.daemonLogs(repository, datastorePath, networkId);
        this.renetStart = (networkId) => this.daemonMethods.renetStart(networkId);
        this.renetStop = (networkId) => this.daemonMethods.renetStop(networkId);
        this.renetStatus = (networkId) => this.daemonMethods.renetStatus(networkId);
        // Backup Methods
        this.push = (repository, destMachine, datastorePath) => this.backupMethods.push(repository, destMachine, datastorePath);
        this.pull = (repository, sourceMachine, datastorePath) => this.backupMethods.pull(repository, sourceMachine, datastorePath);
        this.pushWithOptions = (repository, options) => this.backupMethods.pushWithOptions(repository, options);
        this.pullWithOptions = (repository, options) => this.backupMethods.pullWithOptions(repository, options);
        // Deprecated methods kept for backward compatibility
        /* eslint-disable @typescript-eslint/no-deprecated */
        this.backup = (repository, datastorePath, storageName) => this.backupMethods.backup(repository, datastorePath, storageName);
        this.deploy = (repository, destMachine, datastorePath) => this.backupMethods.deploy(repository, destMachine, datastorePath);
        /* eslint-enable @typescript-eslint/no-deprecated */
        this.checkpointCreate = (repository, checkpointName, datastorePath, networkId) => this.backupMethods.checkpointCreate(repository, checkpointName, datastorePath, networkId);
        this.checkpointRestore = (repository, checkpointName, datastorePath, networkId) => this.backupMethods.checkpointRestore(repository, checkpointName, datastorePath, networkId);
        this.pushWithVault = (vault, timeout) => this.backupMethods.pushWithVault(vault, timeout);
        this.pullWithVault = (vault, timeout) => this.backupMethods.pullWithVault(vault, timeout);
        // Helper Methods
        this.getCombinedOutput = (result) => this.testHelpers.getCombinedOutput(result);
        // eslint-disable-next-line @typescript-eslint/no-deprecated
        this.hasNoSyntaxErrors = (result) => this.testHelpers.hasNoSyntaxErrors(result);
        this.hasValidCommandSyntax = (result) => this.testHelpers.hasValidCommandSyntax(result);
        this.isSuccess = (result) => this.testHelpers.isSuccess(result);
        this.isNotImplemented = (result) => this.testHelpers.isNotImplemented(result);
        this.getErrorMessage = (result) => this.testHelpers.getErrorMessage(result);
        this.readFixture = (relativePath) => this.testHelpers.readFixture(relativePath);
        // Repository Helper Methods
        this.writeFileToRepository = (repositoryName, filePath, content, datastorePath) => this.repositoryHelpers.writeFileToRepository(repositoryName, filePath, content, datastorePath);
        this.isContainerRunning = (containerName, networkId) => this.repositoryHelpers.isContainerRunning(containerName, networkId);
        this.createRepositoryFork = (parentRepo, tag, datastorePath) => this.repositoryHelpers.createRepositoryFork(parentRepo, tag, datastorePath);
        this.repositoryExists = (repositoryName, datastorePath) => this.repositoryHelpers.repositoryExists(repositoryName, datastorePath);
        this.waitForPostgresReady = (containerName, networkId, maxAttempts, intervalMs) => this.repositoryHelpers.waitForPostgresReady(containerName, networkId, maxAttempts, intervalMs);
        // SQL Helper Methods
        this.executeSql = (containerName, sql, networkId) => this.sqlHelpers.executeSql(containerName, sql, networkId);
        this.insertUserRecord = (containerName, username, origin, networkId) => this.sqlHelpers.insertUserRecord(containerName, username, origin, networkId);
        this.recordExistsByOrigin = (containerName, origin, networkId) => this.sqlHelpers.recordExistsByOrigin(containerName, origin, networkId);
        this.getUserRecordCount = (containerName, networkId) => this.sqlHelpers.getUserRecordCount(containerName, networkId);
        this.getUsersDataHash = (containerName, networkId) => this.sqlHelpers.getUsersDataHash(containerName, networkId);
        this.insertBulkUserRecords = (containerName, count, origin, networkId) => this.sqlHelpers.insertBulkUserRecords(containerName, count, origin, networkId);
        if (!config.targetVM) {
            throw new Error('targetVM is required - no default execution target');
        }
        this.opsManager = getOpsManager();
        this.bridgeVM = this.opsManager.getBridgeVMIp();
        this.targetVM = this.resolveTargetVM(config.targetVM);
        // Use SSHExecutor for all SSH operations - computes options fresh each time
        // to ensure SSH keys created by `ops up` are always detected
        this.sshExecutor = getSSHExecutor();
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
        this.backupMethods = new BackupMethods(this.testFunction.bind(this), this.testFunctionWithVault.bind(this));
        // Initialize helpers
        this.testHelpers = new TestHelpers();
        this.repositoryHelpers = new RepositoryHelpers(this.executeViaBridge.bind(this));
        this.sqlHelpers = new SqlHelpers(this.executeViaBridge.bind(this));
    }
    /**
     * Resolve VM target name to IP address.
     */
    resolveTargetVM(target) {
        switch (target) {
            case 'worker1': {
                const workers = this.opsManager.getWorkerVMIps();
                if (workers.length === 0) {
                    throw new Error('No worker VMs configured - cannot target worker1 in Ceph-only mode');
                }
                return workers[0];
            }
            case 'worker2': {
                const workers = this.opsManager.getWorkerVMIps();
                if (workers.length < 2) {
                    throw new Error('Less than 2 worker VMs configured - cannot target worker2');
                }
                return workers[1];
            }
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
    static forWorker(num = 1) {
        return new BridgeTestRunner({ targetVM: `worker${num}` });
    }
    /**
     * Factory method to create a runner for Ceph VMs.
     */
    static forCeph(num = 1) {
        return new BridgeTestRunner({ targetVM: `ceph${num}` });
    }
    // ===========================================================================
    // VM Information & Management
    // ===========================================================================
    /**
     * Get the OpsManager for VM operations.
     */
    getOpsManager() {
        return this.opsManager;
    }
    /**
     * Get the current target VM IP.
     */
    getTargetVM() {
        return this.targetVM;
    }
    /**
     * Get bridge VM IP (calculated from ops config).
     */
    getBridgeVM() {
        return this.bridgeVM;
    }
    /**
     * Get first worker VM IP (calculated from ops config).
     * Throws if no worker VMs are configured (Ceph-only mode).
     */
    getWorkerVM() {
        const workers = this.opsManager.getWorkerVMIps();
        if (workers.length === 0) {
            throw new Error('No worker VMs configured - cannot get worker VM in Ceph-only mode');
        }
        return workers[0];
    }
    /**
     * Get second worker VM IP (calculated from ops config).
     * Throws if less than 2 worker VMs are configured.
     */
    getWorkerVM2() {
        const workers = this.opsManager.getWorkerVMIps();
        if (workers.length < 2) {
            throw new Error('Less than 2 worker VMs configured - cannot get worker2');
        }
        return workers[1];
    }
    /**
     * Get all worker VM IPs (calculated from ops config).
     */
    getWorkerVMs() {
        return this.opsManager.getWorkerVMIps();
    }
    /**
     * Get all Ceph VM IPs.
     */
    getCephVMs() {
        return this.opsManager.getCephVMIps();
    }
    /**
     * Get all VM IPs including bridge (calculated from ops config).
     */
    getAllVMs() {
        return this.opsManager.getVMIps();
    }
    /**
     * Check if a VM is reachable (ping + SSH).
     */
    async isVMReachable(ip) {
        const reachable = await this.opsManager.isVMReachable(ip);
        if (!reachable)
            return false;
        return this.opsManager.isSSHReady(ip);
    }
    /**
     * Ensure VMs are running (starts them if not).
     * Uses ops scripts to manage VMs.
     */
    async ensureVMsRunning(options = {}) {
        return this.opsManager.ensureVMsRunning(options);
    }
    // ===========================================================================
    // Command Execution
    // ===========================================================================
    /**
     * Log command execution outputs for Playwright capture.
     */
    logExecutionResult(stdout, stderr, code) {
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
    async executeViaBridge(command, timeout) {
        const cmdTimeout = timeout ?? this.defaultTimeout;
        const escapedForBridge = this.sshExecutor.escapeForNestedSSH(command);
        // Get SSH options fresh each time (never cache - keys may be created after instantiation)
        const sshOpts = this.sshExecutor.getSSHOptions({ connectTimeout: 10, batchMode: true });
        const user = process.env.USER;
        if (!user) {
            throw new Error('USER environment variable is not set');
        }
        // Two-hop SSH command: Host → Bridge → Target
        // Uses identity file from {RENET_DATA_DIR}/staging/.ssh/id_rsa if available
        // Always use user@host format for consistency
        const sshCmd = `ssh ${sshOpts} ${user}@${this.bridgeVM} "ssh ${sshOpts} ${user}@${this.targetVM} \\"${escapedForBridge}\\""`;
        // Log the command being executed
        // eslint-disable-next-line no-console
        console.log(`\n[SSH ${this.bridgeVM} → ${this.targetVM}] ${command}`);
        const fallbackDirect = async (reason) => {
            // eslint-disable-next-line no-console
            console.log(`[BridgeTestRunner] Falling back to direct SSH to ${this.targetVM}: ${reason}`);
            return this.executeOnVM(this.targetVM, command, timeout);
        };
        try {
            const { stdout, stderr } = await execAsync(sshCmd, { timeout: cmdTimeout });
            this.logExecutionResult(stdout, stderr, 0);
            return { stdout, stderr, code: 0 };
        }
        catch (error) {
            const err = error;
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
    async executeOnVM(host, command, timeout) {
        const cmdTimeout = timeout ?? this.defaultTimeout;
        // Get SSH options fresh each time (never cache - keys may be created after instantiation)
        const sshOpts = this.sshExecutor.getSSHOptions({ connectTimeout: 10, batchMode: true });
        const user = process.env.USER;
        if (!user) {
            throw new Error('USER environment variable is not set');
        }
        // Always use user@host format for consistency
        const sshCmd = `ssh ${sshOpts} ${user}@${host} "${command.replaceAll('"', '\\"')}"`;
        // Log the command being executed
        // eslint-disable-next-line no-console
        console.log(`\n[SSH ${host}] ${command}`);
        try {
            const { stdout, stderr } = await execAsync(sshCmd, { timeout: cmdTimeout });
            this.logExecutionResult(stdout, stderr, 0);
            return { stdout, stderr, code: 0 };
        }
        catch (error) {
            const err = error;
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
    async executeOnBridge(command, timeout) {
        return this.executeOnVM(this.getBridgeVM(), command, timeout);
    }
    /**
     * Execute on worker VM via SSH.
     */
    async executeOnWorker(command, timeout) {
        return this.executeOnVM(this.getWorkerVM(), command, timeout);
    }
    /**
     * Execute on second worker VM via SSH.
     */
    async executeOnWorker2(command, timeout) {
        return this.executeOnVM(this.getWorkerVM2(), command, timeout);
    }
    /**
     * Execute a command on the target Ceph VM.
     * Alias for executeViaBridge for clarity in Ceph-specific tests.
     */
    async executeOnCeph(command, timeout) {
        return this.executeViaBridge(command, timeout);
    }
    /**
     * Execute a command on all worker VMs in parallel.
     */
    async executeOnAllWorkers(command, timeout) {
        const workers = this.getWorkerVMs();
        const results = new Map();
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
    buildCommonFlags(opts) {
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
    buildCephFlags(opts) {
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
    buildContainerFlags(opts) {
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
    buildFilesystemFlags(opts) {
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
        return flags;
    }
    /**
     * Build installation flags.
     */
    buildInstallationFlags(opts) {
        let flags = '';
        if (opts.installSource) {
            flags += ` --install-source ${opts.installSource}`;
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
    async testFunction(opts) {
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
    async testSimpleFunction(functionName) {
        return this.testFunction({ function: functionName });
    }
    /**
     * Get renet version on target VM to verify it's working.
     */
    async getRenetVersion() {
        return this.executeViaBridge('renet version');
    }
    /**
     * Check if renet is available and working on target VM.
     */
    async isRenetAvailable() {
        const result = await this.getRenetVersion();
        return result.code === 0;
    }
    /**
     * Test a bridge function on a specific machine via SSH.
     * Uses `renet` directly (assumes it's in PATH on the VM).
     */
    async testFunctionOnMachine(host, opts) {
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
    async executeRenetOnMachine(host, renetCommand, timeout) {
        return this.executeOnVM(host, `renet ${renetCommand}`, timeout);
    }
    /**
     * Check setup status on a specific machine.
     */
    async checkSetupOnMachine(host) {
        // machine_check_system is available through bridge once
        return this.executeOnVM(host, 'renet bridge once --test-mode --function machine_check_system');
    }
    /**
     * Check datastore status on a specific machine.
     */
    async checkDatastoreOnMachine(host, datastorePath) {
        // check_datastore may need direct CLI call
        return this.executeOnVM(host, `renet datastore status --path ${datastorePath} 2>&1 || echo "datastore check completed"`);
    }
    /**
     * List repositories on a specific machine.
     */
    async listRepositoriesOnMachine(host, datastorePath) {
        return this.executeOnVM(host, `renet repository list --datastore ${datastorePath} 2>&1 || echo "list completed"`);
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
    async testFunctionWithVault(functionName, vault, timeout) {
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
        }
        finally {
            // Cleanup vault file on target VM
            await this.executeViaBridge(`rm -f ${vaultPath}`);
        }
    }
    /**
     * Execute any function with vault configuration.
     */
    async executeWithVault(functionName, vault, timeout) {
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
    async resetWorkerState(datastorePath = DEFAULT_DATASTORE_PATH) {
        // eslint-disable-next-line no-console
        console.log(`\n[Reset] Cleaning worker state at ${datastorePath}...`);
        // 1. Force teardown all daemons (stops containers, unmounts repos)
        for (const netId of [DEFAULT_NETWORK_ID, FORK_NETWORK_ID_A, FORK_NETWORK_ID_B]) {
            await this.executeViaBridge(`sudo renet daemon teardown --network-id ${netId} --force 2>/dev/null || true`);
        }
        // 2. Kill any processes using the datastore (prevents busy mount)
        await this.executeViaBridge(`sudo lsof +D ${datastorePath} 2>/dev/null | awk 'NR>1 {print $2}' | xargs -r sudo kill 2>/dev/null || true`);
        // 3. Sync filesystem before unmount
        await this.executeViaBridge('sync');
        // 4. Unmount datastore - try normal first, then lazy unmount as fallback
        await this.executeViaBridge(`mountpoint -q ${datastorePath} && (sudo umount ${datastorePath} 2>/dev/null || sudo umount -l ${datastorePath}) || true`);
        // 5. Detach any loop devices associated with the backing file
        await this.executeViaBridge(`losetup -j ${datastorePath}.img 2>/dev/null | cut -d: -f1 | xargs -r sudo losetup -d 2>/dev/null || true`);
        // 6. Remove datastore backing file
        await this.executeViaBridge(`sudo rm -f ${datastorePath}.img`);
        // 7. Clean up any leftover files in datastore directory (including hidden files)
        await this.executeViaBridge(`sudo rm -rf ${datastorePath}/* ${datastorePath}/.* 2>/dev/null || true`);
        // 8. Remove datastore marker/metadata if any
        await this.executeViaBridge(`sudo rm -f ${datastorePath}/.datastore 2>/dev/null || true`);
        // eslint-disable-next-line no-console
        console.log('[Reset] Worker state cleaned');
    }
}
//# sourceMappingURL=BridgeTestRunner.js.map