import { exec } from 'node:child_process';
import * as crypto from 'node:crypto';
import * as fs from 'node:fs';
import { promisify } from 'node:util';
import { LIMITS_DEFAULTS } from '@rediacc/shared/config/defaults';
import { VM_RENET_INSTALL_PATH } from '../../constants';
import { getOpsManager, OpsManager } from '../bridge/OpsManager';
import { getRenetResolver, RenetResolver } from '../RenetResolver';
import { getSSHExecutor, SSHExecutor } from '../ssh';

const execAsync = promisify(exec);

/**
 * Calculate MD5 hash of a file.
 */
function getFileMD5(filePath: string): string {
  const content = fs.readFileSync(filePath);
  return crypto.createHash('md5').update(content).digest('hex');
}

/**
 * The renet `ops up` installed on a VM, as whatever /usr/bin/renet resolves to.
 * bridgesvc.InstallRenet (the bridge and every Ceph node) moves the binary to RENET_BINARY_PATH when that is set, and to /usr/lib/rediacc/renet/current/renet otherwise, then points /usr/bin/renet at it.
 * The target path therefore differs between CI and a local run, and only the resolved symlink is stable.
 */
const OPS_UP_RENET_PATH = '"$(readlink -f /usr/bin/renet)"';
const OPS_UP_RENET_MD5_COMMAND = `md5sum ${OPS_UP_RENET_PATH} 2>/dev/null | cut -d" " -f1`;

/**
 * The marker `renet setup` writes on completion for the default uid 7111 (config.SetupMarkerPath in private/renet/pkg/config/paths.go).
 * `renet ops up` runs `renet setup --skip-datastore` on the bridge, and with no --datastore that is the same run as the harness's own `sudo renet setup`.
 */
const RENET_SETUP_MARKER_PATH = '/var/lib/rediacc/setup_7111_completed';

/**
 * Finds a working CRIU as root, with an explicit PATH.
 * `renet setup` installs CRIU to /usr/sbin/criu, and the copy fallback below installs it to /usr/local/bin/criu.
 * A bare `which criu` over SSH runs as the login user, whose PATH on debian and opensuse has no /usr/sbin, so it reported an installed CRIU as missing and sent the harness into a source build that then failed with "criu: command not found".
 * Setting PATH inside the root shell keeps the answer independent of both the login user's PATH and sudo's secure_path, and `criu --version` proves the binary runs rather than merely exists.
 */
export const CRIU_PROBE_COMMAND =
  "sudo sh -c 'PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin; command -v criu && criu --version' 2>&1";

/**
 * True when CRIU_PROBE_COMMAND found a runnable CRIU: exit 0 and an absolute path on the first line.
 */
export function criuProbeFound(result: { code: number; stdout: string }): boolean {
  const firstLine = result.stdout.split('\n')[0]?.trim() ?? '';
  return result.code === 0 && firstLine.startsWith('/');
}

/**
 * True when the output of OPS_UP_RENET_MD5_COMMAND is exactly the local binary's md5.
 * Empty output (no /usr/bin/renet), extra lines or a mismatch are false, so the caller falls back to copying from the host.
 */
export function opsUpRenetMatchesLocal(md5Output: string, localMD5: string): boolean {
  const lines = md5Output
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
  return lines.length === 1 && lines[0] === localMD5;
}

export interface EnsureRenetOptions {
  /**
   * Set only by a global setup that has just run `renet ops up --force` in this same process.
   * Every VM was then recreated from its base image and given renet by ops up, so a VM whose ops-up install already matches the local binary byte for byte stages the deploy from that copy instead of transferring the binary from the host again.
   * The install layout and the md5 verification after it are unchanged.
   */
  freshReset?: boolean;
}

export interface InfrastructureConfig {
  bridgeVM: string;
  workerVM: string | undefined; // Can be undefined in a Ceph-only topology
  defaultTimeout: number;
}

