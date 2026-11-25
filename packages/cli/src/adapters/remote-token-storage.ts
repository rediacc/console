/**
 * Remote Token Storage
 *
 * Manages rotating X-Config-Token values and associated wrappedCek
 * in separate files outside the config (tokens should never be in config).
 *
 * Token file location: <configDir>/.tokens/<configName>.json
 * File permissions: 0o600
 */

import { createHash } from 'node:crypto';
import { promises as fs } from 'node:fs';
import { join } from 'node:path';
import type { StoredConfigKeyWrap } from '@rediacc/shared/config-schema';
import { getConfigDir } from '@rediacc/shared/paths';
import lockfile from 'proper-lockfile';
import { readLocalMachineId } from '../services/account/client-machine-id.js';
import { rdcCommand } from '../services/config/config-name.js';

const TOKENS_DIR = join(getConfigDir(), '.tokens');

/**
 * What this device last saw of the config its token file serves (PLAN-config-sync-hardening T8/T9).
 * Kept in the token file rather than the config file so a wiped or replaced cache cannot reset it.
 */
export interface SyncRecord {
  /** `<storeId>/<configId>/<teamId or empty>`: a record for another config is ignored. */
  binding: string;
  /** The newest version this device pulled or pushed; a pull older than it is a rollback. */
  highWater: number;
  /** The envelope version the server held at `highWater` (a pull below it is refused as a downgrade). */
  envelopeVersion: 2 | 3 | 4;
  /** That envelope's `commitments.fckSalt`: the key of this device's tombstone proofs. */
  fckSalt: string;
  /**
   * That envelope's content-key wrap when it is v4: the next push unwraps the config's content key
   * from it, so the key (and every commitment key) stays the same across pushes.
   */
  configKey?: StoredConfigKeyWrap;
  /**
   * The store's CEK generation this device's wrapped CEK belongs to (T10): recorded when a blob
   * opened under it, sent with every push, and held against the store's to tell a rotated-away key
   * from an unreadable config. Absent until the first pull or push that learns it.
   */
  cekGeneration?: number;
  /**
   * The newest version of each policy record this device opened, by
   * `<storeId>/<configId>/<teamId or empty>` (services/config/policy-record.ts): a lower version is a
   * replayed policy and is refused.
   */
  policyHighWater?: Record<string, number>;
}

export interface TokenData {
  /** Current rotating config token */
  token: string;
  /** Wrapped CEK (base64) for this config */
  wrappedCek: string;
  /** What this device last saw of the config; absent until its first pull or push. */
  sync?: SyncRecord;
}

/**
 * Proof that THIS device enrolled a config, kept beside its token file as `<configName>.enrolled`.
 * Non-secret: the device id is a digest of the host's machine id, so a marker carried over in a
 * copied config directory names the other machine and reads as not enrolled here.
 */
export interface EnrollmentMarker {
  /** `deviceIdentity()` of the device that enrolled. */
  deviceId: string;
  /** ISO time of the enrollment. */
  enrolledAt: string;
}

/** The digest of this host's machine id that a marker records (the raw id never leaves the host). */
export async function deviceIdentity(): Promise<string> {
  const machineId = await readLocalMachineId();
  return createHash('sha256').update(`rdc-device-enrollment:${machineId}`).digest('hex');
}

/** Lock retry options matching config-file-storage.ts */
const LOCK_OPTIONS = {
  stale: 45_000,
  retries: { retries: 900, minTimeout: 50, maxTimeout: 50, factor: 1 },
};

/**
 * One adapter operation's hold on a config's token file (`RemoteTokenStorage.withLease`).
 *
 * `token` is the token the next request must send. `update` persists a rotated token under the lock
 * the lease already holds and makes it the lease's current token, so every request of the operation
 * sends the token the previous one returned, and no other process spends a token this one has used.
 */
export interface TokenLease {
  /** The token file as it was when the lease was taken, or null when this config has none. */
  readonly data: TokenData | null;
  /** The token the next request of this operation sends. */
  readonly token: string | undefined;
  /** The sync record as it stands now (the lease's own `recordSync` writes included). */
  readonly sync: SyncRecord | undefined;
  /** Persist a rotated token and send it on the next request. */
  update(token: string): Promise<void>;
  /** Persist what this device now knows of the config (after a pull or a push). */
  recordSync(record: SyncRecord): Promise<void>;
}

export class RemoteTokenStorage {
  private readonly tokensDir: string;

  private readonly identify: () => Promise<string>;

  constructor(tokensDir: string = TOKENS_DIR, identify: () => Promise<string> = deviceIdentity) {
    this.tokensDir = tokensDir;
    this.identify = identify;
  }

  private getMarkerPath(configName: string): string {
    return join(this.tokensDir, `${configName}.enrolled`);
  }

