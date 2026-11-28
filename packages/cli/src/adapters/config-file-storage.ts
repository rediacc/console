import { AsyncLocalStorage } from 'node:async_hooks';
import { randomUUID } from 'node:crypto';
import { promises as fs } from 'node:fs';
import { basename, join } from 'node:path';
import {
  createEmptyRdcConfig,
  hasRemoteConfig,
  isSealed,
  type MigrationContext,
  parseConfig,
  type RdcConfig,
  RdcConfigSchema,
  runMigrations,
  stringifyConfig,
  usesMasterPassword,
} from '@rediacc/shared/config-schema';
import { getConfigDir } from '@rediacc/shared/paths';
import lockfile from 'proper-lockfile';
import { getSubscriptionTokenFile } from '../services/account/subscription-auth.js';
import { replaySavedEdit } from '../services/core/config-delta.js';
import { currentRequestConfig } from '../services/core/request-context.js';
import { parseJsonText } from '../utils/json-text.js';
import {
  decryptConfigFields,
  encryptConfigFields,
  injectEncryptedStubs,
} from './config-field-crypto.js';
import {
  encryptionOfText,
  hasLegacyBlobs,
  hasUnopenedBlobs,
  isReservedFile,
  refuseInRequestScope,
  sealIdentity,
  sealUpgrade,
  upgradeVerifier,
  writeScoped,
} from './config-file-ops.js';
import { dropKey, SealKeyLostError } from './config-seal-key.js';
import { nodeCryptoProvider } from './crypto.js';

export { resetFileStoreRefusalNotice } from './config-file-ops.js';

const CONFIG_DIR = getConfigDir();
const DEFAULT_CONFIG_NAME = 'rediacc';

/**
 * Called when a sealed config's keyring key is lost (D7): services/config/seal-recovery.ts pulls the
 * config from its store and re-seals it under a new key. The read or write that hit the loss runs
 * once more after the handler returns; a second loss propagates.
 */
export type SealKeyLostHandler = (name: string, error: SealKeyLostError) => Promise<void>;

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
/** Pushes a state edit of a remote-enabled config to its store (registered by the config service). */
export type RemoteStateWriter = (
  name: string,
  updater: (config: RdcConfig) => RdcConfig
) => Promise<RdcConfig>;

export class ConfigFileStorage {
  private readonly cache = new Map<string, RdcConfig>();
  private remoteStateWriter: RemoteStateWriter | null = null;
  private sealKeyLostHandler: SealKeyLostHandler | null = null;
  /**
   * Config names whose file lock the CURRENT async call chain holds. Re-entrancy is a property of
   * the call chain, not of the instance: a per-name counter on the instance made every concurrent
   * caller that arrived while another held the lock look re-entrant, so it skipped the lock and
   * ran its read-modify-write unprotected (lost writes under concurrent update()).
   */
  private readonly heldLocks = new AsyncLocalStorage<ReadonlySet<string>>();
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
   * The master password of `config`, checked against its verifier (process cache, then
   * REDIACC_MASTER_PASSWORD, then a prompt). Lazy import, to avoid an adapters-to-services module
   * cycle at eval time.
   */
  private async requirePassword(config: RdcConfig): Promise<string> {
    const { requireMasterPassword } = await import('../services/core/master-password.js');
    return requireMasterPassword(config);
  }

  /** The password a seal transform of `config` needs, or undefined when its key has no password part. */
  private passwordFor(config: RdcConfig): Promise<string | undefined> {
    if (usesMasterPassword(config.encryption?.mode) || hasLegacyBlobs(config)) {
      return this.requirePassword(config);
    }
    return Promise.resolve(undefined);
  }

  private async encryptConfig(config: RdcConfig): Promise<RdcConfig> {
    if (!isSealed(config)) return config;
    return encryptConfigFields(config, await this.passwordFor(config));
  }

  private async decryptConfig(config: RdcConfig): Promise<RdcConfig> {
    if (!isSealed(config) || !hasUnopenedBlobs(config)) return config;
    return decryptConfigFields(config, await this.passwordFor(config));
  }