/**
 * InfrastructureManager for bridge tests.
 *
 * Always runs in full VM mode:
 * - Automatically starts VMs using renet ops commands if not running
 * - Verifies renet is installed on all VMs
 * - No middleware or Docker containers required - renet runs in local/test mode
 *
 * DELEGATES TO SSHExecutor:
 * All SSH operations are delegated to the centralized SSHExecutor to ensure
 * consistent behavior and avoid code duplication.
 */
export class InfrastructureManager {
  private readonly config: InfrastructureConfig;
  private readonly opsManager: OpsManager;
  private readonly resolver: RenetResolver;
  private readonly sshExecutor: SSHExecutor;
  /**
   * VMs whose ops-up renet was proven identical to the local binary before the deploy replaced it.
   * The deploy rewrites /usr/bin/renet, so this is the only record of which binary ops up ran `renet setup` with.
   */
  private readonly opsUpRenetMatched = new Set<string>();

  constructor() {
    this.opsManager = getOpsManager();
    this.resolver = getRenetResolver();
    this.sshExecutor = getSSHExecutor();

    const workerIps = this.opsManager.getWorkerVMIps();
    this.config = {
      bridgeVM: this.opsManager.getBridgeVMIp(),
      workerVM: workerIps.length > 0 ? workerIps[0] : undefined,
      defaultTimeout: Number.parseInt(
        process.env.BRIDGE_TIMEOUT ?? LIMITS_DEFAULTS.CONNECTION_TIMEOUT,
        10
      ),
    };
  }

  /**
   * Get the path to renet binary (from resolver).
   */
  getRenetPath(): string {
    return this.resolver.getPath();
  }

  /**
   * Check if renet binary is available locally.
   * Uses RenetResolver which handles all resolution and auto-build logic.
   */
  async isRenetAvailable(): Promise<{ available: boolean; path: string }> {
    try {
      const result = await this.resolver.ensureBinary();
      return { available: true, path: result.path };
    } catch {
      return { available: false, path: '' };
    }
  }

  /**
   * Check if bridge VM is reachable via SSH.
   * Delegates to SSHExecutor for consistent behavior.
   */
  async isBridgeVMReachable(): Promise<boolean> {
    const ready = await this.sshExecutor.isSSHReady(this.config.bridgeVM, {
      connectTimeout: 5,
      batchMode: true,
    });
    if (!ready) {
      console.warn('[InfrastructureManager] Bridge VM check failed');
    }
    return ready;
  }

  /**
   * Check if worker VM is reachable via SSH.
   * Delegates to SSHExecutor for consistent behavior.
   * Returns true if no worker VMs are configured (a Ceph-only topology).
   */
  async isWorkerVMReachable(): Promise<boolean> {
    // In a Ceph-only topology, there are no workers - return true
    if (this.config.workerVM === undefined) {
      return true;
    }
    const ready = await this.sshExecutor.isSSHReady(this.config.workerVM, {
      connectTimeout: 5,
      batchMode: true,
    });
    if (!ready) {
      console.warn('[InfrastructureManager] Worker VM check failed');
    }
    return ready;
  }

  /**
   * Get current infrastructure status.
   */
  async getStatus(): Promise<{
    renet: { available: boolean; path: string };
    bridgeVM: boolean;
    workerVM: boolean;
  }> {
    const [renet, bridgeVM, workerVM] = await Promise.all([
      this.isRenetAvailable(),
      this.isBridgeVMReachable(),
      this.isWorkerVMReachable(),
    ]);

    return { renet, bridgeVM, workerVM };
  }