  /**
   * Record that this device enrolled `configName`, now. Called once an enrollment succeeded (the
   * handoff or a re-enrollment); a failure here costs only the wording of a later missing-key
   * message, so callers do not let it fail the enrollment.
   */
  async recordEnrollment(configName: string): Promise<void> {
    await this.ensureDirectory();
    const path = this.getMarkerPath(configName);
    const marker: EnrollmentMarker = {
      deviceId: await this.identify(),
      enrolledAt: new Date().toISOString(),
    };
    const tmpPath = `${path}.tmp`;
    await fs.writeFile(tmpPath, JSON.stringify(marker), { mode: 0o600 });
    await fs.rename(tmpPath, path);
  }

  /**
   * True only when the marker beside the token file names this device. No marker (a config copied
   * from another machine, or enrolled before markers existed), another device's marker, or an
   * unreadable one all read as not enrolled here.
   */
  async enrolledHere(configName: string): Promise<boolean> {
    try {
      const raw = await fs.readFile(this.getMarkerPath(configName), 'utf-8');
      const marker = JSON.parse(raw) as Partial<EnrollmentMarker> | null;
      return typeof marker?.deviceId === 'string' && marker.deviceId === (await this.identify());
    } catch {
      return false;
    }
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

  /** temp+rename write; the caller holds the lock. */
  private async writeUnlocked(path: string, data: TokenData): Promise<void> {
    const tmpPath = `${path}.tmp`;
    await fs.writeFile(tmpPath, JSON.stringify(data), { mode: 0o600 });
    await fs.rename(tmpPath, path);
  }

  /**
   * Atomically save a token and wrappedCek.
   * Uses file locking + temp+rename for crash safety. A sync record the file already holds is kept
   * unless `data` carries one: re-enrolling a device (a CEK rotation's re-handoff) must not forget
   * the versions it saw. The record names its config, so a file re-pointed elsewhere ignores it.
   * Its `cekGeneration` is dropped: it described the wrapped CEK being replaced, and the new one's
   * is learned again on the next pull.
   */
  async set(configName: string, data: TokenData): Promise<void> {
    await this.ensureDirectory();
    const path = this.getPath(configName);

    // Ensure the file exists for locking (proper-lockfile requires it)
    try {
      await fs.access(path);
    } catch {
      try {
        // 'wx': never truncate a token a concurrent set() wrote since the access check.
        await fs.writeFile(path, '{}', { mode: 0o600, flag: 'wx' });
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code !== 'EEXIST') throw error;
      }
    }

    const release = await lockfile.lock(path, LOCK_OPTIONS);
    try {
      const existing = data.sync ? null : await this.get(configName).catch(() => null);
      const kept = existing?.sync ? withoutGeneration(existing.sync) : undefined;
      await this.writeUnlocked(path, kept ? { ...data, sync: kept } : data);
    } finally {
      await release();
    }
  }

  /**
   * Hold the token file's lock for a whole adapter operation: read the token, run every request
   * with it, and persist each rotated token under the same lock (F8). Two processes sharing one
   * token file then take turns instead of spending the same token twice, and an older token can
   * never overwrite a newer one. Not reentrant: `fn` must not take another lease on `configName`.
   *
   * A config with no token file runs `fn` unlocked with `data` null; the adapter refuses that
   * before any request, and `update` throws.
   */
  async withLease<T>(configName: string, fn: (lease: TokenLease) => Promise<T>): Promise<T> {
    const path = this.getPath(configName);
    let release: () => Promise<void>;
    try {
      release = await lockfile.lock(path, LOCK_OPTIONS);
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error;
      return fn({
        data: null,
        token: undefined,
        sync: undefined,
        update: () => Promise.reject(missingTokenFile(configName)),
        recordSync: () => Promise.reject(missingTokenFile(configName)),
      });
    }
    try {
      const data = await this.get(configName);
      let current = data;
      const lease: TokenLease = {
        data,
        get token() {
          return current?.token;
        },
        get sync() {
          return current?.sync;
        },
        update: async (token: string) => {
          if (!current) throw missingTokenFile(configName);
          current = { ...current, token };
          await this.writeUnlocked(path, current);
        },
        recordSync: async (sync: SyncRecord) => {
          if (!current) throw missingTokenFile(configName);
          current = { ...current, sync };
          await this.writeUnlocked(path, current);
        },
      };
      return await fn(lease);
    } finally {
      await release();
    }
  }

  /**
   * Update only the token value, preserving wrappedCek. The read and the write happen under one
   * lock, so a concurrent rotation cannot be overwritten by an older token.
   */
  async updateToken(configName: string, token: string): Promise<void> {
    await this.withLease(configName, (lease) => lease.update(token));
  }

  /**
   * Delete the token file for a config, and the enrollment marker beside it.
   */
  async delete(configName: string): Promise<void> {
    for (const path of [this.getPath(configName), this.getMarkerPath(configName)]) {
      try {
        await fs.unlink(path);
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code !== 'ENOENT') {
          throw error;
        }
      }
    }
  }
}

function withoutGeneration(sync: SyncRecord): SyncRecord {
  const rest = { ...sync };
  delete rest.cekGeneration;
  return rest;
}

function missingTokenFile(configName: string): Error {
  return new Error(
    `No token file for config "${configName}". Run: ${rdcCommand('config remote enable', configName)}`
  );
}

export const remoteTokenStorage = new RemoteTokenStorage();
