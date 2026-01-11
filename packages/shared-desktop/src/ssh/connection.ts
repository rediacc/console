import { spawn, type ChildProcess } from 'node:child_process';
import { DEFAULTS } from '@rediacc/shared/config';
import { startSSHAgent, addKeyToAgent, stopSSHAgent, isSSHAgentAvailable } from './agent.js';
import { createTempSSHKeyFile, removeTempSSHKeyFile, decodeSSHKey } from './keyManager.js';
import { createTempKnownHostsFile, removeTempKnownHostsFile } from './knownHosts.js';
import { getPlatform, windowsToUnixPath } from '../utils/platform.js';

/**
 * Connection method used for SSH
 */
export type ConnectionMethod = 'file-based' | 'ssh-agent';

/**
 * SSH connection setup result
 */
export interface SSHSetupResult {
  sshOptions: string[];
  keyFilePath?: string;
  knownHostsPath: string;
  agentPid?: string;
  agentSocketPath?: string;
  connectionMethod: ConnectionMethod;
}

/**
 * Converts a path for SSH compatibility on Windows
 * Handles both Windows OpenSSH and MSYS2 SSH
 *
 * @param path - Path to convert
 * @param sshExecutable - Optional SSH executable path for detection
 * @returns Converted path
 */
export function convertPathForSSH(path: string, sshExecutable?: string): string {
  if (!path || getPlatform() !== 'windows') {
    return path;
  }

  // Determine if we're using MSYS2 SSH
  let usingMsys2 = false;
  if (sshExecutable) {
    const lowerPath = sshExecutable.toLowerCase();
    usingMsys2 = lowerPath.includes('msys') || lowerPath.includes('mingw');
  }

  if (usingMsys2) {
    // Convert Windows path to MSYS2 format
    return windowsToUnixPath(path);
  }
  // For Windows OpenSSH, just normalize backslashes to forward slashes
  return path.replaceAll('\\', '/');
}

/**
 * Builds SSH options array for a connection
 *
 * @param options - Connection setup options
 * @returns Array of SSH options (without -o prefix where applicable)
 */
export function buildSSHOptions(options: {
  knownHostsPath: string;
  keyFilePath?: string;
  port?: number;
  strictHostKeyChecking?: boolean;
  sshExecutable?: string;
  /** Force TTY allocation with -tt (default: false) */
  forceTTY?: boolean;
}): string[] {
  const {
    knownHostsPath,
    keyFilePath,
    port = 22,
    strictHostKeyChecking = true,
    sshExecutable,
    forceTTY = false,
  } = options;

  // Convert paths for SSH compatibility
  const convertedKnownHostsPath = convertPathForSSH(knownHostsPath, sshExecutable);
  const convertedKeyFilePath = keyFilePath
    ? convertPathForSSH(keyFilePath, sshExecutable)
    : undefined;

  const opts: string[] = [];

  // Force TTY allocation for interactive sessions (like Python CLI's -tt flag)
  if (forceTTY) {
    opts.push('-tt');
  }

  opts.push(
    '-o',
    `StrictHostKeyChecking=${strictHostKeyChecking ? 'yes' : 'no'}`,
    '-o',
    `UserKnownHostsFile=${convertedKnownHostsPath}`,
    '-p',
    String(port),
    // Security options
    '-o',
    'PasswordAuthentication=no',
    '-o',
    'PubkeyAuthentication=yes',
    '-o',
    'PreferredAuthentications=publickey'
  );

  if (convertedKeyFilePath) {
    opts.push('-i', convertedKeyFilePath);
  }

  return opts;
}

/**
 * Sets up SSH connection using SSH agent
 *
 * @param sshKey - SSH private key content
 * @param known_hosts - Known hosts entry from vault (REQUIRED)
 * @param port - SSH port (default: 22)
 * @param sshExecutable - Optional SSH executable for path conversion
 * @param forceTTY - Force TTY allocation with -tt (default: false)
 * @returns SSH setup result with options and agent info
 */
export async function setupSSHAgentConnection(
  sshKey: string,
  known_hosts: string,
  port = 22,
  sshExecutable?: string,
  forceTTY = false
): Promise<SSHSetupResult> {
  // Security: ALWAYS require host key from service
  if (!known_hosts || known_hosts.trim().length === 0) {
    throw new Error(
      'Security Error: No host key found in vault. ' +
        'The service MUST provide a host key for all SSH connections.'
    );
  }

  // Validate and decode the SSH key
  try {
    decodeSSHKey(sshKey);
  } catch (e) {
    throw new Error(`SSH key validation failed: ${e instanceof Error ? e.message : String(e)}`);
  }

  // Start SSH agent
  const agentResult = await startSSHAgent();

  try {
    // Add key to agent
    await addKeyToAgent(sshKey, agentResult.socketPath);

    // Create known hosts file
    const knownHostsPath = await createTempKnownHostsFile(known_hosts);

    // Build SSH options (no key file needed, agent will provide it)
    const sshOptions = buildSSHOptions({
      knownHostsPath,
      port,
      strictHostKeyChecking: true,
      sshExecutable,
      forceTTY,
    });

    return {
      sshOptions,
      knownHostsPath,
      agentPid: agentResult.agentPid,
      agentSocketPath: agentResult.socketPath,
      connectionMethod: 'ssh-agent',
    };
  } catch (error) {
    // Clean up agent if key addition fails
    await stopSSHAgent(agentResult.agentPid);
    throw error;
  }
}

