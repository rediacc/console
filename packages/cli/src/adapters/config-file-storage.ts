import { promises as fs } from 'node:fs';
import { homedir } from 'node:os';
import { basename, join } from 'node:path';
import lockfile from 'proper-lockfile';
import { type RdcConfig, createEmptyRdcConfig } from '../types/index.js';

const CONFIG_DIR = join(homedir(), '.rediacc');
const DEFAULT_CONFIG_NAME = 'rediacc';

/** Files in ~/.rediacc/ that are not config files */
const EXCLUDED_FILES = new Set(['.credentials.json', 'update-state.json']);

/**
 * Storage adapter for per-file CLI configuration with file locking.
 *
 * Each config is a separate JSON file in ~/.rediacc/ (e.g., rediacc.json, production.json).
 * Uses proper-lockfile for cross-platform file locking with atomic temp+rename writes.
 */
export class ConfigFileStorage {
  private readonly cache = new Map<string, RdcConfig>();
  private readonly lockDepths = new Map<string, number>();
  private readonly configDir: string;

  constructor(configDir: string = CONFIG_DIR) {
    this.configDir = configDir;
  }

  private getPath(name: string): string {
    return join(this.configDir, `${name}.json`);
  }

  private getBackupPath(name: string): string {
    return `${this.getPath(name)}.bak`;
  }

