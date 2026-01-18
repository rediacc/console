import { getSSHExecutor, SSHExecutor } from '../ssh';
import { SSH_DEFAULTS } from '../sshConfig';

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
 * DELEGATES TO SSHExecutor:
 * All SSH operations are delegated to the centralized SSHExecutor to ensure
 * consistent behavior and avoid code duplication.
 */
export class OpsVMExecutor {
  private readonly sshExecutor: SSHExecutor;

  constructor() {
    this.sshExecutor = getSSHExecutor();
  }

  /**
   * Check if a VM is reachable via ping
   */
  async isVMReachable(ip: string, timeoutSeconds = 2): Promise<boolean> {
    return this.sshExecutor.isReachable(ip, timeoutSeconds);
  }

  /**
   * Check if SSH is available on a VM
   */
  async isSSHReady(ip: string): Promise<boolean> {
    return this.sshExecutor.isSSHReady(ip, {
      connectTimeout: 5,
      quiet: true,
    });
  }

  /**
   * Wait for a VM to be ready (ping + SSH)
   */
  async waitForVM(ip: string, timeoutMs = 120000): Promise<boolean> {
    return this.sshExecutor.waitForHost(ip, timeoutMs);
  }

  /**
   * Execute a command on a remote VM via SSH
   */
  async executeOnVM(
    ip: string,
    command: string,
    timeoutMs: number = SSH_DEFAULTS.EXEC_TIMEOUT
  ): Promise<{ stdout: string; stderr: string; code: number }> {
    const result = await this.sshExecutor.execute(ip, command, {
      connectTimeout: 5,
      quiet: true,
      execTimeout: timeoutMs,
    });
    return {
      stdout: result.stdout,
      stderr: result.stderr,
      code: result.code,
    };
  }

  /**
   * Execute a command on multiple VMs in parallel
   */
  async executeOnMultipleVMs(
    ips: string[],
    command: string,
    timeoutMs: number = SSH_DEFAULTS.EXEC_TIMEOUT
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

  /**
   * Get the underlying SSHExecutor for advanced operations
   */
  getSSHExecutor(): SSHExecutor {
    return this.sshExecutor;
  }
}
