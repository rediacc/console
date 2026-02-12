/**
 * StorageBrowserService - Browse files in remote storage systems.
 *
 * Calls `rclone lsjson` directly with credentials from vault content,
 * using shared parsers from @rediacc/shared to parse the output.
 */

import { spawn } from 'node:child_process';
import {
  buildRcloneArgs,
  FileListParserFactory,
  type RemoteFile,
} from '@rediacc/shared/queue-vault';

/** Default timeout for rclone operations (30 seconds). */
const RCLONE_TIMEOUT_MS = 30_000;

interface SpawnResult {
  stdout: string;
  stderr: string;
  exitCode: number;
}

class StorageBrowserService {
  /**
   * List files in a storage at the given path.
   * Calls `rclone lsjson` directly with credentials from vault content.
   */
  async browse(
    vaultContent: Record<string, unknown>,
    subPath?: string
  ): Promise<RemoteFile[]> {
    const { remote, params } = buildRcloneArgs(vaultContent, subPath);
    const args = ['lsjson', remote, ...params];

    const result = await this.spawnRclone(args);

    if (result.exitCode !== 0) {
      const errorMsg = result.stderr.trim() || `rclone exited with code ${result.exitCode}`;
      throw new Error(errorMsg);
    }

    const parser = new FileListParserFactory(subPath ?? '', { detectGuids: true });
    return parser.parse(result.stdout);
  }

  /**
   * Check if rclone binary is available in PATH.
   */
  async isAvailable(): Promise<boolean> {
    try {
      const result = await this.spawnRclone(['version'], 5_000);
      return result.exitCode === 0;
    } catch {
      return false;
    }
  }

  private spawnRclone(args: string[], timeout = RCLONE_TIMEOUT_MS): Promise<SpawnResult> {
    return new Promise((resolve, reject) => {
      const child = spawn('rclone', args, {
        stdio: ['ignore', 'pipe', 'pipe'],
      });

      let stdout = '';
      let stderr = '';

      child.stdout.on('data', (data: Buffer) => {
        stdout += data.toString();
      });
      child.stderr.on('data', (data: Buffer) => {
        stderr += data.toString();
      });

      const timer = setTimeout(() => {
        child.kill('SIGTERM');
        reject(new Error(`rclone timed out after ${timeout}ms`));
      }, timeout);

      child.on('close', (code) => {
        clearTimeout(timer);
        resolve({ stdout, stderr, exitCode: code ?? 1 });
      });

      child.on('error', (err) => {
        clearTimeout(timer);
        if ((err as NodeJS.ErrnoException).code === 'ENOENT') {
          reject(new Error('rclone is not installed or not in PATH. Install it from https://rclone.org/install/'));
        } else {
          reject(err);
        }
      });
    });
  }
}

export const storageBrowserService = new StorageBrowserService();
