import { exec } from 'node:child_process';
import * as crypto from 'node:crypto';
import * as fs from 'node:fs';
import { promisify } from 'node:util';
import { LIMITS_DEFAULTS } from '@rediacc/shared/config/defaults';
import { VM_RENET_INSTALL_PATH } from '../../constants';
import { getOpsManager, OpsManager } from '../bridge/OpsManager';
import { getRenetBinaryPath } from '../renetPath';

const execAsync = promisify(exec);

/**
 * Calculate MD5 hash of a file.
 */
function getFileMD5(filePath: string): string {
  const content = fs.readFileSync(filePath);
  return crypto.createHash('md5').update(content).digest('hex');
}

export interface InfrastructureConfig {
  bridgeVM: string;
  workerVM: string;
  defaultTimeout: number;
}

/**
 * InfrastructureManager for bridge tests.
 *
 * Always runs in full VM mode:
 * - Automatically starts VMs using renet ops commands if not running
 * - Verifies renet is installed on all VMs
 * - No middleware or Docker containers required - renet runs in local/test mode
 */
export class InfrastructureManager {
  private readonly config: InfrastructureConfig;
  private detectedRenetPath: string | null = null;
  private readonly opsManager: OpsManager;

  constructor() {
    this.opsManager = getOpsManager();

    this.config = {
      bridgeVM: this.opsManager.getBridgeVMIp(),
      workerVM: this.opsManager.getWorkerVMIps()[0],
      defaultTimeout: Number.parseInt(
        process.env.BRIDGE_TIMEOUT ?? LIMITS_DEFAULTS.CONNECTION_TIMEOUT,
        10
      ),
    };
  }

  /**
   * Get the path to renet binary (cached after first detection).
   */
  getRenetPath(): string {
    if (this.detectedRenetPath) {
      return this.detectedRenetPath;
    }
    return getRenetBinaryPath();
  }

  /**
   * Check if renet binary is available locally.
   *
   * Uses centralized getRenetBinaryPath() which handles:
   * - VM_RENET_INSTALL_PATH env var (CI mode)
   * - RENET_BIN env var (deprecated)
   * - RENET_ROOT/bin/renet
   * - Auto-detected path
   */
  async isRenetAvailable(): Promise<{ available: boolean; path: string }> {
    const renetPath = getRenetBinaryPath();

    // Try the resolved path first
    try {
      await execAsync(`${renetPath} version`, { timeout: 5000 });
      this.detectedRenetPath = renetPath;
      return { available: true, path: renetPath };
    } catch {
      // Continue to PATH check
    }

    // Fallback: Check if in PATH
    try {
      await execAsync('renet version', { timeout: 5000 });
      this.detectedRenetPath = 'renet';
      return { available: true, path: 'renet' };
    } catch {
      // Not found
    }

    return { available: false, path: '' };
  }

  /**
   * Check if bridge VM is reachable via SSH.
   */
  async isBridgeVMReachable(): Promise<boolean> {
    try {
      await execAsync(
        `ssh -o ConnectTimeout=5 -o BatchMode=yes -o StrictHostKeyChecking=no ${this.config.bridgeVM} "echo ok"`,
        { timeout: 10000 }
      );
      return true;
    } catch {
      return false;
    }
  }

  /**
   * Check if worker VM is reachable via SSH.
   */
  async isWorkerVMReachable(): Promise<boolean> {
    try {
      await execAsync(
        `ssh -o ConnectTimeout=5 -o BatchMode=yes -o StrictHostKeyChecking=no ${this.config.workerVM} "echo ok"`,
        { timeout: 10000 }
      );
      return true;
    } catch {
      return false;
    }
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
  async ensureInfrastructure(): Promise<void> {
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
      throw new Error(
        'Renet binary not found.\n' +
          'Build manually with: cd renet && ./go dev\n' +
          'Or set RENET_BINARY_PATH environment variable.'
      );
    }

    // Always ensure VMs are running
    await this.ensureVMsRunning(status);

    // Ensure renet is installed on all VMs
    await this.ensureRenetOnVMs();
  }

