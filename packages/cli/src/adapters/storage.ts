import { promises as fs } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import lockfile from 'proper-lockfile';
import type { CliConfig } from '../types/index.js';
import { createEmptyConfig } from '../types/index.js';

const CONFIG_DIR = join(homedir(), '.rediacc');
const CONFIG_FILE = 'config.json';
const CONFIG_PATH = join(CONFIG_DIR, CONFIG_FILE);

/**
 * Storage adapter for CLI configuration with file locking for multi-process safety.
 *
 * Uses proper-lockfile for cross-platform file locking:
 * - 10 second timeout
 * - 50ms polling interval
 * - Atomic temp file + rename pattern for crash safety
 */
class ConfigStorage {
  private cache: CliConfig | null = null;

  private async ensureDirectory(): Promise<void> {
    try {
      await fs.mkdir(CONFIG_DIR, { recursive: true, mode: 0o700 });
    } catch (error) {
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
      const emptyConfig = createEmptyConfig();
      await fs.writeFile(CONFIG_PATH, JSON.stringify(emptyConfig, null, 2), { mode: 0o600 });
    }
  }

  /**
   * Execute an operation with exclusive file lock.
   */
  private async withLock<T>(operation: () => Promise<T>): Promise<T> {
    await this.ensureConfigFile();

    const release = await lockfile.lock(CONFIG_PATH, {
      stale: 10000,
      retries: {
        retries: 200,
        minTimeout: 50,
        maxTimeout: 50,
      },
    });

    try {
      return await operation();
    } finally {
      await release();
    }
  }

  private async loadUnlocked(): Promise<CliConfig> {
    try {
      const content = await fs.readFile(CONFIG_PATH, 'utf-8');
      const data = JSON.parse(content);
      return {
        currentContext: data.currentContext ?? '',
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

    const tempPath = `${CONFIG_PATH}.tmp.${process.pid}.${Date.now()}`;
    const content = JSON.stringify(config, null, 2);

    await fs.writeFile(tempPath, content, { mode: 0o600 });
    await fs.rename(tempPath, CONFIG_PATH);

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
   * Get the config file path.
   */
  getConfigPath(): string {
    return CONFIG_PATH;
  }
}

export const configStorage = new ConfigStorage();
