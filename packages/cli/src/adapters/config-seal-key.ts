/**
 * Seal keys of a config's encrypted-at-rest leaves (PLAN-config-sealed-local.md D2, D3).
 *
 * - `K_ring`: 32 random bytes, base64, held in the OS secure storage under the config's `keyringId`
 *   (`rdc:seal:<uuid>`), fresh per seal and per re-seal.
 * - `K_pw`: PBKDF2-SHA256(password, kdf.salt, kdf.iterations), present whenever the master password is
 *   part of the key.
 * - Field key: HKDF-SHA256 over `K_ring`, `K_pw` or `K_ring || K_pw` (by mode), with
 *   `rdc-config-seal-v2|<config.id>` as info, used as an AES-256-GCM key.
 *
 * One cache per process holds every `K_ring` and `K_pw` it has seen, so a config read costs at most one
 * secure-storage `get` per key per process (one PowerShell spawn on a DPAPI host, not one per field),
 * and one PBKDF2 per password. Nothing here runs at import: `getSecureStorage()` is called only when a
 * key is actually needed, so a public read that never unseals never selects a backend (its proof alone
 * is a round trip, three PowerShell spawns on DPAPI).
 *
 * No key, password or derived byte ever leaves this module except as a key object or as the value
 * stored in secure storage; nothing is printed or logged.
 */

import { createHash, randomBytes, randomUUID, timingSafeEqual } from 'node:crypto';
import {
  aesDecryptFromString,
  aesEncryptToString,
  hkdfDeriveKey,
} from '@rediacc/shared/config-crypto';
import {
  type EncryptionMode,
  type RdcConfig,
  SEAL_KEYRING_ID,
  usesKeyring,
  usesMasterPassword,
} from '@rediacc/shared/config-schema';
import { ENCRYPTION_CONFIG } from '@rediacc/shared/encryption';
import { getSecureStorage } from '../utils/secure-storage.js';
import { nodeCryptoProvider } from './crypto.js';

/** Bytes of a random seal key. */
const RING_KEY_BYTES = 32;
const FIELD_KEY_INFO = 'rdc-config-seal-v2|';
const KDF_ALG = 'pbkdf2-sha256';

export interface SealKdf {
  alg: typeof KDF_ALG;
  iterations: number;
  salt: string;
}

/**
 * A sealed config's key cannot be had: secure storage has no entry for its `keyringId` (`missing`), or
 * a v2 blob failed authentication under a key that includes the keyring key (`auth`). A legacy blob
 * that fails to decrypt is never key loss. Carries identifiers only, never key material; the recovery
 * (services/config/seal-recovery.ts) and its user-facing line belong to the caller.
 */
export class SealKeyLostError extends Error {
  constructor(
    readonly configId: string,
    readonly keyringId: string,
    readonly reason: 'missing' | 'auth'
  ) {
    super(
      `seal key ${keyringId} of config ${configId} is ${reason === 'missing' ? 'missing' : 'not the key the config was sealed with'}`
    );
    this.name = 'SealKeyLostError';
  }
}

// ─── Per-process cache ──────────────────────────────────────────────────

/** Secure-storage key -> its value, only ever a value that was found. */
const secretCache = new Map<string, string>();

interface PasswordKey {
  /** SHA-256 of the password the key was derived from, so a different password is never served a cached key. */
  passwordDigest: Buffer;
  key: Buffer;
}

/** `<config.id>|<iterations>|<salt>` -> the PBKDF2 output for that salt. */
const passwordKeyCache = new Map<string, PasswordKey>();

/** Forget every cached key (tests, and a process that must re-read secure storage). */
export function clearSealKeyCache(): void {
  secretCache.clear();
  passwordKeyCache.clear();
}

/**
 * The value secure storage holds under `storageKey`, read at most once per process; null when there is
 * none (an absence is not cached, so a later write is seen). Used for the seal key, and by the remote
 * adapter for the slot secret (D9), so both share one read per process.
 */
export async function readCachedSecret(storageKey: string): Promise<string | null> {
  const cached = secretCache.get(storageKey);
  if (cached !== undefined) return cached;
  const value = await getSecureStorage().get(storageKey);
  if (value !== null) secretCache.set(storageKey, value);
  return value;
}

/** `readCachedSecret` for a caller that cannot await (the api-token reader, D9); the same cache. */
function readCachedSecretSync(storageKey: string): string | null {
  const cached = secretCache.get(storageKey);
  if (cached !== undefined) return cached;
  const value = getSecureStorage().getSync(storageKey);
  if (value !== null) secretCache.set(storageKey, value);
  return value;
}

/** Store `value` under `storageKey` and remember it for this process. */
export async function writeCachedSecret(storageKey: string, value: string): Promise<void> {
  await getSecureStorage().set(storageKey, value);
  secretCache.set(storageKey, value);
}

/** Delete `storageKey` from secure storage and from this process's cache. */
export async function deleteCachedSecret(storageKey: string): Promise<void> {
  secretCache.delete(storageKey);
  await getSecureStorage().delete(storageKey);
}