  /**
   * Ensure VMs are running and ready.
   */
  private async ensureVMsRunning(status: {
    renet: { available: boolean; path: string };
    bridgeVM: boolean;
    workerVM: boolean;
  }): Promise<void> {
    const vmsReady = status.bridgeVM && status.workerVM;

    if (vmsReady) {
      return;
    }

    // eslint-disable-next-line no-console
    console.log('');
    // eslint-disable-next-line no-console
    console.log('VMs not ready - starting via ops scripts...');

    const result = await this.opsManager.ensureVMsRunning();

    if (!result.success) {
      throw new Error(`Failed to start VMs: ${result.message}\n` + 'Check ops logs for details.');
    }

    // eslint-disable-next-line no-console
    console.log(result.message);

    // Verify VMs are now ready
    const newStatus = await this.getStatus();
    // eslint-disable-next-line no-console
    console.log('');
    // eslint-disable-next-line no-console
    console.log('Updated Status:');
    // eslint-disable-next-line no-console
    console.log('  Bridge VM:', newStatus.bridgeVM ? 'OK' : 'DOWN');
    // eslint-disable-next-line no-console
    console.log('  Worker VM:', newStatus.workerVM ? 'OK' : 'DOWN');

    if (!newStatus.bridgeVM || !newStatus.workerVM) {
      const missing: string[] = [];
      if (!newStatus.bridgeVM) missing.push('bridge VM');
      if (!newStatus.workerVM) missing.push('worker VM');

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
  private async deployRenetToVM(ip: string, localPath: string, localMD5: string): Promise<boolean> {
    const remoteMD5 = await this.getRemoteRenetMD5(ip);

    if (remoteMD5 === localMD5) {
      return false; // Already up to date
    }

    // Deploy via scp to temp then sudo mv
    const user = process.env.USER;
    if (!user) {
      throw new Error('USER environment variable is not set');
    }
    try {
      // Copy to temp location
      await execAsync(
        `scp -q -o StrictHostKeyChecking=no "${localPath}" ${user}@${ip}:/tmp/renet`,
        { timeout: 60000 } // Increased timeout for larger binaries
      );

      // Move to final location and set permissions
      await execAsync(
        `ssh -q -o StrictHostKeyChecking=no ${user}@${ip} "sudo mv /tmp/renet ${VM_RENET_INSTALL_PATH} && sudo chmod +x ${VM_RENET_INSTALL_PATH}"`,
        { timeout: 10000 }
      );

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
  async ensureRenetOnVMs(): Promise<void> {
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

    // Deploy to all VMs: bridge + workers + ceph
    const allIPs = this.opsManager.getAllVMIps();

    for (const ip of allIPs) {
      const hasRenet = await this.opsManager.isRenetInstalledOnVM(ip);

      if (hasRenet) {
        // Check if update is needed
        const wasUpdated = await this.deployRenetToVM(ip, localPath, localMD5);
        const version = await this.opsManager.getRenetVersionOnVM(ip);

        if (wasUpdated) {
          // eslint-disable-next-line no-console
          console.log(`  ✓ ${ip}: renet updated (${version ?? 'unknown version'})`);
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
   * 1. Try to extract CRIU from bridge container (pre-built, fast)
   * 2. Fall back to building from source if container not available
   *
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

    // Check if any worker needs CRIU
    const anyNeedsCriu = await this.checkIfCriuNeeded(workerIPs);

    if (!anyNeedsCriu) {
      // eslint-disable-next-line no-console
      console.log('  CRIU already installed on all workers');
      return;
    }

    // Try to extract CRIU from bridge container
    const criuSourcePath = await this.extractCriuFromContainer(bridgeIP);

    // Deploy CRIU to each worker VM
    await this.deployCriuToWorkers(workerIPs, criuSourcePath, bridgeIP, user);

    // Cleanup temp file on bridge
    if (criuSourcePath) {
      await this.opsManager.executeOnVM(bridgeIP, 'rm -f /tmp/criu');
    }
  }

  /**
   * Check if any worker VM needs CRIU installation.
   */
  private async checkIfCriuNeeded(workerIPs: string[]): Promise<boolean> {
    for (const ip of workerIPs) {
      const result = await this.opsManager.executeOnVM(ip, 'which criu 2>/dev/null');
      if (result.code !== 0) {
        return true;
      }
    }
    return false;
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
   * Deploy CRIU to worker VMs.
   */
  private async deployCriuToWorkers(
    workerIPs: string[],
    criuSourcePath: string | null,
    bridgeIP: string,
    user: string
  ): Promise<void> {
    for (const ip of workerIPs) {
      const criuCheck = await this.opsManager.executeOnVM(ip, 'which criu 2>/dev/null');
      if (criuCheck.code === 0 && criuCheck.stdout.trim()) {
        // eslint-disable-next-line no-console
        console.log(`  ✓ ${ip}: CRIU already installed`);
        continue;
      }

      if (criuSourcePath) {
        const copied = await this.copyCriuFromBridge(ip, criuSourcePath, bridgeIP, user);
        if (copied) {
          continue;
        }
      }

      await this.buildCriuFromSource(ip);
    }
  }

  /**
   * Copy CRIU from bridge VM to worker VM.
   */
  private async copyCriuFromBridge(
    ip: string,
    criuSourcePath: string,
    bridgeIP: string,
    user: string
  ): Promise<boolean> {
    // eslint-disable-next-line no-console
    console.log(`  ${ip}: Copying CRIU from bridge...`);
    const copyResult = await this.opsManager.executeOnVM(
      bridgeIP,
      `scp -o StrictHostKeyChecking=no ${criuSourcePath} ${user}@${ip}:/tmp/criu && ssh -o StrictHostKeyChecking=no ${user}@${ip} "sudo mv /tmp/criu /usr/local/bin/criu && sudo chmod +x /usr/local/bin/criu"`
    );

    if (copyResult.code === 0) {
      // eslint-disable-next-line no-console
      console.log(`  ✓ ${ip}: CRIU installed from container`);
      return true;
    }
    // eslint-disable-next-line no-console
    console.log(`  Warning: Copy failed for ${ip}, will try building from source`);
    return false;
  }

  /**
   * Build CRIU from source on a worker VM.
   */
  private async buildCriuFromSource(ip: string): Promise<void> {
    // eslint-disable-next-line no-console
    console.log(`  ${ip}: Building CRIU from source (this may take a few minutes)...`);

    const vmId = ip.split('.').pop();

    await execAsync(`${getRenetBinaryPath()} ops worker install-criu ${vmId}`, {
      timeout: 600000,
    }).catch((error: unknown) => ({
      stdout: '',
      stderr: error instanceof Error ? error.message : String(error),
    }));

    const verifyResult = await this.opsManager.executeOnVM(ip, 'criu --version');
    if (verifyResult.code === 0) {
      // eslint-disable-next-line no-console
      console.log(`  ✓ ${ip}: CRIU built and installed`);
    } else {
      // eslint-disable-next-line no-console
      console.log(`  Warning: CRIU installation failed on ${ip} (non-fatal for most tests)`);
    }
  }
}