  /**
   * Ensure infrastructure is ready for tests.
   * - Verifies renet binary is available
   * - Starts VMs if not running
   * - Deploys renet to VMs if outdated
   */
  async ensureInfrastructure(options: EnsureRenetOptions = {}): Promise<void> {
    // eslint-disable-next-line no-console
    console.log('Checking infrastructure status...');

    const status = await this.getStatus();
    // eslint-disable-next-line no-console
    console.log('');
    // eslint-disable-next-line no-console
    console.log('Initial Status:');
    // eslint-disable-next-line no-console
    console.log('  Renet:', status.renet.available ? `OK (${status.renet.path})` : 'NOT FOUND');
    // eslint-disable-next-line no-console
    console.log('  Bridge VM:', status.bridgeVM ? 'OK' : 'DOWN');
    // eslint-disable-next-line no-console
    console.log('  Worker VM:', status.workerVM ? 'OK' : 'DOWN');

    if (!status.renet.available) {
      // RenetResolver already tried all resolution strategies including auto-build
      throw new Error('Renet binary not available.\n' + 'Check error messages above for details.');
    }

    // Always ensure VMs are running
    await this.ensureVMsRunning(status);

    // Ensure renet is installed on all VMs
    await this.ensureRenetOnVMs(options);
  }

  /**
   * Check if workers are configured (not a Ceph-only topology).
   */
  private hasWorkerVMs(): boolean {
    return this.config.workerVM !== undefined;
  }

  /**
   * Check if worker VMs are ready, accounting for a Ceph-only topology.
   */
  private isWorkerVMStatusReady(workerStatus: boolean): boolean {
    return this.hasWorkerVMs() ? workerStatus : true;
  }

  /**
   * Log worker VM status, including for a Ceph-only topology.
   */
  private logWorkerStatus(workerStatus: boolean): void {
    if (this.hasWorkerVMs()) {
      console.warn('  Worker VM:', workerStatus ? 'OK' : 'DOWN');
    } else {
      console.warn('  Worker VM: N/A (Ceph-only topology)');
    }
  }

  /**
   * Ensure VMs are running and ready.
   */
  private async ensureVMsRunning(status: {
    renet: { available: boolean; path: string };
    bridgeVM: boolean;
    workerVM: boolean;
  }): Promise<void> {
    const vmsReady = status.bridgeVM && this.isWorkerVMStatusReady(status.workerVM);

    if (vmsReady) {
      return;
    }

    console.warn('');
    console.warn('VMs not ready - starting via ops scripts...');

    const result = await this.opsManager.ensureVMsRunning();

    if (!result.success) {
      throw new Error(`Failed to start VMs: ${result.message}\n` + 'Check ops logs for details.');
    }

    console.warn(result.message);

    // Verify VMs are now ready
    const newStatus = await this.getStatus();
    console.warn('');
    console.warn('Updated Status:');
    console.warn('  Bridge VM:', newStatus.bridgeVM ? 'OK' : 'DOWN');
    this.logWorkerStatus(newStatus.workerVM);

    const workerReady = this.isWorkerVMStatusReady(newStatus.workerVM);
    if (!newStatus.bridgeVM || !workerReady) {
      const missing: string[] = [];
      if (!newStatus.bridgeVM) missing.push('bridge VM');
      if (this.hasWorkerVMs() && !newStatus.workerVM) missing.push('worker VM');

      throw new Error(
        `VMs started but still not reachable: ${missing.join(', ')}\n` +
          'Check network connectivity and SSH configuration.'
      );
    }
  }

  /**
   * Get MD5 hash of renet binary on a remote VM.
   */
  private async getRemoteRenetMD5(ip: string): Promise<string | null> {
    const result = await this.opsManager.executeOnVM(
      ip,
      `md5sum ${VM_RENET_INSTALL_PATH} 2>/dev/null | cut -d" " -f1`
    );
    if (result.code === 0 && result.stdout.trim().length === 32) {
      return result.stdout.trim();
    }
    return null;
  }

