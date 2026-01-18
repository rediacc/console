import { exec } from 'node:child_process';
import { promisify } from 'node:util';
import {
  getSSHOptions,
  getSCPOptions,
  isSSHKeyAvailable,
  getSSHPrivateKeyPath,
  SSH_DEFAULTS,
} from '../sshConfig';

const execAsync = promisify(exec);

/**
 * SSH configuration options.
 */
export interface SSHConfig {
  /** Connection timeout in seconds. Default: 10 */
  connectTimeout?: number;
  /** Enable batch mode (no password prompts). Default: true */
  batchMode?: boolean;
  /** Suppress warnings. Default: false */
  quiet?: boolean;
  /** Command execution timeout in milliseconds. Default: 60000 */
  execTimeout?: number;
}

/**
 * Result of SSH command execution.
 */
export interface SSHResult {
  stdout: string;
  stderr: string;
  code: number;
  success: boolean;
}

/**
 * SSHExecutor - Centralized SSH operations handler.
 *
 * DESIGN PRINCIPLES:
 * 1. Never cache SSH options - compute fresh each time (keys may be created after instantiation)
 * 2. Always use user@host format - never rely on SSH config defaults
 * 3. Standardize timeouts to 10s for CI environments
 * 4. Proper command escaping for nested SSH
 *
 * This class consolidates SSH operations that were previously scattered across:
 * - BridgeTestRunner (cached sshOpts - BUG)
 * - OpsVMExecutor (dynamic options - correct)
 * - InfrastructureManager (duplicated methods)
 * - StorageTestHelper (hardcoded options)
 */
export class SSHExecutor {
  private keyLogged = false;

  /**
   * Get SSH options string for direct SSH commands.
   *
   * CRITICAL: Called fresh each time because SSH keys may be created
   * by renet during `ops up`, after this executor is instantiated.
   *
   * @param config - Optional SSH configuration overrides
   * @returns SSH options string including identity file if available
   */
  getSSHOptions(config?: SSHConfig): string {
    const connectTimeout = config?.connectTimeout ?? SSH_DEFAULTS.CONNECT_TIMEOUT;
    const batchMode = config?.batchMode ?? SSH_DEFAULTS.BATCH_MODE;
    const quiet = config?.quiet ?? SSH_DEFAULTS.QUIET;

    // Start with base options from sshConfig
    let opts = getSSHOptions();

    // Add timeout
    opts += ` -o ConnectTimeout=${connectTimeout}`;

    // Add batch mode if enabled
    if (batchMode) {
      opts += ' -o BatchMode=yes';
    }

    // Add quiet mode if enabled
    if (quiet) {
      opts += ' -q';
    }

    // Log key status once per session
    this.logKeyStatusOnce();

    return opts;
  }

  /**
   * Get SCP options string for file copy commands.
   *
   * @param config - Optional SSH configuration overrides
   * @returns SCP options string including identity file if available
   */
  getSCPOptions(config?: SSHConfig): string {
    const quiet = config?.quiet ?? true; // SCP defaults to quiet

    let opts = getSCPOptions();

    if (quiet) {
      opts += ' -q';
    }

    return opts;
  }

  /**
   * Execute a command on a remote host via SSH.
   *
   * @param host - Target host IP or hostname
   * @param command - Command to execute
   * @param config - Optional SSH configuration
   * @returns Execution result
   */
  async execute(host: string, command: string, config?: SSHConfig): Promise<SSHResult> {
    const user = this.getUser();
    const timeout = config?.execTimeout ?? SSH_DEFAULTS.EXEC_TIMEOUT;
    const sshOpts = this.getSSHOptions(config);

    // Always use user@host format
    const escapedCommand = this.escapeForSSH(command);
    const sshCmd = `ssh ${sshOpts} ${user}@${host} "${escapedCommand}"`;

    return this.executeCommand(sshCmd, timeout);
  }

  /**
   * Execute a command through two SSH hops: Host -> Bridge -> Target.
   *
   * @param bridge - Bridge VM host
   * @param target - Target VM host
   * @param command - Command to execute on target
   * @param config - Optional SSH configuration
   * @returns Execution result
   */
  async executeNested(
    bridge: string,
    target: string,
    command: string,
    config?: SSHConfig
  ): Promise<SSHResult> {
    const user = this.getUser();
    const timeout = config?.execTimeout ?? SSH_DEFAULTS.EXEC_TIMEOUT;
    const sshOpts = this.getSSHOptions(config);

    // Escape for nested SSH (double escaping needed)
    const escapedForTarget = this.escapeForNestedSSH(command);

    // Two-hop SSH command: Host -> Bridge -> Target
    const sshCmd = `ssh ${sshOpts} ${user}@${bridge} "ssh ${sshOpts} ${user}@${target} \\"${escapedForTarget}\\""`;

    return this.executeCommand(sshCmd, timeout);
  }

  /**
   * Copy a file to a remote host via SCP.
   *
   * @param host - Target host
   * @param localPath - Local file path
   * @param remotePath - Remote destination path
   * @param config - Optional SSH configuration
   * @returns Execution result
   */
  async copyTo(
    host: string,
    localPath: string,
    remotePath: string,
    config?: SSHConfig
  ): Promise<SSHResult> {
    const user = this.getUser();
    const timeout = config?.execTimeout ?? SSH_DEFAULTS.EXEC_TIMEOUT;
    const scpOpts = this.getSCPOptions(config);

    const scpCmd = `scp ${scpOpts} "${localPath}" ${user}@${host}:${remotePath}`;

    return this.executeCommand(scpCmd, timeout);
  }

