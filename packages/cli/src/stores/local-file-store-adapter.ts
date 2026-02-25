import { promises as fs } from 'node:fs';
import { join } from 'node:path';
import type { IStoreAdapter, PullResult, PushResult } from './types.js';
import type { RdcConfig } from '../types/index.js';
import type { StoreEntry } from '../types/store.js';

/**
 * Local file store adapter. Stores config files as JSON in a local directory.
 * Useful for backups on another disk, mounted volume, or shared folder.
 */
export class LocalFileStoreAdapter implements IStoreAdapter {
  private readonly basePath: string;

  constructor(entry: StoreEntry) {
    if (!entry.localPath) {
      throw new Error('Local file store requires a localPath');
    }
    this.basePath = entry.localPath;
  }

  private configPath(configName: string): string {
    return join(this.basePath, `${configName}.json`);
  }

  async push(config: RdcConfig, configName: string): Promise<PushResult> {
    const filePath = this.configPath(configName);

    // Check remote for conflict
    try {
      const content = await fs.readFile(filePath, 'utf-8');
      const remote = JSON.parse(content) as RdcConfig;
      if (remote.id !== config.id) {
        return {
          success: false,
          error: `GUID mismatch: local config id "${config.id}" does not match remote "${remote.id}".`,
        };
      }
      if (remote.version > config.version) {
        return {
          success: false,
          error: `Version conflict: remote version ${remote.version} is newer than local version ${config.version}. Run "rdc store pull" first.`,
        };
      }
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error;
      // File doesn't exist — no conflict
    }

    await fs.mkdir(this.basePath, { recursive: true });
    const tempPath = `${filePath}.tmp.${process.pid}.${Date.now()}`;
    await fs.writeFile(tempPath, JSON.stringify(config, null, 2), { mode: 0o600 });
    await fs.rename(tempPath, filePath);
    return { success: true, remoteVersion: config.version };
  }

  async pull(configName: string): Promise<PullResult> {
    const filePath = this.configPath(configName);
    try {
      const content = await fs.readFile(filePath, 'utf-8');
      const config = JSON.parse(content) as RdcConfig;
      return { success: true, config };
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === 'ENOENT') {
        return { success: false, error: `Config "${configName}" not found in store` };
      }
      throw error;
    }
  }

  async list(): Promise<string[]> {
    try {
      const files = await fs.readdir(this.basePath);
      return files
        .filter((f) => f.endsWith('.json'))
        .map((f) => f.replace(/\.json$/, ''))
        .sort();
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === 'ENOENT') return [];
      throw error;
    }
  }

  async delete(configName: string): Promise<PushResult> {
    const filePath = this.configPath(configName);
    try {
      await fs.unlink(filePath);
      return { success: true };
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === 'ENOENT') {
        return { success: false, error: `Config "${configName}" not found in store` };
      }
      throw error;
    }
  }

  async verify(): Promise<boolean> {
    try {
      await fs.access(this.basePath);
      return true;
    } catch {
      return false;
    }
  }
}
