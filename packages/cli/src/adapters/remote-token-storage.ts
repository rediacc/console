/**
 * Remote Token Storage
 *
 * Manages rotating X-Config-Token values and associated wrappedCek
 * in separate files outside the config (tokens should never be in config).
 *
 * Token file location: <configDir>/.tokens/<configName>.json
 * File permissions: 0o600
 *
 * Sealing (PLAN-config-sealed-local.md D9): a write that knows the config's slot-secret id (the
 * adapter's lease passes `remote.storageKeyId`, and a file sealed before records it as `slotKeyId`)
 * stores the confidential values (`token`, `sync.fckSalt`, `sync.configKey`, `sync.policyContext`)
 * as `sealed: {v:1, data}`, AES-256-GCM under HKDF(slot secret, "rdc-token-seal-v1|<configName>").
 * `wrappedCek` is already ciphertext under the slot secret and stays as it is. The anti-rollback
 * counters (`binding`, `highWater`, `envelopeVersion`, `cekGeneration`, `policyHighWater`) stay
 * plaintext: they are not secret, and sealing them would let a lost key reset them silently, which
 * T8/T9 forbid. A file with no `sealed` field (written before sealing, or by `set()`) reads as it
 * always did and is sealed by its next leased write.
 */

import { createHash } from 'node:crypto';
import { promises as fs } from 'node:fs';
import { join } from 'node:path';
import { hkdfDeriveKey } from '@rediacc/shared/config-crypto';
import type { StoredConfigKeyWrap } from '@rediacc/shared/config-schema';
import { getConfigDir } from '@rediacc/shared/paths';
import lockfile from 'proper-lockfile';
import { readLocalMachineId } from '../services/account/client-machine-id.js';
import { rdcCommand } from '../services/config/config-name.js';
import { parseJsonText } from '../utils/json-text.js';
import { clearSealKeyCache, openString, readCachedSecret, sealString } from './config-seal-key.js';
import { RemotePasskeySecretMissingError, RemoteStaleSlotError } from './remote-config-errors.js';
import type { RemotePolicyContext } from './remote-config-types.js';

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
  /**
   * That envelope's `commitments.fckSalt`: the key of this device's tombstone proofs. Absent only
   * when a re-enrollment kept the counters of a sealed record it could no longer open (the slot
   * secret under its id was replaced); the next pull or push records it again.
   */
  fckSalt?: string;
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
  /**
   * The principal and effective policy the last opened session judged this device's runs with
   * (RemoteConfigAdapter.policyContext). Read only when the config server is unreachable, so a
   * read served from the offline cache is judged as the same member it was online; a device that
   * never opened a session holds none and is refused offline.
   */
  policyContext?: RemotePolicyContext;
}

export interface TokenData {
  /** Current rotating config token */
  token: string;
  /** Wrapped CEK (base64) for this config */
  wrappedCek: string;
  /** What this device last saw of the config; absent until its first pull or push. */
  sync?: SyncRecord;
}

/** Where the token file's slot secret comes from (tests inject one; the default is the per-process cache of config-seal-key.ts). */
export interface SlotSecrets {
  /** The slot secret under `storageKeyId`, or null when secure storage holds none. */
  read(storageKeyId: string): Promise<string | null>;
  /**
   * Forget every cached secret. `set()` calls it: it writes a new enrollment's credentials right
   * after its caller stored a (possibly different) slot secret under the same id, so a value cached
   * earlier in this process may be stale.
   */
  reset(): void;
}

const processSlotSecrets: SlotSecrets = {
  read: readCachedSecret,
  reset: clearSealKeyCache,
};

const TOKEN_SEAL_INFO = 'rdc-token-seal-v1|';

/** The confidential values of a token file, sealed together. */
interface SealedTokenFields {
  token: string;
  fckSalt?: string;
  configKey?: StoredConfigKeyWrap;
  policyContext?: RemotePolicyContext;
}

/** The token file as it is on disk: TokenData, with the confidential values moved under `sealed` when it is sealed. */
interface TokenFile {
  token?: string;
  wrappedCek: string;
  sync?: Partial<SyncRecord>;
  /** The secure-storage id of the slot secret the `sealed` field is keyed by. */
  slotKeyId?: string;
  sealed?: { v: 1; data: string };
}

/** What a write is sealed under: a slot-secret id, or none (plaintext). */
interface SealTarget {
  slotKeyId?: string;
}

/**
 * Proof that THIS device enrolled a config, kept beside its token file as `<configName>.enrolled`.
 * Non-secret: the device id is a digest of the host's machine id, so a marker carried over in a
 * copied config directory names the other machine and reads as not enrolled here.
 */
interface EnrollmentMarker {
  /** `deviceIdentity()` of the device that enrolled. */
  deviceId: string;
  /** ISO time of the enrollment. */
  enrolledAt: string;
}