  /**
   * Deploy renet binary to a VM if it's different from the local version.
   * Verifies the deployment by checking MD5 after copy.
   */
  private async deployRenetToVM(
    ip: string,
    localPath: string,
    localMD5: string,
    stageFromVM = false
  ): Promise<boolean> {
    const remoteMD5 = await this.getRemoteRenetMD5(ip);

    if (remoteMD5 === localMD5) {
      return false; // Already up to date
    }

    try {
      // Copy to a temp location using SSHExecutor. Stage in /var/tmp, NOT /tmp: Fedora mounts /tmp as tmpfs capped by VM RAM, and the dev renet binary intermittently does not fit ('scp: write remote "/tmp/renet": Failure' — the recurring fedora-only setup red). Same fix as renet's
      // own Go staging sites (bridge/worker/image-builder); /var/tmp is
      // disk-backed on every distro.
      // With stageFromVM the VM already holds these exact bytes from ops up, so the stage is a VM-local copy rather than a ~200 MB transfer from the host.
      const copyResult = stageFromVM
        ? await this.stageRenetFromVM(ip)
        : await this.sshExecutor.copyTo(ip, localPath, '/var/tmp/renet', {
            execTimeout: 60000, // Increased timeout for larger binaries
          });

      if (!copyResult.success) {
        throw new Error(`Staging renet failed: ${copyResult.stderr}`);
      }

      // Move to final location, set permissions, and create symlinks: - /usr/lib/rediacc/renet/current -> versioned dir (for bridge commands) - /usr/bin/renet -> versioned binary (for PATH lookup)
      const installDir = VM_RENET_INSTALL_PATH.substring(0, VM_RENET_INSTALL_PATH.lastIndexOf('/'));
      const installRoot = installDir.substring(0, installDir.lastIndexOf('/'));
      const currentDir = `${installRoot}/current`;
      // install(1) copies the ~100MB binary; on an IO-starved CI runner right
      // after a VM reset that can exceed 10s, so give it real headroom.
      const moveResult = await this.sshExecutor.execute(
        ip,
        `sudo mkdir -p ${installDir} ${currentDir} && sudo install -m 755 /var/tmp/renet ${VM_RENET_INSTALL_PATH} && sudo ln -sf ${VM_RENET_INSTALL_PATH} ${currentDir}/renet && sudo ln -sf ${VM_RENET_INSTALL_PATH} /usr/bin/renet`,
        { execTimeout: 60000 }
      );

      if (!moveResult.success) {
        throw new Error(`Move/chmod failed: ${moveResult.stderr}`);
      }

      // Diagnostic probe: verify /usr/bin/renet symlink is visible via a non-login SSH shell (same shape the bridge harness uses for check_rediacc_cli, which just runs `which renet`). On openSUSE Leap 16.0 Minimal Cloud that test fails at 0.7s even though /usr/bin is writable — this line puts ls/readlink/which/PATH output in the CI log so we can tell whether the symlink truly
      // exists, where it resolves, and what PATH the shell sees. Never fails the deploy — diagnostic only.
      const verifyResult = await this.sshExecutor.execute(
        ip,
        'ls -la /usr/bin/renet 2>&1; readlink -f /usr/bin/renet 2>&1; which renet 2>&1; echo "PATH=$PATH"',
        { execTimeout: 5000 }
      );
      if (!verifyResult.success || !verifyResult.stdout.includes('/usr/bin/renet')) {
        console.warn(
          `[InfrastructureManager] renet symlink verification warning for ${ip}: stdout=${verifyResult.stdout} stderr=${verifyResult.stderr}`
        );
      }

      // Verify the deployment by checking MD5
      const newRemoteMD5 = await this.getRemoteRenetMD5(ip);
      if (newRemoteMD5 !== localMD5) {
        throw new Error(`MD5 mismatch after deploy: local=${localMD5}, remote=${newRemoteMD5}`);
      }

      return true;
    } catch (error: unknown) {
      const err = error as { message?: string };
      throw new Error(`Failed to deploy renet to ${ip}: ${err.message ?? 'Unknown error'}`);
    }
  }

