/**
 * SFTP Client - Direct SSH/SFTP connection for file operations
 *
 * Uses the ssh2 package for pure JS SFTP connectivity.
 * This is used by Electron for the direct file browser feature.
 */

import { lookup } from 'node:dns/promises';
import { isIP } from 'node:net';
import { DEFAULTS } from '@rediacc/shared/config';
import type { FileEntry, SFTPWrapper, Stats } from 'ssh2';
import { type ConnectConfig, Client as SSHClient } from 'ssh2';
import { fingerprint, keyBlobAlgorithm, parseKnownHosts } from '../../utils/host-keys.js';
import type { FileInfo } from '../types/index.js';
import { classifySshConnectFailure, SshConnectError } from './connect-error.js';

/**
 * Configuration for SFTP client connection
 */
export interface SFTPClientConfig {
  /** SSH host */
  host: string;
  /** SSH port (default: 22) */
  port?: number;
  /** SSH username */
  username: string;
  /** SSH private key (PEM format) */
  privateKey: string;
  /** SSH private key passphrase */
  passphrase?: string;
  /** Connection timeout in ms (default: 10000) */
  timeout?: number;
  /** Keep-alive interval in ms (default: 10000) */
  keepaliveInterval?: number;
  /**
   * Machine name as configured, used only to make a host-key mismatch error
   * actionable (it names the machine to pass to `rdc machine scan-keys`).
   * Falls back to `host` when absent.
   */
  machineName?: string;
  /** Known hosts entries for host-key verification (OpenSSH format) */
  knownHosts?: string;
  /**
   * The machine's IPv6 address. A connect to `host` that never completes
   * (EGRESS_UNREACHABLE) is retried once over it; some egress networks drop
   * IPv4 to a host they reach over IPv6.
   */
  ipv6?: string;
}

/** A hostname's IPv6 (AAAA) address, or undefined when it has none. */
export type Ipv6Resolver = (hostname: string) => Promise<string | undefined>;

const resolveAaaa: Ipv6Resolver = async (hostname) => {
  try {
    return (await lookup(hostname, { family: 6 })).address;
  } catch {
    return undefined;
  }
};

/**
 * SFTP Client for direct file operations over SSH
 *
 * Provides a Promise-based API for file operations on remote machines.
 * Sessions should be properly closed when done to release resources.
 *
 * @example
 * ```typescript
 * const client = new SFTPClient({
 *   host: 'server.example.com',
 *   username: 'user',
 *   privateKey: '-----BEGIN OPENSSH PRIVATE KEY-----...',
 * });
 *
 * await client.connect();
 * const files = await client.listDirectory('/home/user');
 * await client.close();
 * ```
 */
export class SFTPClient {
  /** Replaced once by the IPv6 retry: an ssh2 client that failed to connect is never reused. */
  private ssh: SSHClient;
  private sftp: SFTPWrapper | null = null;
  private connected = false as boolean;

  /** `createClient` and `resolveIpv6` let a test plant an ssh2 client and a resolver; production takes the defaults. */
  constructor(
    private readonly config: SFTPClientConfig,
    private readonly createClient: () => SSHClient = () => new SSHClient(),
    private readonly resolveIpv6: Ipv6Resolver = resolveAaaa
  ) {
    this.ssh = createClient();
  }

  /**
   * Establish SSH connection and open SFTP subsystem.
   *
   * A connect that never completes (kind `unreachable`) is retried once over the
   * machine's IPv6 address when it has one; every other failure is reported as is.
   */
  async connect(): Promise<void> {
    if (this.connected) {
      return;
    }
    try {
      await this.connectTo(this.config.host);
    } catch (error) {
      if (!(error instanceof SshConnectError) || error.kind !== 'unreachable') throw error;
      const ipv6 = await this.ipv6Fallback();
      if (!ipv6) throw error;
      try {
        this.ssh.end();
      } catch {
        // Best effort: the failed client is already closed.
      }
      this.ssh = this.createClient();
      try {
        await this.connectTo(ipv6);
      } catch (retryError) {
        throw error.withIpv6Attempt(ipv6, retryError);
      }
    }
  }