  /**
   * Run `operation`; when it hits a lost seal key and a handler is registered, let the handler
   * recover (D7) and run `operation` once more. Without a handler the error propagates.
   */
  private async withSealRecovery<T>(name: string, operation: () => Promise<T>): Promise<T> {
    try {
      return await operation();
    } catch (error) {
      const handler = this.sealKeyLostHandler;
      if (!(error instanceof SealKeyLostError) || !handler) throw error;
      const recovered: Promise<void> = handler(name, error);
      await recovered;
      this.cache.delete(name);
      return operation();
    }
  }

  /**
   * Register the D7 recovery (services/config/seal-recovery.ts). When a write hit the loss, the
   * handler runs inside that write's file lock, so its own cache write takes the lock re-entrantly.
   */
  setSealKeyLostHandler(handler: SealKeyLostHandler | null): void {
    this.sealKeyLostHandler = handler;
  }

  /**
   * Copy the current config file to a .bak backup and return the text it held; null when there
   * is no file yet (first-ever write).
   */
  private async createBackup(name: string): Promise<string | null> {
    const backupPath = this.getBackupPath(name);
    let previous: string;
    try {
      previous = await fs.readFile(this.getPath(name), 'utf-8');
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === 'ENOENT') {
        return null;
      }
      throw error;
    }
    await this.writeBackup(backupPath, previous);
    return previous;
  }

  private async writeBackup(backupPath: string, content: string): Promise<void> {
    await fs.writeFile(backupPath, content, { mode: 0o600 });
    await fs.chmod(backupPath, 0o600);
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
      try {
        // 'wx': never truncate a file a concurrent caller created (and may already have written to) since the access check.
        await fs.writeFile(configPath, stringifyConfig(emptyConfig), { mode: 0o600, flag: 'wx' });
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code !== 'EEXIST') throw error;
      }
    }
  }

  /**
   * Execute an operation with exclusive file lock.
   * Supports re-entrant calls, if we already hold the lock, skip acquisition.
   */
  private async withLock<T>(
    name: string,
    operation: () => Promise<T>,
    opts: { createIfMissing?: boolean } = {}
  ): Promise<T> {
    if (opts.createIfMissing === false) {
      // State-write path: never resurrect a removed config (see updateState).
      await fs.access(this.getPath(name));
    } else {
      await this.ensureConfigFile(name);
    }
    const configPath = this.getPath(name);

    // Re-entrant: this call chain already holds the lock
    if (this.heldLocks.getStore()?.has(name)) {
      return operation();
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

    try {
      const held = new Set(this.heldLocks.getStore());
      held.add(name);
      return await this.heldLocks.run(held, operation);
    } finally {
      await release();
    }
  }

  private migrationContext(): MigrationContext {
    return {
      // A v2-era file has no v2 verifier to check against; the blob's own decrypt rejects a wrong password.
      getMasterPassword: async () => {
        const { resolveUncheckedMasterPassword } = await import(
          '../services/core/master-password.js'
        );
        return resolveUncheckedMasterPassword();
      },
      // The v2 compound-blob unpack needs AES-GCM. The schema package is runtime-portable and carries no crypto provider, so the host injects one.
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

    const { config, migrated } = await this.parseAtRest(content, name);

    // Persist the upgraded shape so future loads skip the migration step. Best-effort: a read-only filesystem or lock failure must not break load.
    if (migrated) {
      try {
        await this.withLock(name, () => this.persistMigration(name));
      } catch {
        // Ignore, caller still gets the in-memory upgraded config.
      }
    }
    return config;
  }

  /** Migrate and strictly parse the at-rest text of a config file. */
  private async parseAtRest(
    content: string,
    name: string
  ): Promise<{ config: RdcConfig; migrated: boolean }> {
    const raw = parseJsonText(content) as unknown;
    const migration = await runMigrations(raw, this.migrationContext());
    // Hydrate encrypted leaves with type-valid stubs so the strict parse of the at-rest form succeeds without prompting for the master password. Sensitive values are decrypted lazily (loadDecrypted / update), never at load.
    const hydrated = injectEncryptedStubs(migration.config as RdcConfig);
    return {
      config: parseConfig(RdcConfigSchema, hydrated, `config "${name}"`),
      migrated: migration.migrated,
    };
  }

  /**
   * Write the migrated shape of a config, under the lock. The file is read again HERE, not reused from the unlocked load that noticed the old schema: another process may have written it in between, and saving the earlier read would put its stale content back.
   */
  private async persistMigration(name: string): Promise<void> {
    const { config, migrated } = await this.parseAtRest(
      await fs.readFile(this.getPath(name), 'utf-8'),
      name
    );
    // A sealed config's at-rest copy carries blobs that only a key or a password can re-seal; a public load must touch neither (D4), so its migrated shape lands with the next decrypted write instead.
    if (migrated && !isSealed(config)) await this.saveUnlocked(config, name, true, false);
  }

  /**
   * Load a config file by name (uses cache if available).
   * Returns the on-disk (at-rest) shape: encrypted leaves live in
   * `encryption.encryptedFields`, not the plaintext tree. Public-field reads
   * never prompt for the master password.
   */
  async load(name: string = DEFAULT_CONFIG_NAME): Promise<RdcConfig> {
    // Inside a request-scoped dispatch the granted config IS the config; a file of the same name (or none, on a container) must not be read in its place.
    const scoped = currentRequestConfig();
    if (scoped) return scoped.config;

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
    // Already plaintext: the executor decrypted it for the session.
    const scoped = currentRequestConfig();
    if (scoped) return scoped.config;

    const decrypted = await this.withSealRecovery(name, async () =>
      this.decryptConfig(await this.load(name))
    );
    await this.persistVerifierUpgrade(name, decrypted);
    return decrypted;
  }

  /**
   * After a read that verified a legacy master-password verifier, write it back as v2 under the lock
   * (D8). Inside a held lock the enclosing write rewrites it. Best-effort: a read-only filesystem
   * must not fail the read.
   */
  private async persistVerifierUpgrade(name: string, config: RdcConfig): Promise<void> {
    const verifier = config.credentials?.masterPasswordVerifier;
    if (!verifier || !usesMasterPassword(config.encryption?.mode)) return;
    if (this.heldLocks.getStore()?.has(name)) return;
    const mp = await import('../services/core/master-password.js');
    if (!mp.isLegacyVerifier(verifier) || !mp.isVerifiedMasterPassword(config.id, verifier)) return;
    try {
      await this.mutate(name, (current) => current, false, { createIfMissing: false });
    } catch {
      // The next write rewrites it.
    }
  }

  /**
   * Save a config atomically. Seals per field in every sealed mode, and on a remote-enabled config
   * upgrades to a keyring seal first (D5) unless `transform` is false (the migration persist, which
   * must touch no key and prompt for nothing). Bumps the version counter unless `bumpVersion` is
   * false (state writes).
   *
   * Order: a newly minted keyring key is stored BEFORE the temp-file rename and deleted when the
   * write does not land, so the file never names a key secure storage lacks. When the seal identity
   * changes (seal, re-seal, unseal, password change), `.bak` is overwritten with the new bytes.
   */
  private async saveUnlocked(
    config: RdcConfig,
    name: string,
    bumpVersion = true,
    transform = true
  ): Promise<void> {
    await this.ensureDirectory();
    const previousText = await this.createBackup(name);
    const previous = previousText === null ? undefined : encryptionOfText(previousText);
    const configPath = this.getPath(name);

    const versioned: RdcConfig = bumpVersion ? { ...config, version: config.version + 1 } : config;
    const upgraded = transform
      ? await sealUpgrade(versioned, name, previous)
      : { config: versioned };

    let encrypted: RdcConfig;
    let content: string;
    try {
      const prepared = transform
        ? await upgradeVerifier(upgraded.config, (c) => this.requirePassword(c))
        : upgraded.config;
      encrypted = await this.encryptConfig(prepared);

      // `pid.Date.now()` alone can collide: two saveUnlocked calls for the SAME name that land in the same millisecond compute the identical tempPath. Whichever renames second then hits ENOENT, because the first already moved that path away (observed live: run 30512465488, storage.test.ts's "should not corrupt file under concurrent writes", a lock-window race under CI-runner load that did not reproduce under local stress testing). The random suffix makes every tempPath unique regardless of timing.
      const tempPath = `${configPath}.tmp.${process.pid}.${Date.now()}.${randomUUID()}`;
      content = stringifyConfig(encrypted);

      await fs.writeFile(tempPath, content, { mode: 0o600 });
      await fs.rename(tempPath, configPath);
    } catch (error) {
      if (upgraded.minted) await dropKey(upgraded.minted).catch(() => undefined);
      throw error;
    }

    if (previousText !== null && sealIdentity(previous) !== sealIdentity(encrypted.encryption)) {
      await this.writeBackup(this.getBackupPath(name), content);
    }

    this.cache.set(name, encrypted);
  }

  /**
   * Save a config with file locking. The config passed in must be plaintext
   * (encrypted leaves are produced by this layer, not by callers).
   */
  async save(config: RdcConfig, name: string = DEFAULT_CONFIG_NAME): Promise<void> {
    const scoped = currentRequestConfig();
    if (scoped) {
      // The caller saves a whole document built from the copy it read; replay only its edit, so a replay after a lost compare-and-swap keeps what another device wrote.
      const read = scoped.readCopy;
      await writeScoped(scoped, (newest) => replaySavedEdit(newest, read, config), 'spec');
      return;
    }
    await this.withLock(name, async () => {
      await this.saveUnlocked(config, name);
    });
  }

  private mutate(
    name: string,
    updater: (config: RdcConfig) => RdcConfig,
    bumpVersion: boolean,
    opts: { createIfMissing?: boolean } = {}
  ): Promise<RdcConfig> {
    const scoped = currentRequestConfig();
    if (scoped) return writeScoped(scoped, updater, bumpVersion ? 'spec' : 'state');
    return this.withLock(
      name,
      () =>
        this.withSealRecovery(name, async () => {
          this.cache.delete(name);
          const raw = await this.loadUnlocked(name);
          const plain = await this.decryptConfig(raw);
          const updated = updater(plain);
          await this.saveUnlocked(updated, name, bumpVersion);
          return this.cache.get(name)!;
        }),
      opts
    );
  }

  /**
   * Update the SPEC half of a config (declared intent). Bumps the version
   * counter. Reads the latest from disk, decrypts, applies the updater, and
   * re-encrypts per field on save.
   */
  update(name: string, updater: (config: RdcConfig) => RdcConfig): Promise<RdcConfig> {
    return this.mutate(name, updater, true);
  }

  /**
   * Update the STATE half of a config (runtime status). Does NOT bump the
   * local version counter: status churn must not create audit noise (spec 04
   * §1.3 property 1). The writer is responsible for touching only `state.*`.
   * A remote-enabled config's state write is pushed (see below).
   */
  async updateState(name: string, updater: (config: RdcConfig) => RdcConfig): Promise<RdcConfig> {
    const scoped = currentRequestConfig();
    if (scoped) return writeScoped(scoped, updater, 'state');
    // A STATE write must never CREATE a config file. Status is subordinate to the config's existence: when the file is gone (the tutorial preambles `rm` it between runs; `config prune` removes it), a background writer , the executor daemon's post-request provision bookkeeping above all, must not resurrect an empty config. Observed live: the daemon recreated the file between a preamble's `rm` and its `config init`, which then died on "Config already exists" and cascaded through the whole tutorial sequence. Callers of updateState are best-effort by contract, so a missing config surfaces as a rejected promise they already tolerate.
    try {
      await fs.access(this.getPath(name));
    } catch {
      throw new Error(`Config "${name}" does not exist; refusing to create it for a state write`);
    }
    // `state` syncs (T17): on a remote config the file is a cache the next pull overwrites, so the write is pushed, settled by the server's compare-and-swap (two devices allocating a network ID at once end with distinct IDs). It fails closed when the server is unreachable, like any write.
    if (this.remoteStateWriter && hasRemoteConfig(await this.load(name))) {
      return this.remoteStateWriter(name, updater);
    }
    return this.mutate(name, updater, false, { createIfMissing: false });
  }

  /**
   * Route state writes of remote-enabled configs through `writer`. The config service registers
   * itself here: the push needs its adapter and resource view, which this layer cannot import
   * without a module cycle.
   */
  setRemoteStateWriter(writer: RemoteStateWriter | null): void {
    this.remoteStateWriter = writer;
  }

  /**
   * Delete the `.bak` copy every save leaves beside a config. A purge (the offline cache of a
   * config this account lost access to) must not leave the purged content one rename away.
   */
  async removeBackup(name: string): Promise<void> {
    await fs.rm(this.getBackupPath(name), { force: true });
  }

  /**
   * Update a remote-enabled config's local CACHE (observation of the server
   * copy, not declared intent). Same contract as updateState: never bumps the
   * version counter, never resurrects a deleted config, a cache refresh
   * racing a `config delete` must not bring the file back from the dead.
   */
  async updateCache(name: string, updater: (config: RdcConfig) => RdcConfig): Promise<RdcConfig> {
    const scoped = currentRequestConfig();
    if (scoped) return writeScoped(scoped, updater, 'cache');
    try {
      await fs.access(this.getPath(name));
    } catch {
      throw new Error(`Config "${name}" does not exist; refusing to create it for a cache write`);
    }
    return this.mutate(name, updater, false, { createIfMissing: false });
  }

  /**
   * Create a new config file with a fresh UUID and version 1.
   * Throws if a config with this name already exists.
   */
  async init(name: string = DEFAULT_CONFIG_NAME): Promise<RdcConfig> {
    refuseInRequestScope('create', name);
    await this.ensureDirectory();
    const configPath = this.getPath(name);

    const config = createEmptyRdcConfig();
    const content = stringifyConfig(config);
    try {
      // 'wx' makes the existence check and the create one step: a check-then-write truncated a config another process created (and wrote to) in between.
      await fs.writeFile(configPath, content, { mode: 0o600, flag: 'wx' });
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === 'EEXIST') {
        throw new Error(`Config "${name}" already exists`);
      }
      throw error;
    }
    this.cache.set(name, config);
    return config;
  }

  /**
   * List available config names (*.json in config dir, excluding system files).
   */
  async list(): Promise<string[]> {
    if (currentRequestConfig()) return [DEFAULT_CONFIG_NAME];
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
    const scoped = currentRequestConfig();
    if (scoped) return scoped.config;
    await this.ensureConfigFile(DEFAULT_CONFIG_NAME);
    return this.load(DEFAULT_CONFIG_NAME);
  }

  /**
   * Check if a config file exists.
   */
  async exists(name: string): Promise<boolean> {
    // The request-scoped config answers for every name: it is the only config this request has.
    if (currentRequestConfig()) return true;
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
    refuseInRequestScope('delete', name);
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
    // The config file is gone: the cache entry goes with it even when a later unlink fails.
    this.cache.delete(name);
    try {
      await fs.unlink(this.getBackupPath(name));
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== 'ENOENT') {
        throw error;
      }
    }
    try {
      await fs.unlink(getSubscriptionTokenFile(name, this.configDir));
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== 'ENOENT') {
        throw error;
      }
    }
  }

  /**
   * Recover a config from its .bak backup file.
   * Returns the recovered config, or null if no backup exists.
   */
  async recover(name: string = DEFAULT_CONFIG_NAME): Promise<RdcConfig | null> {
    refuseInRequestScope('restore', name);
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
      const config = parseJsonText(content) as RdcConfig;
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
  withApiLock<T>(name: string, operation: () => Promise<T>): Promise<T> {
    // No file, so nothing to lock: a request-scoped config is private to its request.
    if (currentRequestConfig()) return operation();
    return this.withLock(name, () => {
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