/**
 * Sets up SSH connection using file-based keys
 *
 * @param sshKey - SSH private key content
 * @param known_hosts - Known hosts entry from vault (REQUIRED)
 * @param port - SSH port (default: 22)
 * @param sshExecutable - Optional SSH executable for path conversion
 * @param forceTTY - Force TTY allocation with -tt (default: false)
 * @returns SSH setup result with options and file paths
 */
export async function setupSSHConnection(
  sshKey: string,
  known_hosts: string,
  port = 22,
  sshExecutable?: string,
  forceTTY = false
): Promise<SSHSetupResult> {
  // Security: ALWAYS require host key from service
  if (!known_hosts || known_hosts.trim().length === 0) {
    throw new Error(
      'Security Error: No host key found in vault. ' +
        'The service MUST provide a host key for all SSH connections. ' +
        'Contact your administrator to add the host key to the machine vault.'
    );
  }

  // Validate and decode the SSH key
  try {
    decodeSSHKey(sshKey);
  } catch (e) {
    throw new Error(`SSH key validation failed: ${e instanceof Error ? e.message : String(e)}`);
  }

  // Create temporary files
  const keyFilePath = await createTempSSHKeyFile(sshKey);
  const knownHostsPath = await createTempKnownHostsFile(known_hosts);

  // Build SSH options
  const sshOptions = buildSSHOptions({
    knownHostsPath,
    keyFilePath,
    port,
    strictHostKeyChecking: true,
    sshExecutable,
    forceTTY,
  });

  return {
    sshOptions,
    keyFilePath,
    knownHostsPath,
    connectionMethod: 'file-based',
  };
}

/**
 * Cleans up SSH connection resources
 *
 * @param result - SSH setup result to clean up
 */
export async function cleanupSSHConnection(result: SSHSetupResult): Promise<void> {
  const cleanupPromises: Promise<void>[] = [];

  if (result.keyFilePath) {
    cleanupPromises.push(removeTempSSHKeyFile(result.keyFilePath));
  }

  if (result.knownHostsPath) {
    cleanupPromises.push(removeTempKnownHostsFile(result.knownHostsPath));
  }

  if (result.agentPid) {
    // Kill SSH agent process
    try {
      process.kill(Number.parseInt(result.agentPid, 10));
    } catch {
      // Ignore errors when killing agent
    }
  }

  await Promise.all(cleanupPromises);
}

/**
 * SSH Connection constructor options
 */
export interface SSHConnectionCtorOptions {
  /** SSH port number (default: 22) */
  port?: number;
  /** Whether to try SSH agent first (default: true) */
  preferAgent?: boolean;
  /** Force TTY allocation with -tt for interactive sessions (default: false) */
  forceTTY?: boolean;
}

/**
 * SSH Connection context manager class
 * Provides automatic resource cleanup on exit
 */
export class SSHConnection {
  private readonly sshKey: string;
  private readonly known_hosts: string;
  private readonly port: number;
  private readonly preferAgent: boolean;
  private readonly forceTTY: boolean;
  private setupResult: SSHSetupResult | null = null;
  private isSetup = false;

  /**
   * Creates an SSH connection context
   *
   * @param sshKey - SSH private key content
   * @param known_hosts - Host key from vault (REQUIRED for security)
   * @param options - Connection options (port, preferAgent, forceTTY) or port number for backward compatibility
   */
  constructor(sshKey: string, known_hosts: string, options?: SSHConnectionCtorOptions | number) {
    if (!known_hosts || known_hosts.trim().length === 0) {
      throw new Error(
        'Security Error: known_hosts is required for SSH connections. ' +
          'The service must provide a host key from the vault.'
      );
    }
    this.sshKey = sshKey;
    this.known_hosts = known_hosts;

    // Support both old (port number) and new (options object) signatures
    if (typeof options === 'number') {
      this.port = options;
      this.preferAgent = true;
      this.forceTTY = false;
    } else {
      this.port = options?.port ?? DEFAULTS.SSH.PORT;
      this.preferAgent = options?.preferAgent ?? true;
      this.forceTTY = options?.forceTTY ?? false;
    }
  }