  /** The IPv6 address to retry over: the configured one, else the AAAA record of a hostname. */
  private async ipv6Fallback(): Promise<string | undefined> {
    const { host, ipv6 } = this.config;
    if (ipv6 && ipv6 !== host) return ipv6;
    if (isIP(host) !== 0) return undefined;
    const resolved = await this.resolveIpv6(host);
    return resolved && resolved !== host ? resolved : undefined;
  }

  private connectTo(host: string): Promise<void> {
    const ssh = this.ssh;
    return new Promise((resolve, reject) => {
      const port = this.config.port ?? DEFAULTS.SSH.PORT;
      const readyTimeout = this.config.timeout ?? DEFAULTS.SSH.READY_TIMEOUT;
      // ssh2 emits `connect` once the TCP socket is up; its absence is what separates an unanswered connect from a silent peer.
      let tcpConnected = false;
      const connectConfig: ConnectConfig = {
        host,
        port,
        username: this.config.username,
        privateKey: this.config.privateKey,
        passphrase: this.config.passphrase,
        readyTimeout,
        keepaliveInterval: this.config.keepaliveInterval ?? DEFAULTS.SSH.KEEPALIVE_INTERVAL,
      };

      // Add host-key verification when known_hosts entries are provided.
      //
      // On rejection ssh2 emits a generic transport error, which historically surfaced as an opaque "Host denied (verification failed)". Capture the offered key here so the error handler below can say what actually changed, a mismatch has several very different causes and the operator needs the fingerprints to tell them apart.
      let offeredKey: string | undefined;
      if (this.config.knownHosts) {
        const trustedKeys = parseKnownHosts(this.config.knownHosts);
        connectConfig.hostVerifier = (key: Buffer) => {
          const keyBase64 = key.toString('base64');
          const trusted = trustedKeys.some((tk) => tk.key === keyBase64);
          if (!trusted) offeredKey = keyBase64;
          return trusted;
        };
      }

      ssh.on('connect', () => {
        tcpConnected = true;
      });

      ssh.on('ready', () => {
        ssh.sftp((err, sftp) => {
          if (err) {
            ssh.end();
            reject(new Error(`Failed to open SFTP subsystem: ${err.message}`));
          } else {
            this.sftp = sftp;
            this.connected = true;
            resolve();
          }
        });
      });

      ssh.on('error', (err) => {
        if (offeredKey) {
          reject(new Error(this.hostKeyMismatchMessage(offeredKey)));
          return;
        }
        const failure = err as Error & { level?: string; code?: string };
        reject(
          new SshConnectError({
            kind: classifySshConnectFailure({
              level: failure.level,
              code: failure.code,
              tcpConnected,
            }),
            host,
            port,
            timeoutMs: readyTimeout,
            cause: err.message,
          })
        );
      });

      ssh.on('close', () => {
        // A late close from the client the IPv6 retry replaced must not tear down the live session.
        if (ssh !== this.ssh) return;
        this.connected = false;
        this.sftp = null;
      });

      ssh.connect(connectConfig);
    });
  }

  /**
   * Check if client is connected
   */
  isConnected(): boolean {
    return this.connected && this.sftp !== null;
  }

  /**
   * Ensure client is connected before operations
   */
  private ensureConnected(): SFTPWrapper {
    if (!this.sftp || !this.connected) {
      throw new Error('SFTP client is not connected');
    }
    return this.sftp;
  }

  /**
   * List contents of a directory
   *
   * @param path - Remote directory path
   * @returns Array of file information objects
   */
  async listDirectory(path: string): Promise<FileInfo[]> {
    const sftp = this.ensureConnected();

    return new Promise((resolve, reject) => {
      sftp.readdir(path, (err, list) => {
        if (err) {
          reject(new Error(`Failed to list directory '${path}': ${err.message}`));
        } else {
          const files = list.map((entry: FileEntry) => this.fileEntryToFileInfo(path, entry));
          // Sort: directories first, then by name
          files.sort((a, b) => {
            if (a.isDirectory !== b.isDirectory) {
              return a.isDirectory ? -1 : 1;
            }
            return a.name.localeCompare(b.name);
          });
          resolve(files);
        }
      });
    });
  }

