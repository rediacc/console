/**
 * Remote Token Storage
 *
 * Manages rotating X-Config-Token values and associated wrappedCek
 * in separate files outside the config (tokens should never be in config).
 *
 * Token file location: <configDir>/.tokens/<configName>.json
 * File permissions: 0o600
 */

import { promises as fs } from 'node:fs';
import { join } from 'node:path';
import { getConfigDir } from '@rediacc/shared/paths';
import lockfile from 'proper-lockfile';

const TOKENS_DIR = join(getConfigDir(), '.tokens');

interface TokenData {
  /** Current rotating config token */
  token: string;
  /** Wrapped CEK (base64) for this config */
  wrappedCek: string;
}

/** Lock retry options matching config-file-storage.ts */
const LOCK_OPTIONS = {
  stale: 45_000,
  retries: { retries: 900, minTimeout: 50, maxTimeout: 50, factor: 1 },
};

export class RemoteTokenStorage {
  private readonly tokensDir: string;

  constructor(tokensDir: string = TOKENS_DIR) {
    this.tokensDir = tokensDir;
  }

  private getPath(configName: string): string {
    return join(this.tokensDir, `${configName}.json`);
  }

  private async ensureDirectory(): Promise<void> {
    try {
      await fs.mkdir(this.tokensDir, { recursive: true, mode: 0o700 });
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== 'EEXIST') {
        throw error;
      }
    }
  }

  /**
   * Get the current token and wrappedCek for a config.
   * Returns null if no token file exists.
   */
  async get(configName: string): Promise<TokenData | null> {
    const path = this.getPath(configName);
    try {
      const raw = await fs.readFile(path, 'utf-8');
      return JSON.parse(raw) as TokenData;
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === 'ENOENT') {
        return null;
      }
      throw error;
    }
  }

  /**
   * Atomically save a token and wrappedCek.
   * Uses file locking + temp+rename for crash safety.
   */
  async set(configName: string, data: TokenData): Promise<void> {
    await this.ensureDirectory();
    const path = this.getPath(configName);

    // Ensure the file exists for locking (proper-lockfile requires it)
    try {
      await fs.access(path);
    } catch {
      await fs.writeFile(path, '{}', { mode: 0o600 });
    }

    const release = await lockfile.lock(path, LOCK_OPTIONS);
    try {
      const tmpPath = `${path}.tmp`;
      await fs.writeFile(tmpPath, JSON.stringify(data), { mode: 0o600 });
      await fs.rename(tmpPath, path);
    } finally {
      await release();
    }
  }

  /**
   * Update only the token value, preserving wrappedCek.
   * This is the common case during token rotation.
   */
  async updateToken(configName: string, token: string): Promise<void> {
    const existing = await this.get(configName);
    if (!existing) {
      throw new Error(`No token file for config "${configName}". Run: rdc config remote enable`);
    }
    await this.set(configName, { ...existing, token });
  }

  /**
   * Delete the token file for a config.
   */
  async delete(configName: string): Promise<void> {
    const path = this.getPath(configName);
    try {
      await fs.unlink(path);
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== 'ENOENT') {
        throw error;
      }
    }
  }
}

export const remoteTokenStorage = new RemoteTokenStorage();
