import { SSHExecutor, getSSHExecutor, SSH_DEFAULTS, type SSHConfigOptions } from '../ssh';
import type { CommandResult } from '../types';

/**
 * OpsVMExecutor - Handles SSH command execution on VMs
 *
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

  /**
   * Create an OpsVMExecutor.
   *
   * @param sshExecutor - Optional SSHExecutor instance. If not provided, uses the default singleton.
   */
  constructor(sshExecutor?: SSHExecutor) {
    this.sshExecutor = sshExecutor ?? getSSHExecutor();
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
  ): Promise<CommandResult> {
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
  ): Promise<Map<string, CommandResult>> {
    const results = new Map<string, CommandResult>();

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

/**
 * Create an OpsVMExecutor with custom SSH configuration.
 */
export function createOpsVMExecutor(sshConfigOptions?: SSHConfigOptions): OpsVMExecutor {
  const sshExecutor = new SSHExecutor(sshConfigOptions);
  return new OpsVMExecutor(sshExecutor);
}