  /**
   * Verify renet is installed and up-to-date on all VMs (bridge, workers, ceph).
   * Deploys the local version if VMs have outdated binary.
   */
  async ensureRenetOnVMs(options: EnsureRenetOptions = {}): Promise<void> {
    // eslint-disable-next-line no-console
    console.log('');
    // eslint-disable-next-line no-console
    console.log('Verifying renet on all VMs...');

    const localPath = this.getRenetPath();
    let localMD5: string;

    try {
      localMD5 = getFileMD5(localPath);
    } catch {
      throw new Error(`Cannot read local renet binary at ${localPath}`);
    }

    // Deploy to all VMs: bridge + workers + ceph. Each VM is an independent SSH/SCP round trip against its own machine, so these run concurrently rather than one at a time; the catch below re-throws with the offending IP named, so Promise.all's first-rejection-wins behavior never hides which VM failed.
    const allIPs = this.opsManager.getAllVMIps();

    await Promise.all(
      allIPs.map(async (ip) => {
        try {
          await this.ensureRenetOnVM(ip, localPath, localMD5, options);
        } catch (error: unknown) {
          const err = error as { message?: string };
          throw new Error(`ensureRenetOnVMs failed for ${ip}: ${err.message ?? 'Unknown error'}`);
        }
      })
    );
  }

  /**
   * Verify renet is installed and up-to-date on a single VM, deploying it if
   * missing or outdated. Split out of ensureRenetOnVMs so that method can run
   * this concurrently over every VM via Promise.all.
   */
  private async ensureRenetOnVM(
    ip: string,
    localPath: string,
    localMD5: string,
    options: EnsureRenetOptions
  ): Promise<void> {
    const stageFromVM = options.freshReset === true && (await this.opsUpRenetIsLocal(ip, localMD5));
    if (stageFromVM) {
      this.opsUpRenetMatched.add(ip);
    }
    const hasRenet = await this.opsManager.isRenetInstalledOnVM(ip);

    if (hasRenet) {
      // Check if update is needed
      const wasUpdated = await this.deployRenetToVM(ip, localPath, localMD5, stageFromVM);
      const version = await this.opsManager.getRenetVersionOnVM(ip);

      if (wasUpdated) {
        const source = stageFromVM ? ', staged from the ops-up copy' : '';
        // eslint-disable-next-line no-console
        console.log(`  ✓ ${ip}: renet updated (${version ?? 'unknown version'}${source})`);
      } else {
        // eslint-disable-next-line no-console
        console.log(`  ✓ ${ip}: renet installed (${version ?? 'unknown version'})`);
      }
    } else {
      // Install renet for the first time
      // eslint-disable-next-line no-console
      console.log(`  ${ip}: Installing renet...`);
      await this.deployRenetToVM(ip, localPath, localMD5);
      const version = await this.opsManager.getRenetVersionOnVM(ip);
      // eslint-disable-next-line no-console
      console.log(`  ✓ ${ip}: renet installed (${version ?? 'unknown version'})`);
    }
  }

  /**
   * Stage the renet ops up installed into /var/tmp/renet, the same place the host transfer writes.
   */
  private async stageRenetFromVM(ip: string): Promise<{ success: boolean; stderr: string }> {
    const result = await this.opsManager.executeOnVM(
      ip,
      `cp ${OPS_UP_RENET_PATH} /var/tmp/renet`,
      60000
    );
    return { success: result.code === 0, stderr: result.stderr };
  }

  /**
   * True when the renet /usr/bin/renet resolves to on the VM is the local binary.
   */
  private async opsUpRenetIsLocal(ip: string, localMD5: string): Promise<boolean> {
    const result = await this.opsManager.executeOnVM(ip, OPS_UP_RENET_MD5_COMMAND);
    return result.code === 0 && opsUpRenetMatchesLocal(result.stdout, localMD5);
  }