  /**
   * Sets up the SSH connection
   *
   * If preferAgent is true, attempts to use SSH agent first and falls back
   * to file-based connections if agent setup fails.
   */
  async setup(): Promise<SSHSetupResult> {
    if (this.isSetup && this.setupResult) {
      return this.setupResult;
    }

    // Try SSH agent if preferred
    if (this.preferAgent) {
      try {
        // Check if ssh-agent is available
        const agentAvailable = await isSSHAgentAvailable();
        if (agentAvailable) {
          this.setupResult = await setupSSHAgentConnection(
            this.sshKey,
            this.known_hosts,
            this.port,
            undefined, // sshExecutable
            this.forceTTY
          );
          this.isSetup = true;
          return this.setupResult;
        }
      } catch (error) {
        // Log the error prominently (matches Python CLI behavior)
        console.warn(
          `Warning: SSH agent setup failed, using file-based keys instead.\n` +
            `  Reason: ${error instanceof Error ? error.message : String(error)}`
        );
      }
    }

    // Fall back to file-based connections
    this.setupResult = await setupSSHConnection(
      this.sshKey,
      this.known_hosts,
      this.port,
      undefined, // sshExecutable
      this.forceTTY
    );
    this.isSetup = true;

    return this.setupResult;
  }

  /**
   * Cleans up SSH resources
   */
  async cleanup(): Promise<void> {
    if (this.setupResult) {
      await cleanupSSHConnection(this.setupResult);
      this.setupResult = null;
      this.isSetup = false;
    }
  }

  /**
   * Gets the SSH options for command construction
   */
  get sshOptions(): string[] {
    if (!this.setupResult) {
      throw new Error('SSH connection not set up. Call setup() first.');
    }
    return this.setupResult.sshOptions;
  }

  /**
   * Gets the connection method being used
   */
  get connectionMethod(): ConnectionMethod {
    return this.setupResult?.connectionMethod ?? 'file-based';
  }

  /**
   * Checks if using SSH agent
   */
  get isUsingAgent(): boolean {
    return this.connectionMethod === 'ssh-agent';
  }

  /**
   * Gets the SSH agent socket path if using ssh-agent
   */
  get agentSocketPath(): string | undefined {
    return this.setupResult?.agentSocketPath;
  }

  /**
   * Executes a callback with automatic cleanup
   *
   * @param callback - Function to execute with SSH options
   * @returns Result of the callback
   */
  async withConnection<T>(callback: (sshOptions: string[]) => Promise<T>): Promise<T> {
    try {
      await this.setup();
      return await callback(this.sshOptions);
    } finally {
      await this.cleanup();
    }
  }
}

/**
 * Spawns an SSH process with the given options
 *
 * @param destination - SSH destination (user@host)
 * @param sshOptions - SSH options array
 * @param command - Optional remote command to execute
 * @param options - Spawn options including optional agent socket
 * @returns ChildProcess
 */
export function spawnSSH(
  destination: string,
  sshOptions: string[],
  command?: string,
  options?: {
    cwd?: string;
    env?: NodeJS.ProcessEnv;
    stdio?: 'inherit' | 'pipe';
    agentSocketPath?: string;
  }
): ChildProcess {
  const args = [...sshOptions, destination];
  if (command) {
    args.push(command);
  }

  // Build environment with agent socket if provided
  let env = options?.env ?? process.env;
  if (options?.agentSocketPath) {
    env = {
      ...env,
      SSH_AUTH_SOCK: options.agentSocketPath,
    };
  }

  return spawn('ssh', args, {
    cwd: options?.cwd,
    env,
    stdio: options?.stdio ?? DEFAULTS.PROCESS.STDIO,
  });
}

/**
 * Tests SSH connectivity to a host
 *
 * @param host - Hostname or IP address
 * @param port - Port number (default: 22)
 * @param timeout - Timeout in milliseconds (default: 5000)
 * @returns Object with success status and optional error message
 */
export async function testSSHConnectivity(
  host: string,
  port = 22,
  timeout = 5000
): Promise<{ success: boolean; error?: string }> {
  const net = await import('node:net');

  return new Promise((resolve) => {
    const socket = new net.Socket();

    const timer = setTimeout(() => {
      socket.destroy();
      resolve({
        success: false,
        error: `Connection to ${host}:${port} timed out after ${timeout}ms`,
      });
    }, timeout);

    socket.on('connect', () => {
      clearTimeout(timer);
      socket.destroy();
      resolve({ success: true });
    });

    socket.on('error', (err) => {
      clearTimeout(timer);
      socket.destroy();
      resolve({ success: false, error: `Connection to ${host}:${port} failed: ${err.message}` });
    });

    socket.connect(port, host);
  });
}
