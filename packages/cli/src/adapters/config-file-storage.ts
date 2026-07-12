import { promises as fs } from 'node:fs';
import { basename, join } from 'node:path';
import {
  createEmptyRdcConfig,
  type MigrationContext,
  parseConfig,
  type RdcConfig,
  RdcConfigSchema,
  runMigrations,
  stringifyConfig,
} from '@rediacc/shared/config-schema';
import { getConfigDir } from '@rediacc/shared/paths';
import lockfile from 'proper-lockfile';
import {
  decryptConfigFields,
  encryptConfigFields,
  injectEncryptedStubs,
} from './config-field-crypto.js';
import { nodeCryptoProvider } from './crypto.js';

const CONFIG_DIR = getConfigDir();
const DEFAULT_CONFIG_NAME = 'rediacc';

/** Files in config dir that are not config files */
const EXCLUDED_FILES = new Set(['update-state.json', 'server.json', 'api-token.json']);

/**
 * True for JSON files the CLI writes into the config dir that are NOT rdc
 * configs: the updater state, the subscription server pick (server.json),
 * and subscription device tokens (api-token.json / api-token-<config>.json,
 * written by services/subscription-auth.ts).
 */
function isReservedFile(fileName: string): boolean {
  return EXCLUDED_FILES.has(fileName) || fileName.startsWith('api-token-');
}

function isMasterPassword(config: RdcConfig): boolean {
  return config.encryption?.mode === 'master-password';
}