  /**
   * Copy a file from a remote host via SCP.
   *
   * @param host - Source host
   * @param remotePath - Remote file path
   * @param localPath - Local destination path
   * @param config - Optional SSH configuration
   * @returns Execution result
   */
  async copyFrom(
    host: string,
    remotePath: string,
    localPath: string,
    config?: SSHConfig
  ): Promise<SSHResult> {
    const user = this.getUser();
    const timeout = config?.execTimeout ?? SSH_DEFAULTS.EXEC_TIMEOUT;
    const scpOpts = this.getSCPOptions(config);

    const scpCmd = `scp ${scpOpts} ${user}@${host}:${remotePath} "${localPath}"`;

    return this.executeCommand(scpCmd, timeout);
  }

  /**
   * Check if a host is reachable via ping.
   *
   * @param host - Host to check
   * @param timeoutSeconds - Ping timeout in seconds
   * @returns true if reachable
   */
  async isReachable(host: string, timeoutSeconds = 2): Promise<boolean> {
    try {
      await execAsync(`ping -c 1 -W ${timeoutSeconds} ${host}`, {
        timeout: (timeoutSeconds + 1) * 1000,
      });
      return true;
    } catch {
      return false;
    }
  }

  /**
   * Check if SSH is ready on a host.
   *
   * @param host - Host to check
   * @param config - Optional SSH configuration
   * @returns true if SSH is ready
   */
  async isSSHReady(host: string, config?: SSHConfig): Promise<boolean> {
    const result = await this.execute(host, 'echo ready', {
      ...config,
      execTimeout: 10000,
    });
    return result.success;
  }

  /**
   * Wait for a host to become ready (ping + SSH).
   *
   * @param host - Host to wait for
   * @param timeoutMs - Maximum wait time in milliseconds
   * @param checkIntervalMs - Interval between checks
   * @returns true if host became ready, false if timeout
   */
  async waitForHost(host: string, timeoutMs = 120000, checkIntervalMs = 5000): Promise<boolean> {
    const startTime = Date.now();

    console.warn(`[SSHExecutor] Waiting for host ${host} to be ready...`);

    while (Date.now() - startTime < timeoutMs) {
      const reachable = await this.isReachable(host);
      if (reachable) {
        const sshReady = await this.isSSHReady(host);
        if (sshReady) {
          console.warn(`[SSHExecutor] Host ${host} is ready`);
          return true;
        }
      }

      await this.sleep(checkIntervalMs);
    }

    console.warn(`[SSHExecutor] Timeout waiting for host ${host}`);
    return false;
  }

  /**
   * Get the current user from environment.
   * @throws Error if USER environment variable is not set
   */
  private getUser(): string {
    const user = process.env.USER;
    if (!user) {
      throw new Error('USER environment variable is not set');
    }
    return user;
  }

  /**
   * Escape a command for single-hop SSH.
   */
  escapeForSSH(command: string): string {
    return command.replaceAll('\\', '\\\\').replaceAll('"', '\\"');
  }

  /**
   * Escape a command for nested (two-hop) SSH.
   * Requires double escaping: first for inner SSH, then for outer SSH.
   */
  escapeForNestedSSH(command: string): string {
    // First escape for the inner SSH (target), then for outer SSH (bridge)
    const escapedForTarget = command.replaceAll('\\', '\\\\').replaceAll('"', '\\"');
    return escapedForTarget.replaceAll('\\', '\\\\').replaceAll('"', '\\"');
  }

  /**
   * Execute a shell command with timeout handling.
   */
  private async executeCommand(cmd: string, timeout: number): Promise<SSHResult> {
    try {
      const { stdout, stderr } = await execAsync(cmd, { timeout });
      return { stdout, stderr, code: 0, success: true };
    } catch (error: unknown) {
      const err = error as Error & {
        stdout?: string;
        stderr?: string;
        code?: number;
        killed?: boolean;
        message?: string;
      };

      const stdout = err.stdout ?? '';
      const stderrPrefix = err.killed ? `Command timed out after ${timeout}ms\n` : '';
      const stderrContent = err.stderr || err.message || 'Unknown error';
      const stderr = stderrPrefix + stderrContent;
      const code = err.killed ? 124 : (err.code ?? 1);

      return { stdout, stderr, code, success: false };
    }
  }

  /**
   * Log SSH key status once per session.
   */
  private logKeyStatusOnce(): void {
    if (this.keyLogged) return;

    const keyPath = getSSHPrivateKeyPath();
    if (isSSHKeyAvailable()) {
      console.warn(`[SSHExecutor] Using SSH key: ${keyPath}`);
    } else {
      console.warn(`[SSHExecutor] SSH key not found at ${keyPath}, using default SSH`);
    }

    this.keyLogged = true;
  }

  private sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }
}

// Singleton instance
let sshExecutorInstance: SSHExecutor | null = null;

/**
 * Get the singleton SSHExecutor instance.
 *
 * Using a singleton ensures consistent SSH key logging and state across
 * all components that use SSH operations.
 */
export function getSSHExecutor(): SSHExecutor {
  sshExecutorInstance ??= new SSHExecutor();
  return sshExecutorInstance;
}
