import { exec } from 'node:child_process';
import { promisify } from 'node:util';
import { getSSHOptions, getSSHPrivateKeyPath, isSSHKeyAvailable } from '../sshConfig';

const execAsync = promisify(exec);

const UNKNOWN_ERROR = 'Unknown error';

/**
 * OpsVMExecutor - Handles SSH command execution on VMs
 *
 * Extracted from OpsManager to reduce file size.
 * Provides methods for:
 * - SSH connectivity checks
 * - Command execution on individual VMs
 * - Batch command execution on multiple VMs
 * - Renet version detection
 *
 * SSH KEYS:
 * Uses SSH keys from OPS_HOME/staging/.ssh/id_rsa (same location as renet).
 * Falls back to default SSH if key is not available.
 *
 * NOTE: SSH options are computed dynamically (not cached in constructor) because
 * renet creates SSH keys during `ops up`, which happens after this class is instantiated.
 */
export class OpsVMExecutor {
  private sshKeyLogged = false;

  /**
   * Get SSH options dynamically.
   *
   * This is called fresh each time because the SSH key may be created by renet
   * during ops up, after this executor is instantiated.
   */
  private getSSHOptionsWithTimeout(): string {
    const baseOptions = getSSHOptions();

    // Log key status once per session
    if (!this.sshKeyLogged) {
      const keyPath = getSSHPrivateKeyPath();
      if (isSSHKeyAvailable()) {
        console.warn(`[OpsVMExecutor] Using SSH key: ${keyPath}`);
      } else {
        console.warn(`[OpsVMExecutor] SSH key not found at ${keyPath}, using default SSH`);
      }
      this.sshKeyLogged = true;
    }

    return `${baseOptions} -q -o ConnectTimeout=5`;
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
        throw new Error('USER environment variable is not set');
      }
      const sshOptions = this.getSSHOptionsWithTimeout();
      await execAsync(`ssh ${sshOptions} ${user}@${ip} "echo ready"`, { timeout: 10000 });
      return true;
    } catch {
      return false;
    }
  }

  /**
   * Wait for a VM to be ready (ping + SSH)
   */
  async waitForVM(ip: string, timeoutMs = 120000): Promise<boolean> {
    const startTime = Date.now();
    const checkInterval = 5000; // 5 seconds

    console.warn(`[OpsVMExecutor] Waiting for VM ${ip} to be ready...`);

    while (Date.now() - startTime < timeoutMs) {
      const reachable = await this.isVMReachable(ip);
      if (reachable) {
        const sshReady = await this.isSSHReady(ip);
        if (sshReady) {
          console.warn(`[OpsVMExecutor] VM ${ip} is ready`);
          return true;
        }
      }

      await this.sleep(checkInterval);
    }

    console.warn(`[OpsVMExecutor] Timeout waiting for VM ${ip}`);
    return false;
  }

  /**
   * Execute a command on a remote VM via SSH
   */
  async executeOnVM(
    ip: string,
    command: string,
    timeoutMs = 60000
  ): Promise<{ stdout: string; stderr: string; code: number }> {
    const user = process.env.USER;
    if (!user) {
      throw new Error('USER environment variable is not set');
    }
    const sshOptions = this.getSSHOptionsWithTimeout();
    const sshCommand = `ssh ${sshOptions} ${user}@${ip} "${command.replaceAll('"', '\\"')}"`;

    try {
      const { stdout, stderr } = await execAsync(sshCommand, { timeout: timeoutMs });
      return { stdout, stderr, code: 0 };
    } catch (error: unknown) {
      const err = error as { stdout?: string; stderr?: string; code?: number; message?: string };
      return {
        stdout: err.stdout ?? '',
        stderr: err.stderr ?? err.message ?? UNKNOWN_ERROR,
        code: err.code ?? 1,
      };
    }
  }

  /**
   * Execute a command on multiple VMs in parallel
   */
  async executeOnMultipleVMs(
    ips: string[],
    command: string,
    timeoutMs = 60000
  ): Promise<Map<string, { stdout: string; stderr: string; code: number }>> {
    const results = new Map<string, { stdout: string; stderr: string; code: number }>();

    const promises = ips.map(async (ip) => {
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
    const result = await this.executeOnVM(ip, 'which renet || command -v renet');
    return result.code === 0 && result.stdout.trim().length > 0;
  }

  /**
   * Get renet version on a VM
   */
  async getRenetVersionOnVM(ip: string): Promise<string | null> {
    const result = await this.executeOnVM(
      ip,
      'renet version 2>/dev/null || renet --version 2>/dev/null'
    );
    if (result.code === 0) {
      return result.stdout.trim();
    }
    return null;
  }

  private sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }
}