  /**
   * Read file contents
   *
   * @param path - Remote file path
   * @returns File contents as Buffer
   */
  async readFile(path: string): Promise<Buffer> {
    const sftp = this.ensureConnected();

    return new Promise((resolve, reject) => {
      const chunks: Buffer[] = [];
      const stream = sftp.createReadStream(path);

      stream.on('data', (chunk: Buffer) => {
        chunks.push(chunk);
      });

      stream.on('end', () => {
        resolve(Buffer.concat(chunks));
      });

      stream.on('error', (err: Error) => {
        reject(new Error(`Failed to read file '${path}': ${err.message}`));
      });
    });
  }

  /**
   * Write data to a file
   *
   * @param path - Remote file path
   * @param data - Data to write
   */
  async writeFile(path: string, data: Buffer): Promise<void> {
    const sftp = this.ensureConnected();

    return new Promise((resolve, reject) => {
      const stream = sftp.createWriteStream(path);

      stream.on('close', () => {
        resolve();
      });

      stream.on('error', (err: Error) => {
        reject(new Error(`Failed to write file '${path}': ${err.message}`));
      });

      stream.end(data);
    });
  }

  /**
   * Create a directory
   *
   * @param path - Remote directory path
   */
  async mkdir(path: string): Promise<void> {
    const sftp = this.ensureConnected();

    return new Promise((resolve, reject) => {
      sftp.mkdir(path, (err) => {
        if (err) {
          reject(new Error(`Failed to create directory '${path}': ${err.message}`));
        } else {
          resolve();
        }
      });
    });
  }

  /**
   * Create a directory and all parent directories if they don't exist
   *
   * @param path - Remote directory path
   */
  async mkdirRecursive(path: string): Promise<void> {
    const parts = path.split('/').filter(Boolean);
    let currentPath = path.startsWith('/') ? '/' : '';

    for (const part of parts) {
      currentPath = currentPath ? `${currentPath}/${part}` : part;
      try {
        await this.stat(currentPath);
      } catch {
        await this.mkdir(currentPath);
      }
    }
  }

  /**
   * Delete a file or empty directory
   *
   * @param path - Remote file/directory path
   * @param isDirectory - Whether the path is a directory
   */
  async delete(path: string, isDirectory: boolean): Promise<void> {
    const sftp = this.ensureConnected();

    return new Promise((resolve, reject) => {
      const callback = (err: Error | null | undefined) => {
        if (err) {
          reject(new Error(`Failed to delete '${path}': ${err.message}`));
        } else {
          resolve();
        }
      };

      if (isDirectory) {
        sftp.rmdir(path, callback);
      } else {
        sftp.unlink(path, callback);
      }
    });
  }

  /**
   * Recursively delete a directory and all its contents
   *
   * @param path - Remote directory path
   */
  async deleteRecursive(path: string): Promise<void> {
    const info = await this.stat(path);

    if (!info.isDirectory) {
      await this.delete(path, false);
      return;
    }

    const entries = await this.listDirectory(path);

    for (const entry of entries) {
      if (entry.isDirectory) {
        await this.deleteRecursive(entry.path);
      } else {
        await this.delete(entry.path, false);
      }
    }

    await this.delete(path, true);
  }

  /**
   * Rename/move a file or directory
   *
   * @param oldPath - Current path
   * @param newPath - New path
   */
  async rename(oldPath: string, newPath: string): Promise<void> {
    const sftp = this.ensureConnected();

    return new Promise((resolve, reject) => {
      sftp.rename(oldPath, newPath, (err) => {
        if (err) {
          reject(new Error(`Failed to rename '${oldPath}' to '${newPath}': ${err.message}`));
        } else {
          resolve();
        }
      });
    });
  }

  /**
   * Get file/directory information
   *
   * @param path - Remote file/directory path
   * @returns File information
   */
  async stat(path: string): Promise<FileInfo> {
    const sftp = this.ensureConnected();

    return new Promise((resolve, reject) => {
      sftp.stat(path, (err, stats) => {
        if (err) {
          reject(new Error(`Failed to stat '${path}': ${err.message}`));
        } else {
          resolve(this.statsToFileInfo(path, stats));
        }
      });
    });
  }

