import { promises as fs } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import lockfile from 'proper-lockfile';
import type { IStorageProvider } from '../types/index.js';

const CONFIG_DIR = join(homedir(), '.rediacc');
const CONFIG_FILE = 'config.json';
const CONFIG_PATH = join(CONFIG_DIR, CONFIG_FILE);

interface StorageData {
  [key: string]: string;
}

/**
 * Node.js storage adapter with file locking for multi-process safety.
 * Compatible with desktop CLI's token storage mechanism.
 *
 * Uses proper-lockfile for cross-platform file locking:
 * - 10 second timeout (matches desktop CLI's config.py APIMutex)
 * - 50ms polling interval
 * - Atomic temp file + rename pattern for crash safety
 */
class NodeStorageAdapter implements IStorageProvider {
  private cache: StorageData | null = null;

  private async ensureDirectory(): Promise<void> {
    try {
      await fs.mkdir(CONFIG_DIR, { recursive: true, mode: 0o700 });
    } catch (error) {
      // Directory may already exist
      if ((error as NodeJS.ErrnoException).code !== 'EEXIST') {
        throw error;
      }
    }
  }

  private async ensureConfigFile(): Promise<void> {
    await this.ensureDirectory();
    try {
      await fs.access(CONFIG_PATH);
    } catch {
      // Create empty config file if it doesn't exist (lockfile needs it)
      await fs.writeFile(CONFIG_PATH, '{}', { mode: 0o600 });
    }
  }

  /**
   * Execute an operation with exclusive file lock.
   * Matches desktop CLI's APIMutex behavior:
   * - 10 second timeout
   * - 50ms polling interval
   */
  private async withLock<T>(operation: () => Promise<T>): Promise<T> {
    await this.ensureConfigFile();

    const release = await lockfile.lock(CONFIG_PATH, {
      stale: 10000, // Consider lock stale after 10s (matches desktop CLI)
      retries: {
        retries: 200, // Retry for ~10 seconds (200 * 50ms)
        minTimeout: 50, // 50ms between retries (matches desktop CLI)
        maxTimeout: 50,
      },
    });

    try {
      return await operation();
    } finally {
      await release();
    }
  }

  private async loadDataUnlocked(): Promise<StorageData> {
    try {
      const content = await fs.readFile(CONFIG_PATH, 'utf-8');
      return JSON.parse(content);
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === 'ENOENT') {
        return {};
      }
      throw error;
    }
  }

  private async loadData(): Promise<StorageData> {
    if (this.cache !== null) {
      return this.cache;
    }

    this.cache = await this.loadDataUnlocked();
    return this.cache;
  }

  private async saveData(data: StorageData): Promise<void> {
    await this.ensureDirectory();

    // Write to temp file first for atomic operation (matches desktop CLI pattern)
    const tempPath = `${CONFIG_PATH}.tmp.${process.pid}.${Date.now()}`;
    const content = JSON.stringify(data, null, 2);

    await fs.writeFile(tempPath, content, { mode: 0o600 });
    await fs.rename(tempPath, CONFIG_PATH);

    this.cache = data;
  }

  async getItem(key: string): Promise<string | null> {
    const data = await this.loadData();
    return data[key] ?? null;
  }

  async setItem(key: string, value: string): Promise<void> {
    await this.withLock(async () => {
      // Re-read inside lock to avoid race conditions
      this.cache = null;
      const data = await this.loadData();
      data[key] = value;
      await this.saveData(data);
    });
  }

  async removeItem(key: string): Promise<void> {
    await this.withLock(async () => {
      // Re-read inside lock to avoid race conditions
      this.cache = null;
      const data = await this.loadData();
      delete data[key];
      await this.saveData(data);
    });
  }

  async clear(): Promise<void> {
    await this.withLock(async () => {
      this.cache = null;
      await this.saveData({});
    });
  }

  // Additional methods for CLI convenience
  async getAll(): Promise<StorageData> {
    return this.loadData();
  }

  async setMultiple(items: Record<string, string>): Promise<void> {
    await this.withLock(async () => {
      // Re-read inside lock to avoid race conditions
      this.cache = null;
      const data = await this.loadData();
      Object.assign(data, items);
      await this.saveData(data);
    });
  }

  getConfigPath(): string {
    return CONFIG_PATH;
  }
}

export const nodeStorageAdapter = new NodeStorageAdapter();
