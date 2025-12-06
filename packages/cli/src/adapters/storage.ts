import { promises as fs } from 'node:fs';
import { join } from 'node:path';
import { homedir } from 'node:os';
import type { IStorageProvider } from '../types/index.js';

const CONFIG_DIR = join(homedir(), '.rediacc');
const CONFIG_FILE = 'config.json';
const CONFIG_PATH = join(CONFIG_DIR, CONFIG_FILE);

interface StorageData {
  [key: string]: string;
}

class NodeStorageAdapter implements IStorageProvider {
  private cache: StorageData | null = null;
  private initialized = false;

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

  private async loadData(): Promise<StorageData> {
    if (this.cache !== null) {
      return this.cache;
    }

    try {
      const content = await fs.readFile(CONFIG_PATH, 'utf-8');
      this.cache = JSON.parse(content);
      return this.cache!;
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === 'ENOENT') {
        this.cache = {};
        return this.cache;
      }
      throw error;
    }
  }

  private async saveData(data: StorageData): Promise<void> {
    await this.ensureDirectory();

    // Write to temp file first for atomic operation
    const tempPath = `${CONFIG_PATH}.tmp`;
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
    const data = await this.loadData();
    data[key] = value;
    await this.saveData(data);
  }

  async removeItem(key: string): Promise<void> {
    const data = await this.loadData();
    delete data[key];
    await this.saveData(data);
  }

  async clear(): Promise<void> {
    await this.saveData({});
  }

  // Additional methods for CLI convenience
  async getAll(): Promise<StorageData> {
    return this.loadData();
  }

  async setMultiple(items: Record<string, string>): Promise<void> {
    const data = await this.loadData();
    Object.assign(data, items);
    await this.saveData(data);
  }

  getConfigPath(): string {
    return CONFIG_PATH;
  }
}

export const nodeStorageAdapter = new NodeStorageAdapter();