  /**
   * Check if a file/directory exists
   *
   * @param path - Remote path
   * @returns true if exists, false otherwise
   */
  async exists(path: string): Promise<boolean> {
    try {
      await this.stat(path);
      return true;
    } catch {
      return false;
    }
  }

  /**
   * Set file permissions
   *
   * @param path - Remote file path
   * @param mode - Permission mode (e.g., 0o755)
   */
  async chmod(path: string, mode: number): Promise<void> {
    const sftp = this.ensureConnected();

    return new Promise((resolve, reject) => {
      sftp.chmod(path, mode, (err) => {
        if (err) {
          reject(new Error(`Failed to chmod '${path}': ${err.message}`));
        } else {
          resolve();
        }
      });
    });
  }

  /**
   * Get the real path (resolve symlinks)
   *
   * @param path - Remote path
   * @returns Resolved real path
   */
  async realpath(path: string): Promise<string> {
    const sftp = this.ensureConnected();

    return new Promise((resolve, reject) => {
      sftp.realpath(path, (err, resolvedPath) => {
        if (err) {
          reject(new Error(`Failed to resolve path '${path}': ${err.message}`));
        } else {
          resolve(resolvedPath);
        }
      });
    });
  }

  /**
   * Execute a command on the remote machine via SSH
   *
   * @param command - Command to execute
   * @returns Command output (stdout)
   * @throws Error if command fails or returns non-zero exit code
   */
  async exec(command: string): Promise<string> {
    if (!this.connected) {
      throw new Error('SFTP client is not connected');
    }

    return new Promise((resolve, reject) => {
      this.ssh.exec(command, (err, channel) => {
        if (err) {
          reject(new Error(`Failed to execute command: ${err.message}`));
          return;
        }

        let stdout = '';
        let stderr = '';

        channel.on('data', (data: Buffer) => {
          stdout += data.toString();
        });

        channel.stderr.on('data', (data: Buffer) => {
          stderr += data.toString();
        });

        channel.on('close', (code: number) => {
          if (code === 0) {
            resolve(stdout);
          } else {
            reject(new Error(`Command exited with code ${code}: ${stderr || stdout}`));
          }
        });

        channel.on('error', (channelErr: Error) => {
          reject(new Error(`Channel error: ${channelErr.message}`));
        });
      });
    });
  }

  /**
   * Execute a command with streaming stdin/stdout/stderr support.
   * Unlike exec(), this streams output in real-time and supports writing to stdin.
   *
   * @param command - Command to execute
   * @param options - Streaming options
   * @returns Exit code from the remote command
   */
  async execStreaming(
    command: string,
    options: {
      stdin?: string;
      onStdout?: (data: Buffer) => void;
      onStderr?: (data: Buffer) => void;
    }
  ): Promise<number> {
    if (!this.connected) {
      throw new Error('SFTP client is not connected');
    }

    return new Promise((resolve, reject) => {
      this.ssh.exec(command, (err, channel) => {
        if (err) {
          reject(new Error(`Failed to execute command: ${err.message}`));
          return;
        }

        if (options.stdin) {
          channel.write(options.stdin);
          channel.end();
        } else {
          channel.end();
        }

        channel.on('data', (data: Buffer) => {
          if (options.onStdout) {
            options.onStdout(data);
          }
        });

        channel.stderr.on('data', (data: Buffer) => {
          if (options.onStderr) {
            options.onStderr(data);
          }
        });

        channel.on('close', (code: number) => {
          resolve(code);
        });

        channel.on('error', (channelErr: Error) => {
          reject(new Error(`Channel error: ${channelErr.message}`));
        });
      });
    });
  }

  /**
   * Close the SFTP session and SSH connection
   */
  close(): void {
    if (this.sftp) {
      this.sftp.end();
      this.sftp = null;
    }

    this.ssh.end();
    this.connected = false;
  }