/**
 * Storage adapter for per-file CLI configuration with file locking.
 *
 * Each config is a separate JSON file in the config dir (e.g., rediacc.json, production.json).
 * Uses proper-lockfile for cross-platform file locking with atomic temp+rename writes.
 *
 * Encryption-at-rest (v3) is a transform owned entirely by this layer: mutating
 * reads (update/updateState) decrypt the on-disk config to plaintext, hand the
 * updater plaintext, and re-encrypt per field on save. Callers never see blobs,
 * and there is no second plaintext path a persist can clobber.
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
   * Resolve the master password for encrypt/decrypt transforms. Prefers the
   * REDIACC_MASTER_PASSWORD env, else the interactive resolver (lazy import to
   * avoid an adapters→services module cycle at eval time).
   */
  private async requirePassword(): Promise<string> {
    if (process.env.REDIACC_MASTER_PASSWORD) return process.env.REDIACC_MASTER_PASSWORD;
    const { requireMasterPassword } = await import('../services/core/master-password.js');
    return requireMasterPassword();
  }

  private async encryptConfig(config: RdcConfig): Promise<RdcConfig> {
    if (!isMasterPassword(config)) return config;
    return encryptConfigFields(config, await this.requirePassword());
  }

  private async decryptConfig(config: RdcConfig): Promise<RdcConfig> {
    if (!isMasterPassword(config)) return config;
    const fields = config.encryption?.encryptedFields;
    if (!fields || Object.keys(fields).length === 0) return config;
    return decryptConfigFields(config, await this.requirePassword());
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
      await fs.writeFile(configPath, stringifyConfig(emptyConfig), { mode: 0o600 });
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

  private migrationContext(): MigrationContext {
    return {
      getMasterPassword: () => this.requirePassword(),
      // The v2 compound-blob unpack needs AES-GCM. The schema package is
      // runtime-portable and carries no crypto provider, so the host injects one.
      decryptLegacyBlob: (data, password) => nodeCryptoProvider.decrypt(data, password),
    };
  }

  private async loadUnlocked(name: string): Promise<RdcConfig> {
    const configPath = this.getPath(name);
    let content: string;
    try {
      content = await fs.readFile(configPath, 'utf-8');
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === 'ENOENT') {
        return createEmptyRdcConfig();
      }
      throw error;
    }

    const raw = JSON.parse(content) as unknown;
    const migration = await runMigrations(raw, this.migrationContext());
    // Hydrate encrypted leaves with type-valid stubs so the strict parse of the
    // at-rest form succeeds without prompting for the master password. Sensitive
    // values are decrypted lazily (loadDecrypted / update), never at load.
    const hydrated = injectEncryptedStubs(migration.config as RdcConfig);
    const config = parseConfig(RdcConfigSchema, hydrated, `config "${name}"`);

    // Persist the upgraded shape so future loads skip the migration step.
    // Best-effort: a read-only filesystem or lock failure must not break load.
    if (migration.migrated) {
      try {
        await this.withLock(name, () => this.saveUnlocked(config, name));
      } catch {
        // Ignore — caller still gets the in-memory upgraded config.
      }
    }
    return config;
  }

  /**
   * Load a config file by name (uses cache if available).
   * Returns the on-disk (at-rest) shape: encrypted leaves live in
   * `encryption.encryptedFields`, not the plaintext tree. Public-field reads
   * never prompt for the master password.
   */
  async load(name: string = DEFAULT_CONFIG_NAME): Promise<RdcConfig> {
    const cached = this.cache.get(name);
    if (cached) return cached;

    const config = await this.loadUnlocked(name);
    this.cache.set(name, config);
    return config;
  }

  /**
   * Load a config and decrypt every encrypted-at-rest leaf into the plaintext
   * tree. Prompts for the master password when the config is encrypted; use
   * only where a sensitive field is actually needed.
   */
  async loadDecrypted(name: string = DEFAULT_CONFIG_NAME): Promise<RdcConfig> {
    const config = await this.load(name);
    return this.decryptConfig(config);
  }

  /**
   * Save a config atomically. Encrypts per field when in master-password mode.
   * Bumps the version counter unless `bumpVersion` is false (state writes).
   */
  private async saveUnlocked(config: RdcConfig, name: string, bumpVersion = true): Promise<void> {
    await this.ensureDirectory();
    await this.createBackup(name);
    const configPath = this.getPath(name);

    const versioned: RdcConfig = bumpVersion ? { ...config, version: config.version + 1 } : config;
    const encrypted = await this.encryptConfig(versioned);

    const tempPath = `${configPath}.tmp.${process.pid}.${Date.now()}`;
    const content = stringifyConfig(encrypted);

    await fs.writeFile(tempPath, content, { mode: 0o600 });
    await fs.rename(tempPath, configPath);

    this.cache.set(name, encrypted);
  }

  /**
   * Save a config with file locking. The config passed in must be plaintext
   * (encrypted leaves are produced by this layer, not by callers).
   */
  async save(config: RdcConfig, name: string = DEFAULT_CONFIG_NAME): Promise<void> {
    await this.withLock(name, async () => {
      await this.saveUnlocked(config, name);
    });
  }

  private async mutate(
    name: string,
    updater: (config: RdcConfig) => RdcConfig,
    bumpVersion: boolean
  ): Promise<RdcConfig> {
    return this.withLock(name, async () => {
      this.cache.delete(name);
      const raw = await this.loadUnlocked(name);
      const plain = await this.decryptConfig(raw);
      const updated = updater(plain);
      await this.saveUnlocked(updated, name, bumpVersion);
      return this.cache.get(name)!;
    });
  }

  /**
   * Update the SPEC half of a config (declared intent). Bumps the version
   * counter. Reads the latest from disk, decrypts, applies the updater, and
   * re-encrypts per field on save.
   */
  async update(name: string, updater: (config: RdcConfig) => RdcConfig): Promise<RdcConfig> {
    return this.mutate(name, updater, true);
  }

  /**
   * Update the STATE half of a config (runtime status). Does NOT bump the
   * version counter — status churn must not create optimistic-version
   * conflicts or audit noise (spec 04 §1.3 property 1). The writer is
   * responsible for touching only `state.*`.
   */
  async updateState(name: string, updater: (config: RdcConfig) => RdcConfig): Promise<RdcConfig> {
    return this.mutate(name, updater, false);
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
    const content = stringifyConfig(config);
    await fs.writeFile(configPath, content, { mode: 0o600 });
    this.cache.set(name, config);
    return config;
  }

  /**
   * List available config names (*.json in config dir, excluding system files).
   */
  async list(): Promise<string[]> {
    await this.ensureDirectory();
    try {
      const files = await fs.readdir(this.configDir);
      return files
        .filter((f) => f.endsWith('.json') && !isReservedFile(f))
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