  /**
   * True when `renet setup` already completed on this VM with the local renet binary.
   * Requires ensureRenetOnVMs({ freshReset: true }) to have proven the ops-up binary identical to the local one first.
   * The VM was then just recreated from its base image, so the marker can only come from the setup ops up ran with that binary.
   * The rule holds for the bridge and for every worker: ops up runs `renet setup --skip-datastore` on the bridge (setupBridge) and plain `sudo renet setup` on each worker in its cluster (worker.Service.Setup in private/renet/pkg/infra/worker/service.go), and both are the run the harness would repeat.
   * When ops up skipped a VM's setup (a base image that already carries Docker, or a worker outside the `--basic` cluster), the marker is absent and this returns false.
   */
  async isSetupCompleteWithLocalRenet(ip: string): Promise<boolean> {
    if (!this.opsUpRenetMatched.has(ip)) {
      return false;
    }
    const marker = await this.opsManager.executeOnVM(ip, `sudo test -f ${RENET_SETUP_MARKER_PATH}`);
    return marker.code === 0;
  }

  /**
   * Get the OpsManager instance for direct VM operations.
   */
  getOpsManager(): OpsManager {
    return this.opsManager;
  }

  /**
   * Deploy CRIU to all worker VMs.
   *
   * Strategy:
   * 1. Probe every worker; one that already runs CRIU (normally all of them, since `renet setup` installs it) needs nothing.
   * 2. For the rest, try to extract CRIU from the bridge container (pre-built, fast).
   * 3. Fall back to building from source if the container or the copy is not available.
   *
   * Each worker is its own SSH target, so the probes and installs run concurrently.
   * CRIU is required for container checkpointing tests.
   */
  async deployCRIUToAllVMs(): Promise<void> {
    // eslint-disable-next-line no-console
    console.log('Checking CRIU deployment...');

    const bridgeIP = this.opsManager.getBridgeVMIp();
    const workerIPs = this.opsManager.getWorkerVMIps();
    const user = process.env.USER;
    if (!user) {
      throw new Error('USER environment variable is not set');
    }

    const missing = await this.workersMissingCriu(workerIPs);
    if (missing.length === 0) {
      // eslint-disable-next-line no-console
      console.log('  CRIU already installed on all workers');
      return;
    }

    const criuSourcePath = await this.extractCriuFromContainer(bridgeIP);
    try {
      await Promise.all(
        missing.map((ip) => this.installCriuOnWorker(ip, criuSourcePath, bridgeIP, user))
      );
    } finally {
      if (criuSourcePath) {
        await this.opsManager.executeOnVM(bridgeIP, `rm -f ${criuSourcePath}`);
      }
    }
  }

  /**
   * Run CRIU_PROBE_COMMAND on one VM.
   */
  private async probeCriu(ip: string): Promise<{ found: boolean; output: string }> {
    const result = await this.opsManager.executeOnVM(ip, CRIU_PROBE_COMMAND);
    return { found: criuProbeFound(result), output: `${result.stdout}${result.stderr}`.trim() };
  }

  /**
   * The worker VMs with no runnable CRIU, each logged with the probe's own output.
   */
  private async workersMissingCriu(workerIPs: string[]): Promise<string[]> {
    const probes = await Promise.all(
      workerIPs.map(async (ip) => ({ ip, ...(await this.probeCriu(ip)) }))
    );
    for (const probe of probes) {
      if (probe.found) {
        // eslint-disable-next-line no-console
        console.log(`  ✓ ${probe.ip}: CRIU already installed (${probe.output.split('\n')[0]})`);
      } else {
        // eslint-disable-next-line no-console
        console.log(`  ${probe.ip}: CRIU not found: ${probe.output || '(no output)'}`);
      }
    }
    return probes.filter((probe) => !probe.found).map((probe) => probe.ip);
  }

  /**
   * Install CRIU on one worker: the bridge copy first, the source build as the fallback.
   */
  private async installCriuOnWorker(
    ip: string,
    criuSourcePath: string | null,
    bridgeIP: string,
    user: string
  ): Promise<void> {
    if (criuSourcePath && (await this.copyCriuFromBridge(ip, criuSourcePath, bridgeIP, user))) {
      return;
    }
    await this.buildCriuFromSource(ip);
  }