/** The digest of this host's machine id that a marker records (the raw id never leaves the host). */
async function deviceIdentity(): Promise<string> {
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

  private readonly slotSecrets: SlotSecrets;

  /** The stored file behind each snapshot `get()` returned for a file it could not open. */
  private readonly snapshots = new WeakMap<TokenData, TokenFile>();

  constructor(
    tokensDir: string = TOKENS_DIR,
    identify: () => Promise<string> = deviceIdentity,
    slotSecrets: SlotSecrets = processSlotSecrets
  ) {
    this.tokensDir = tokensDir;
    this.identify = identify;
    this.slotSecrets = slotSecrets;
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
      const marker = parseJsonText(raw) as Partial<EnrollmentMarker> | null;
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
   * Get the current token and wrappedCek for a config, unsealed. Returns null if no token file
   * exists.
   *
   * A sealed file that cannot be opened (its slot secret is gone, or the secret under its id was
   * replaced) reads as a snapshot with an empty `token` and only the plaintext counters, so a
   * caller asking whether usable credentials exist sees none. It is the file a re-enrollment saves
   * before it replaces the secret: handing the snapshot back to `set()` writes the stored file
   * again byte for byte, sealed values and counters included. A lease on such a file throws the
   * re-enroll error instead (`withLease`).
   */
  async get(configName: string): Promise<TokenData | null> {
    const file = await this.readFile(configName);
    if (!file) return null;
    try {
      return await this.open(configName, file);
    } catch (error) {
      if (!isSlotLoss(error)) throw error;
      const snapshot: TokenData = { token: '', wrappedCek: file.wrappedCek };
      const counters = file.sync ? countersOnly(file.sync) : undefined;
      if (counters) snapshot.sync = counters;
      this.snapshots.set(snapshot, file);
      return snapshot;
    }
  }

  /** The token file as stored, or null when there is none. */
  private async readFile(configName: string): Promise<TokenFile | null> {
    try {
      const raw = await fs.readFile(this.getPath(configName), 'utf-8');
      return parseJsonText(raw) as TokenFile;
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === 'ENOENT') {
        return null;
      }
      throw error;
    }
  }

  /** The AES-GCM key and AAD of a `configName` token file sealed under `slotKeyId`; null when the secret is gone. */
  private async sealKey(
    configName: string,
    slotKeyId: string
  ): Promise<{ key: CryptoKey; aad: string } | null> {
    const secret = await this.slotSecrets.read(slotKeyId);
    if (secret === null) return null;
    const key = await hkdfDeriveKey(
      new TextEncoder().encode(secret),
      new Uint8Array(0),
      `${TOKEN_SEAL_INFO}${configName}`
    );
    return { key, aad: `${TOKEN_SEAL_INFO}${configName}|${slotKeyId}` };
  }

  /** A stored file as TokenData: a plaintext one as it is, a sealed one opened under its slot secret. */
  private async open(configName: string, file: TokenFile): Promise<TokenData> {
    if (!file.sealed) return file as TokenData;
    return joinFields(file, await this.openSealed(configName, file));
  }

  private async openSealed(configName: string, file: TokenFile): Promise<SealedTokenFields> {
    const { sealed, slotKeyId } = file;
    if (!sealed || !slotKeyId) throw new RemoteStaleSlotError(undefined, configName);
    const seal = await this.sealKey(configName, slotKeyId);
    if (!seal) {
      throw new RemotePasskeySecretMissingError(configName, await this.enrolledHere(configName));
    }
    try {
      return parseJsonText(await openString(seal.key, sealed.data, seal.aad)) as SealedTokenFields;
    } catch (error) {
      throw new RemoteStaleSlotError({ cause: error }, configName);
    }
  }

  /**
   * TokenData as it goes to disk: sealed under `target.slotKeyId` when one is named, plaintext
   * otherwise. A named slot secret that secure storage no longer holds refuses the write with the
   * re-enroll error rather than falling back to plaintext.
   */
  private async toFile(
    configName: string,
    data: TokenData,
    target: SealTarget
  ): Promise<TokenFile> {
    const { slotKeyId } = target;
    if (!slotKeyId) return data;
    const seal = await this.sealKey(configName, slotKeyId);
    if (!seal) {
      throw new RemotePasskeySecretMissingError(configName, await this.enrolledHere(configName));
    }
    const { fields, rest } = splitFields(data);
    return {
      ...rest,
      slotKeyId,
      sealed: { v: 1, data: await sealString(seal.key, JSON.stringify(fields), seal.aad) },
    };
  }

  /** temp+rename write, sealed under `target`; the caller holds the lock. */
  private async writeUnlocked(
    configName: string,
    path: string,
    data: TokenData,
    target: SealTarget
  ): Promise<void> {
    await writeFileAtomic(path, await this.toFile(configName, data, target));
  }

  /**
   * Atomically save a token and wrappedCek.
   * Uses file locking + temp+rename for crash safety. A sync record the file already holds is kept
   * unless `data` carries one: re-enrolling a device (a CEK rotation's re-handoff) must not forget
   * the versions it saw. The record names its config, so a file re-pointed elsewhere ignores it.
   * Its `cekGeneration` is dropped: it described the wrapped CEK being replaced, and the new one's
   * is learned again on the next pull.
   *
   * The write is plaintext: `set()` stores a new enrollment's credentials (or restores the previous
   * ones after a failed re-enrollment) around a slot secret its caller is still changing, so it
   * cannot know which secret will stand. The next leased write, which names the slot the adapter
   * opens the CEK with, seals it. A kept record whose sealed values no longer open (the secret
   * under its id was replaced) keeps its plaintext counters only.
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
      await this.setUnlocked(configName, path, data);
    } finally {
      await release();
    }
  }

  /** The body of `set()`, under its lock. */
  private async setUnlocked(configName: string, path: string, data: TokenData): Promise<void> {
    const stored = this.snapshots.get(data);
    const existing = stored || data.sync ? undefined : await this.keptSync(configName);
    // After keptSync, which may still open the record under a secret cached before the caller replaced it.
    this.slotSecrets.reset();
    if (stored) {
      await writeFileAtomic(path, stored);
      return;
    }
    const kept = existing ? withoutGeneration(existing) : undefined;
    await this.writeUnlocked(configName, path, kept ? { ...data, sync: kept } : data, {});
  }

  /**
   * The sync record `set()` carries over: the whole record when the file opens, its plaintext
   * counters when the file is sealed and no longer opens, none when there is no file or no record.
   */
  private async keptSync(configName: string): Promise<SyncRecord | undefined> {
    const file = await this.readFile(configName).catch(() => null);
    if (!file?.sync) return undefined;
    try {
      return (await this.open(configName, file)).sync;
    } catch {
      return countersOnly(file.sync);
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
   *
   * `seal.slotKeyId` names the slot secret the lease's writes are sealed under (the adapter passes
   * its `remote.storageKeyId`); without one they keep the file's own `slotKeyId`, or stay plaintext.
   */
  async withLease<T>(
    configName: string,
    fn: (lease: TokenLease) => Promise<T>,
    seal: SealTarget = {}
  ): Promise<T> {
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
      const file = await this.readFile(configName);
      const data = file ? await this.open(configName, file) : null;
      const target: SealTarget = { slotKeyId: seal.slotKeyId ?? file?.slotKeyId };
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
          await this.writeUnlocked(configName, path, current, target);
        },
        recordSync: async (sync: SyncRecord) => {
          if (!current) throw missingTokenFile(configName);
          current = { ...current, sync };
          await this.writeUnlocked(configName, path, current, target);
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

/** temp+rename write of a token file at 0600; the caller holds the lock. */
async function writeFileAtomic(path: string, file: TokenFile): Promise<void> {
  const tmpPath = `${path}.tmp`;
  await fs.writeFile(tmpPath, JSON.stringify(file), { mode: 0o600 });
  await fs.rename(tmpPath, path);
}

/** A sealed token file failed to open because of its slot secret (gone, or replaced). */
function isSlotLoss(error: unknown): boolean {
  return error instanceof RemotePasskeySecretMissingError || error instanceof RemoteStaleSlotError;
}

/** TokenData split into the values `sealed` holds and the rest, which stays plaintext. */
function splitFields(data: TokenData): {
  fields: SealedTokenFields;
  rest: Omit<TokenFile, 'sealed' | 'slotKeyId'>;
} {
  const fields: SealedTokenFields = { token: data.token };
  const rest: Omit<TokenFile, 'sealed' | 'slotKeyId'> = { wrappedCek: data.wrappedCek };
  if (data.sync) {
    const { fckSalt, configKey, policyContext, ...counters } = data.sync;
    if (fckSalt !== undefined) fields.fckSalt = fckSalt;
    if (configKey !== undefined) fields.configKey = configKey;
    if (policyContext !== undefined) fields.policyContext = policyContext;
    rest.sync = counters;
  }
  return { fields, rest };
}

/** The inverse of `splitFields`. */
function joinFields(file: TokenFile, fields: SealedTokenFields): TokenData {
  const data: TokenData = { token: fields.token, wrappedCek: file.wrappedCek };
  if (file.sync) {
    data.sync = {
      ...(file.sync as SyncRecord),
      ...(fields.fckSalt === undefined ? {} : { fckSalt: fields.fckSalt }),
      ...(fields.configKey === undefined ? {} : { configKey: fields.configKey }),
      ...(fields.policyContext === undefined ? {} : { policyContext: fields.policyContext }),
    };
  }
  return data;
}

/** A stored record's plaintext anti-rollback counters, without any confidential value. */
function countersOnly(sync: Partial<SyncRecord>): SyncRecord | undefined {
  const { binding, highWater, envelopeVersion, cekGeneration, policyHighWater } = sync;
  if (binding === undefined || highWater === undefined || envelopeVersion === undefined) {
    return undefined;
  }
  return {
    binding,
    highWater,
    envelopeVersion,
    ...(cekGeneration === undefined ? {} : { cekGeneration }),
    ...(policyHighWater === undefined ? {} : { policyHighWater }),
  };
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