  /**
   * Convert ssh2 FileEntry to our FileInfo type
   */
  private fileEntryToFileInfo(parentPath: string, entry: FileEntry): FileInfo {
    const fullPath = parentPath.endsWith('/')
      ? `${parentPath}${entry.filename}`
      : `${parentPath}/${entry.filename}`;

    // Check file type from mode bits
    // S_IFMT = 0o170000 (file type mask)
    // S_IFDIR = 0o040000 (directory)
    // S_IFREG = 0o100000 (regular file)
    // S_IFLNK = 0o120000 (symbolic link)
    const mode = entry.attrs.mode;
    const fileTypeMask = mode & 0o170000;
    const isDirectory = fileTypeMask === 0o040000;
    const isFile = fileTypeMask === 0o100000;
    const isSymlink = fileTypeMask === 0o120000;

    return {
      name: entry.filename,
      path: fullPath,
      isDirectory,
      isFile,
      isSymlink,
      size: entry.attrs.size,
      modifiedAt: new Date(entry.attrs.mtime * 1000),
      permissions: this.formatPermissions(mode),
      owner: entry.attrs.uid.toString(),
      group: entry.attrs.gid.toString(),
    };
  }

  /**
   * Convert ssh2 Stats to our FileInfo type
   */
  private statsToFileInfo(path: string, stats: Stats): FileInfo {
    const name = path.split('/').pop() ?? '';

    return {
      name,
      path,
      isDirectory: stats.isDirectory(),
      isFile: stats.isFile(),
      isSymlink: stats.isSymbolicLink(),
      size: stats.size,
      modifiedAt: new Date(stats.mtime * 1000),
      permissions: this.formatPermissions(stats.mode),
      owner: stats.uid.toString(),
      group: stats.gid.toString(),
    };
  }

  /**
   * Format mode number to permission string (e.g., "755")
   */
  private formatPermissions(mode: number): string {
    return (mode & 0o777).toString(8);
  }

  /** Build the host-key mismatch message for this connection's config. */
  private hostKeyMismatchMessage(offeredKey: string): string {
    return buildHostKeyMismatchMessage({
      machineName: this.config.machineName ?? this.config.host,
      host: this.config.host,
      knownHosts: this.config.knownHosts ?? '',
      offeredKey,
    });
  }
}

/**
 * Explain a host-key mismatch in terms the operator can act on.
 *
 * Deliberately not a "tip: run scan-keys" hint. Pinning exists to make exactly
 * this failure loud, and an unconditional remedy trains the reflex of re-pinning
 * on every mismatch, which defeats the point. The remedy is stated
 * conditionally, after the causes and the fingerprints needed to tell them
 * apart.
 *
 * A stale local config is listed as a cause because it is a real and easily
 * missed one: several divergent copies of the config file will present an old
 * pin against an unchanged host, which looks identical to key rotation.
 */
export function buildHostKeyMismatchMessage(params: {
  machineName: string;
  host: string;
  knownHosts: string;
  offeredKey: string;
}): string {
  const { machineName, host, knownHosts, offeredKey } = params;

  const offeredType = keyBlobAlgorithm(offeredKey);
  const pinned = parseKnownHosts(knownHosts);

  // Compare like with like: a host offers one key per algorithm, so the meaningful comparison is against the pin of the same algorithm. Falling back to listing every pin keeps the message useful when the offered blob cannot be decoded.
  const sameAlgorithm = offeredType ? pinned.filter((e) => e.type === offeredType) : [];
  const toShow = sameAlgorithm.length ? sameAlgorithm : pinned;

  const pinnedSummary = toShow.length
    ? toShow.map((e) => `  pinned:   ${e.type} ${fingerprint(e.key)}`).join('\n')
    : '  pinned:   (none recorded)';

  return [
    `Host key mismatch for "${machineName}" (${host})`,
    '',
    pinnedSummary,
    `  offered:  ${offeredType || '(unknown algorithm)'} ${fingerprint(offeredKey)}`,
    '',
    'A rebuilt, reinstalled, or migrated machine will do this. So will a stale',
    'local config, and so will a man-in-the-middle. Confirm the fingerprint out',
    'of band before trusting it.',
    '',
    `If the change is expected: rdc machine scan-keys ${machineName}`,
  ].join('\n');
}
