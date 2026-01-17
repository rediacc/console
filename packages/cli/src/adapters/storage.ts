import { promises as fs } from 'node:fs';
import { homedir } from 'node:os';
import { dirname, join } from 'node:path';
import lockfile from 'proper-lockfile';
import { type CliConfig, createEmptyConfig } from '../types/index.js';

const CONFIG_DIR = join(homedir(), '.rediacc');
const CONFIG_FILE = 'config.json';
const DEFAULT_CONFIG_PATH = join(CONFIG_DIR, CONFIG_FILE);

/**
 * Storage adapter for CLI configuration with file locking for multi-process safety.
 *
 * Uses proper-lockfile for cross-platform file locking:
 * - 45 second timeout (to accommodate long-running API operations)
 * - 50ms polling interval
 * - Atomic temp file + rename pattern for crash safety
 */
export class ConfigStorage {
  private cache: CliConfig | null = null;
  private lockDepth = 0; // Track re-entrant lock depth
  private readonly configPath: string;

  constructor(configPath: string = DEFAULT_CONFIG_PATH) {
    this.configPath = configPath;
  }

  private async ensureDirectory(): Promise<void> {
    const configDir = dirname(this.configPath);
    try {
      await fs.mkdir(configDir, { recursive: true, mode: 0o700 });
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== 'EEXIST') {
        throw error;
      }
    }
  }

  private async ensureConfigFile(): Promise<void> {
    await this.ensureDirectory();
    try {
      await fs.access(this.configPath);
    } catch {
      const emptyConfig = createEmptyConfig();
      await fs.writeFile(this.configPath, JSON.stringify(emptyConfig, null, 2), { mode: 0o600 });
    }
  }

  /**
   * Execute an operation with exclusive file lock.
   * Supports re-entrant calls - if we already hold the lock, skip acquisition.
   */
  private async withLock<T>(operation: () => Promise<T>): Promise<T> {
    await this.ensureConfigFile();

    // Re-entrant check: if we already hold the lock, just run the operation
    if (this.lockDepth > 0) {
      this.lockDepth++;
      try {
        return await operation();
      } finally {
        this.lockDepth--;
      }
    }

    // Acquire lock for the first time
    const release = await lockfile.lock(this.configPath, {
      stale: 45000,
      retries: {
        retries: 900,
        minTimeout: 50,
        maxTimeout: 50,
      },
    });

    this.lockDepth++;
    try {
      return await operation();
    } finally {
      this.lockDepth--;
      await release();
    }
  }

  private async loadUnlocked(): Promise<CliConfig> {
    try {
      const content = await fs.readFile(this.configPath, 'utf-8');
      const data = JSON.parse(content);
      return {
        contexts: data.contexts ?? {},
      };
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === 'ENOENT') {
        return createEmptyConfig();
      }
      throw error;
    }
  }

  /**
   * Load the configuration (uses cache if available).
   */
  async load(): Promise<CliConfig> {
    if (this.cache !== null) {
      return this.cache;
    }
    this.cache = await this.loadUnlocked();
    return this.cache;
  }

  /**
   * Save the configuration atomically.
   */
  private async saveUnlocked(config: CliConfig): Promise<void> {
    await this.ensureDirectory();

    const tempPath = `${this.configPath}.tmp.${process.pid}.${Date.now()}`;
    const content = JSON.stringify(config, null, 2);

    await fs.writeFile(tempPath, content, { mode: 0o600 });
    await fs.rename(tempPath, this.configPath);

    this.cache = config;
  }

  /**
   * Save the configuration with file locking.
   */
  async save(config: CliConfig): Promise<void> {
    await this.withLock(async () => {
      await this.saveUnlocked(config);
    });
  }

  /**
   * Update the configuration atomically with a callback.
   */
  async update(updater: (config: CliConfig) => CliConfig): Promise<CliConfig> {
    return this.withLock(async () => {
      this.cache = null;
      const config = await this.loadUnlocked();
      const updated = updater(config);
      await this.saveUnlocked(updated);
      return updated;
    });
  }

  /**
   * Clear the cache (useful for testing or forcing reload).
   */
  clearCache(): void {
    this.cache = null;
  }

  /**
   * Execute an operation with exclusive file lock, clearing cache first.
   * Use this for API operations that read-modify-write the token.
   *
   * The cache must be cleared because another process may have updated
   * the config file while we were waiting for the lock.
   */
  async withApiLock<T>(operation: () => Promise<T>): Promise<T> {
    return this.withLock(async () => {
      this.cache = null; // Force fresh read from file
      return operation();
    });
  }

  /**
   * Get the config file path.
   */
  getConfigPath(): string {
    return this.configPath;
  }
}

export const configStorage = new ConfigStorage();
