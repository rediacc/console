import { promises as fs } from 'node:fs';
import { homedir } from 'node:os';
import { dirname, join } from 'node:path';
import type { StoreEntry } from '../types/store.js';

const DEFAULT_STORES_PATH = join(homedir(), '.rediacc', '.credentials.json');

/**
 * Manages the store registry at ~/.rediacc/.credentials.json.
 * Stores are external backends (S3, local-file, bitwarden, git)
 * where config files can be synced.
 */
export class StoreRegistry {
  private readonly storesPath: string;
  private cache: StoreEntry[] | null = null;

  constructor(storesPath: string = DEFAULT_STORES_PATH) {
    this.storesPath = storesPath;
  }

  private async ensureDirectory(): Promise<void> {
    const dir = dirname(this.storesPath);
    try {
      await fs.mkdir(dir, { recursive: true, mode: 0o700 });
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== 'EEXIST') {
        throw error;
      }
    }
  }

  private async loadFromDisk(): Promise<StoreEntry[]> {
    try {
      const content = await fs.readFile(this.storesPath, 'utf-8');
      return JSON.parse(content) as StoreEntry[];
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === 'ENOENT') {
        return [];
      }
      throw error;
    }
  }

  private async saveToDisk(stores: StoreEntry[]): Promise<void> {
    await this.ensureDirectory();
    const tempPath = `${this.storesPath}.tmp.${process.pid}.${Date.now()}`;
    const content = JSON.stringify(stores, null, 2);
    await fs.writeFile(tempPath, content, { mode: 0o600 });
    await fs.rename(tempPath, this.storesPath);
    this.cache = stores;
  }

  /**
   * List all registered stores.
   */
  async list(): Promise<StoreEntry[]> {
    if (this.cache) return [...this.cache];
    const stores = await this.loadFromDisk();
    this.cache = stores;
    return [...stores];
  }

  /**
   * Get a store by name.
   */
  async get(name: string): Promise<StoreEntry | null> {
    const stores = await this.list();
    return stores.find((s) => s.name === name) ?? null;
  }

  /**
   * Add a new store. Throws if a store with the same name already exists.
   */
  async add(entry: StoreEntry): Promise<void> {
    const stores = await this.loadFromDisk();
    if (stores.some((s) => s.name === entry.name)) {
      throw new Error(`Store "${entry.name}" already exists`);
    }
    stores.push(entry);
    await this.saveToDisk(stores);
  }

  /**
   * Remove a store by name.
   */
  async remove(name: string): Promise<void> {
    const stores = await this.loadFromDisk();
    const index = stores.findIndex((s) => s.name === name);
    if (index === -1) {
      throw new Error(`Store "${name}" not found`);
    }
    stores.splice(index, 1);
    await this.saveToDisk(stores);
  }

  /**
   * Update an existing store entry.
   */
  async update(name: string, updates: Partial<Omit<StoreEntry, 'name'>>): Promise<void> {
    const stores = await this.loadFromDisk();
    const index = stores.findIndex((s) => s.name === name);
    if (index === -1) {
      throw new Error(`Store "${name}" not found`);
    }
    stores[index] = { ...stores[index], ...updates };
    await this.saveToDisk(stores);
  }

  /**
   * Clear cache (useful for testing).
   */
  clearCache(): void {
    this.cache = null;
  }
}

export const storeRegistry = new StoreRegistry();