  /**
   * Copy the current config file to a .bak backup.
   * Skips silently if the source file does not exist (first-ever write).
   */
  private async createBackup(name: string): Promise<void> {
    const configPath = this.getPath(name);
    const backupPath = this.getBackupPath(name);
    try {
      await fs.copyFile(configPath, backupPath);
      await fs.chmod(backupPath, 0o600);
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === 'ENOENT') {
        return;
      }
      throw error;
    }
  }

  private async ensureDirectory(): Promise<void> {
    try {
      await fs.mkdir(this.configDir, { recursive: true, mode: 0o700 });
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== 'EEXIST') {
        throw error;
      }
    }
  }

  private async ensureConfigFile(name: string): Promise<void> {
    await this.ensureDirectory();
    const configPath = this.getPath(name);
    try {
      await fs.access(configPath);
    } catch {
      const emptyConfig = createEmptyRdcConfig();
      await fs.writeFile(configPath, JSON.stringify(emptyConfig, null, 2), { mode: 0o600 });
    }
  }

  /**
   * Execute an operation with exclusive file lock.
   * Supports re-entrant calls — if we already hold the lock, skip acquisition.
   */
  private async withLock<T>(name: string, operation: () => Promise<T>): Promise<T> {
    await this.ensureConfigFile(name);
    const configPath = this.getPath(name);

    const depth = this.lockDepths.get(name) ?? 0;

    // Re-entrant: already hold the lock
    if (depth > 0) {
      this.lockDepths.set(name, depth + 1);
      try {
        return await operation();
      } finally {
        this.lockDepths.set(name, depth);
      }
    }

    // Acquire lock
    const release = await lockfile.lock(configPath, {
      stale: 45000,
      retries: {
        retries: 900,
        minTimeout: 50,
        maxTimeout: 50,
      },
    });

    this.lockDepths.set(name, 1);
    try {
      return await operation();
    } finally {
      this.lockDepths.set(name, 0);
      await release();
    }
  }

  private async loadUnlocked(name: string): Promise<RdcConfig> {
    const configPath = this.getPath(name);
    try {
      const content = await fs.readFile(configPath, 'utf-8');
      return JSON.parse(content) as RdcConfig;
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === 'ENOENT') {
        return createEmptyRdcConfig();
      }
      throw error;
    }
  }

  /**
   * Load a config file by name (uses cache if available).
   * Defaults to "rediacc" if no name is provided.
   */
  async load(name: string = DEFAULT_CONFIG_NAME): Promise<RdcConfig> {
    const cached = this.cache.get(name);
    if (cached) return cached;

    const config = await this.loadUnlocked(name);
    this.cache.set(name, config);
    return config;
  }

  /**
   * Save a config atomically. Increments the version number.
   */
  private async saveUnlocked(config: RdcConfig, name: string): Promise<void> {
    await this.ensureDirectory();
    await this.createBackup(name);
    const configPath = this.getPath(name);

    const toWrite: RdcConfig = {
      ...config,
      version: config.version + 1,
    };

    const tempPath = `${configPath}.tmp.${process.pid}.${Date.now()}`;
    const content = JSON.stringify(toWrite, null, 2);

    await fs.writeFile(tempPath, content, { mode: 0o600 });
    await fs.rename(tempPath, configPath);

    this.cache.set(name, toWrite);
  }

  /**
   * Save a config with file locking.
   */
  async save(config: RdcConfig, name: string = DEFAULT_CONFIG_NAME): Promise<void> {
    await this.withLock(name, async () => {
      await this.saveUnlocked(config, name);
    });
  }

  /**
   * Update a config atomically with a callback.
   * Reads the latest version from disk, applies the updater, increments version, saves.
   */
  async update(name: string, updater: (config: RdcConfig) => RdcConfig): Promise<RdcConfig> {
    return this.withLock(name, async () => {
      this.cache.delete(name);
      const config = await this.loadUnlocked(name);
      const updated = updater(config);
      await this.saveUnlocked(updated, name);
      return { ...updated, version: updated.version + 1 };
    });
  }

  /**
   * Create a new config file with a fresh UUID and version 1.
   * Throws if a config with this name already exists.
   */
  async init(name: string = DEFAULT_CONFIG_NAME): Promise<RdcConfig> {
    await this.ensureDirectory();
    const configPath = this.getPath(name);

    try {
      await fs.access(configPath);
      throw new Error(`Config "${name}" already exists`);
    } catch (error) {
      if ((error as Error).message.includes('already exists')) throw error;
      // File doesn't exist — good, create it
    }

    const config = createEmptyRdcConfig();
    const content = JSON.stringify(config, null, 2);
    await fs.writeFile(configPath, content, { mode: 0o600 });
    this.cache.set(name, config);
    return config;
  }

  /**
   * List available config names (files in ~/.rediacc/*.json, excluding system files).
   */
  async list(): Promise<string[]> {
    await this.ensureDirectory();
    try {
      const files = await fs.readdir(this.configDir);
      return files
        .filter((f) => f.endsWith('.json') && !EXCLUDED_FILES.has(f))
        .map((f) => basename(f, '.json'))
        .sort();
    } catch {
      return [];
    }
  }

  /**
   * Load the default config, creating it if it doesn't exist.
   * Only applies to the default config name ("rediacc").
   */
  async getOrCreateDefault(): Promise<RdcConfig> {
    await this.ensureConfigFile(DEFAULT_CONFIG_NAME);
    return this.load(DEFAULT_CONFIG_NAME);
  }

  /**
   * Check if a config file exists.
   */
  async exists(name: string): Promise<boolean> {
    const configPath = this.getPath(name);
    try {
      await fs.access(configPath);
      return true;
    } catch {
      return false;
    }
  }

  /**
   * Delete a config file and its backup.
   */
  async delete(name: string): Promise<void> {
    if (name === DEFAULT_CONFIG_NAME) {
      throw new Error('Cannot delete the default config "rediacc"');
    }
    const configPath = this.getPath(name);
    try {
      await fs.unlink(configPath);
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== 'ENOENT') {
        throw error;
      }
      throw new Error(`Config "${name}" not found`);
    }
    try {
      await fs.unlink(this.getBackupPath(name));
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== 'ENOENT') {
        throw error;
      }
    }
    this.cache.delete(name);
  }

  /**
   * Recover a config from its .bak backup file.
   * Returns the recovered config, or null if no backup exists.
   */
  async recover(name: string = DEFAULT_CONFIG_NAME): Promise<RdcConfig | null> {
    const backupPath = this.getBackupPath(name);
    try {
      await fs.access(backupPath);
    } catch {
      return null;
    }

    return this.withLock(name, async () => {
      const configPath = this.getPath(name);
      await fs.copyFile(backupPath, configPath);
      await fs.chmod(configPath, 0o600);
      this.cache.delete(name);
      return this.loadUnlocked(name);
    });
  }

  /**
   * Get metadata about a backup file.
   * Returns null if no backup exists.
   */
  async getBackupInfo(
    name: string = DEFAULT_CONFIG_NAME
  ): Promise<{ path: string; version: number; id: string; modifiedAt: Date } | null> {
    const backupPath = this.getBackupPath(name);
    try {
      const stat = await fs.stat(backupPath);
      const content = await fs.readFile(backupPath, 'utf-8');
      const config = JSON.parse(content) as RdcConfig;
      return {
        path: backupPath,
        version: config.version,
        id: config.id,
        modifiedAt: stat.mtime,
      };
    } catch {
      return null;
    }
  }

  /**
   * Execute an operation with exclusive file lock, clearing cache first.
   * Use for operations that read-modify-write and need a fresh read.
   */
  async withApiLock<T>(name: string, operation: () => Promise<T>): Promise<T> {
    return this.withLock(name, async () => {
      this.cache.delete(name);
      return operation();
    });
  }

  /**
   * Get the full path for a config file.
   */
  getConfigPath(name: string = DEFAULT_CONFIG_NAME): string {
    return this.getPath(name);
  }

  /**
   * Get the config directory path.
   */
  getConfigDir(): string {
    return this.configDir;
  }

  /**
   * Clear the cache (useful for testing or forcing reload).
   */
  clearCache(): void {
    this.cache.clear();
  }
}

export const configFileStorage = new ConfigFileStorage();