  /**
   * Try to extract CRIU from bridge container.
   */
  private async extractCriuFromContainer(bridgeIP: string): Promise<string | null> {
    const containerCheck = await this.opsManager.executeOnVM(
      bridgeIP,
      "docker ps --filter 'name=bridge' --format '{{.Names}}' | head -1"
    );

    if (containerCheck.code !== 0 || !containerCheck.stdout.trim()) {
      return null;
    }

    const containerName = containerCheck.stdout.trim();
    // eslint-disable-next-line no-console
    console.log(`  Found bridge container: ${containerName}`);

    const extractResult = await this.opsManager.executeOnVM(
      bridgeIP,
      `docker cp ${containerName}:/opt/criu/criu-linux-amd64 /tmp/criu 2>/dev/null && chmod +x /tmp/criu && echo "extracted"`
    );

    if (extractResult.code === 0 && extractResult.stdout.includes('extracted')) {
      // eslint-disable-next-line no-console
      console.log('  ✓ Extracted CRIU from bridge container');
      return '/tmp/criu';
    }

    return null;
  }

  /**
   * Copy CRIU from bridge VM to worker VM.
   * Uses SSHExecutor for consistent SSH options in nested commands.
   */
  private async copyCriuFromBridge(
    ip: string,
    criuSourcePath: string,
    bridgeIP: string,
    user: string
  ): Promise<boolean> {
    console.warn(`  ${ip}: Copying CRIU from bridge...`);

    // Get SSH/SCP options for the nested commands (from bridge to worker). These run on the bridge VM, so drop `-i` (host path) — the bridge has its own key at ~/.ssh/id_rsa from renet's mesh distribution.
    const nestedOpts = this.sshExecutor.getInnerSSHOptions({
      connectTimeout: 10,
      batchMode: true,
    });
    const scpOpts = this.sshExecutor.getInnerSCPOptions({ quiet: true });

    const copyResult = await this.opsManager.executeOnVM(
      bridgeIP,
      `scp ${scpOpts} ${criuSourcePath} ${user}@${ip}:/tmp/criu && ssh ${nestedOpts} ${user}@${ip} "sudo mv /tmp/criu /usr/local/bin/criu && sudo chmod +x /usr/local/bin/criu"`
    );

    if (copyResult.code === 0) {
      console.warn(`  ✓ ${ip}: CRIU installed from container`);
      return true;
    }
    console.warn(
      `  Warning: Copy failed for ${ip} (exit ${copyResult.code}: ${copyResult.stderr.trim()}), will try building from source`
    );
    return false;
  }

  /**
   * Build CRIU from source on a worker VM.
   * A failure stays non-fatal for the run, since most suites never checkpoint, but both the install command's error and the final probe's output are printed, so the reason is in the log rather than only the word "failed".
   */
  private async buildCriuFromSource(ip: string): Promise<void> {
    // eslint-disable-next-line no-console
    console.log(`  ${ip}: Building CRIU from source (this may take a few minutes)...`);

    const vmId = ip.split('.').pop();

    const installError = await execAsync(`${this.getRenetPath()} ops worker install-criu ${vmId}`, {
      timeout: 600000,
    }).then(
      () => null,
      (error: unknown) => (error instanceof Error ? error.message : String(error))
    );

    const probe = await this.probeCriu(ip);
    if (probe.found) {
      // eslint-disable-next-line no-console
      console.log(`  ✓ ${ip}: CRIU built and installed (${probe.output.split('\n')[0]})`);
      return;
    }
    // eslint-disable-next-line no-console
    console.log(
      `  Warning: CRIU installation failed on ${ip} (non-fatal for most tests)\n` +
        `    install-criu: ${installError ?? 'exited 0'}\n` +
        `    probe: ${probe.output || '(no output)'}`
    );
  }
}