// ─── Seal keys ──────────────────────────────────────────────────────────

function decodeRingKey(value: string): Buffer | null {
  const key = Buffer.from(value, 'base64');
  return key.length === RING_KEY_BYTES ? key : null;
}

/**
 * The random seal key under `keyringId`. Throws SealKeyLostError (`missing`) when secure storage has
 * no entry, or an entry that is not a seal key.
 */
export async function loadKey(configId: string, keyringId: string): Promise<Buffer> {
  const value = await readCachedSecret(keyringId);
  const key = value === null ? null : decodeRingKey(value);
  if (!key) throw new SealKeyLostError(configId, keyringId, 'missing');
  return key;
}

/** `loadKey` for a caller that cannot await (the api-token reader, D9); the same cache and the same error. */
export function loadKeySync(configId: string, keyringId: string): Buffer {
  const value = readCachedSecretSync(keyringId);
  const key = value === null ? null : decodeRingKey(value);
  if (!key) throw new SealKeyLostError(configId, keyringId, 'missing');
  return key;
}

/**
 * Mint a fresh random seal key, store it in secure storage and return its `keyringId`. The caller
 * records the id in the config, and deletes the key with `dropKey` when the write it was minted for
 * does not land.
 */
export async function mintKey(): Promise<string> {
  const keyringId = `rdc:seal:${randomUUID()}`;
  await writeCachedSecret(keyringId, randomBytes(RING_KEY_BYTES).toString('base64'));
  return keyringId;
}

/** Delete a seal key from secure storage and from the cache. */
export async function dropKey(keyringId: string): Promise<void> {
  if (!SEAL_KEYRING_ID.test(keyringId)) throw new Error(`not a seal key id: ${keyringId}`);
  await deleteCachedSecret(keyringId);
}

/** A new password KDF record: PBKDF2-SHA256 at `ENCRYPTION_CONFIG.ITERATIONS` over a fresh salt. */
export function newSealKdf(): SealKdf {
  return {
    alg: KDF_ALG,
    iterations: ENCRYPTION_CONFIG.ITERATIONS,
    salt: randomBytes(ENCRYPTION_CONFIG.SALT_LENGTH).toString('base64'),
  };
}

/** PBKDF2 of `password` under `kdf`, derived once per (config, salt, password) per process. */
export async function derivePasswordKey(
  configId: string,
  kdf: SealKdf,
  password: string
): Promise<Buffer> {
  const slot = `${configId}|${kdf.iterations}|${kdf.salt}`;
  const passwordDigest = createHash('sha256').update(password, 'utf8').digest();
  const cached = passwordKeyCache.get(slot);
  if (cached && timingSafeEqual(cached.passwordDigest, passwordDigest)) return cached.key;
  const key = await nodeCryptoProvider.deriveKeyBytes(
    password,
    Buffer.from(kdf.salt, 'base64'),
    kdf.iterations
  );
  passwordKeyCache.set(slot, { passwordDigest, key });
  return key;
}

/**
 * The AES-256-GCM field key of a sealed config, from the mode, `keyringId` and `kdf` recorded in
 * `config.encryption`. `password` is required when the mode includes the master password.
 */
export async function deriveFieldKey(config: RdcConfig, password?: string): Promise<CryptoKey> {
  const encryption = config.encryption;
  const mode: EncryptionMode | undefined = encryption?.mode;
  if (!encryption || mode === 'plaintext' || mode === undefined) {
    throw new Error(`config ${config.id} is not sealed`);
  }
  const parts: Buffer[] = [];
  if (usesKeyring(mode)) {
    if (!encryption.keyringId)
      throw new Error(`config ${config.id} is in ${mode} mode without a keyringId`);
    parts.push(await loadKey(config.id, encryption.keyringId));
  }
  if (usesMasterPassword(mode)) {
    if (!encryption.kdf) throw new Error(`config ${config.id} is in ${mode} mode without a kdf`);
    if (password === undefined) throw new Error(`config ${config.id} needs its master password`);
    parts.push(await derivePasswordKey(config.id, encryption.kdf, password));
  }
  return hkdfDeriveKey(Buffer.concat(parts), new Uint8Array(0), `${FIELD_KEY_INFO}${config.id}`);
}

// ─── Blob primitives ────────────────────────────────────────────────────

/** AES-256-GCM of `plaintext` under `key` with `aad` authenticated: base64(iv + ciphertext + tag). */
export function sealString(key: CryptoKey, plaintext: string, aad: string): Promise<string> {
  const encoder = new TextEncoder();
  return aesEncryptToString(key, encoder.encode(plaintext), encoder.encode(aad));
}

/** The inverse of `sealString`; rejects when the key or the AAD differs, or the bytes were changed. */
export async function openString(key: CryptoKey, sealed: string, aad: string): Promise<string> {
  const plain = await aesDecryptFromString(key, sealed, new TextEncoder().encode(aad));
  return new TextDecoder().decode(plain);
}
