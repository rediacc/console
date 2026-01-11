/**
 * SFTP Client - Direct SSH/SFTP connection for file operations
 *
 * Uses the ssh2 package for pure JS SFTP connectivity.
 * This is used by Electron for the direct file browser feature.
 */

import { Client as SSHClient, type ConnectConfig } from 'ssh2';
import { DEFAULTS } from '@rediacc/shared/config';
import type { FileInfo, SSHCredentials } from '../types/index.js';
import type { SFTPWrapper, FileEntry, Stats } from 'ssh2';

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
}

/**
 * Progress callback for file transfer operations
 */
export type TransferProgressCallback = (
  transferred: number,
  total: number,
  filename: string
) => void;

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
  private readonly ssh: SSHClient;
  private sftp: SFTPWrapper | null = null;
  private connected = false;

  constructor(private readonly config: SFTPClientConfig) {
    this.ssh = new SSHClient();
  }

  /**
   * Establish SSH connection and open SFTP subsystem
   */
  async connect(): Promise<void> {
    if (this.connected) {
      return;
    }

    return new Promise((resolve, reject) => {
      const connectConfig: ConnectConfig = {
        host: this.config.host,
        port: this.config.port ?? DEFAULTS.SSH.PORT,
        username: this.config.username,
        privateKey: this.config.privateKey,
        passphrase: this.config.passphrase,
        readyTimeout: this.config.timeout ?? DEFAULTS.SSH.READY_TIMEOUT,
        keepaliveInterval: this.config.keepaliveInterval ?? DEFAULTS.SSH.KEEPALIVE_INTERVAL,
      };

      this.ssh.on('ready', () => {
        this.ssh.sftp((err, sftp) => {
          if (err) {
            this.ssh.end();
            reject(new Error(`Failed to open SFTP subsystem: ${err.message}`));
          } else {
            this.sftp = sftp;
            this.connected = true;
            resolve();
          }
        });
      });

      this.ssh.on('error', (err) => {
        reject(new Error(`SSH connection error: ${err.message}`));
      });

      this.ssh.on('close', () => {
        this.connected = false;
        this.sftp = null;
      });

      this.ssh.connect(connectConfig);
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
}

/**
 * Create an SFTP client from SSH credentials
 *
 * @param credentials - SSH credentials
 * @returns Configured SFTP client (not connected)
 */
export function createSFTPClient(credentials: SSHCredentials): SFTPClient {
  return new SFTPClient({
    host: credentials.host,
    port: credentials.port,
    username: credentials.username,
    privateKey: credentials.privateKey,
    passphrase: credentials.passphrase,
  });
}
