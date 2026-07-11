/**
 * Per-field encryption-at-rest transform for the config file (v3).
 *
 * Encryption is a STORAGE-LAYER transform, not a caller behavior: every writer
 * goes through ConfigFileStorage, which decrypts on read and re-encrypts on
 * write, so no caller ever produces or sees a blob. This is the single
 * chokepoint that makes the R2-F3 data-loss class impossible — there is no
 * second "plaintext resources" path that a persist can clobber.
 *
 * Granularity is driven ENTIRELY by schema/sensitivity.ts: any leaf whose
 * registry meta has `encryptAtRest` (default true for secret/credential) is
 * moved out of the plaintext tree into `encryption.encryptedFields[pointer]`.
 * The one deliberate exception is `/credentials/masterPasswordVerifier`
 * (encryptAtRest:false) — encrypting it under the password it verifies would
 * be a bootstrapping deadlock.
 *
 * Because an encrypted leaf is ABSENT from the plaintext tree at rest, a strict
 * schema parse of the on-disk form would reject required fields (e.g. a cloud
 * provider's apiToken). `injectEncryptedStubs` hydrates each encrypted leaf with
 * a type-valid placeholder before parse so public reads succeed WITHOUT
 * prompting for the master password (spec 04 §2.4); `decryptConfigFields`
 * replaces the stubs with real values when a sensitive field is actually read.
 */

import { walkSensitive, setByPointer, getByPointer } from '../schema/walker.js';
import type { RdcConfig } from '../schema/schemas.js';
import { nodeCryptoProvider } from './crypto.js';

const STUB_PREFIX = '<encrypted:';

function isMasterPassword(config: RdcConfig): boolean {
  return config.encryption?.mode === 'master-password';
}

/** Type-valid placeholder for an encrypted leaf we have not decrypted. */
function stubFor(pointer: string): unknown {
  // vaultContent is the one object-typed encrypt-at-rest leaf; every other is a
  // string. An object stub keeps the record schema happy.
  return pointer.endsWith('/vaultContent')
    ? { __encryptedStub: pointer }
    : `${STUB_PREFIX}${pointer}>`;
}

function isStub(value: unknown): boolean {
  if (typeof value === 'string') return value.startsWith(STUB_PREFIX);
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return '__encryptedStub' in (value as Record<string, unknown>);
  }
  return false;
}

function parentPointer(pointer: string): string {
  const idx = pointer.lastIndexOf('/');
  return idx <= 0 ? '' : pointer.slice(0, idx);
}

/**
 * Fill every encrypted leaf with a type-valid stub so a strict parse of the
 * at-rest config succeeds. `encryptedFields` is left intact so a later
 * decryptConfigFields can restore the real values. No-op unless master-password.
 */
export function injectEncryptedStubs(config: RdcConfig): RdcConfig {
  if (!isMasterPassword(config)) return config;
  const fields = config.encryption?.encryptedFields;
  if (!fields) return config;

  let result: RdcConfig = config;
  for (const pointer of Object.keys(fields)) {
    if (getByPointer(result, pointer) === undefined) {
      result = setByPointer(result, pointer, stubFor(pointer)) as RdcConfig;
    }
  }
  return result;
}

/**
 * Move every encrypt-at-rest leaf into `encryption.encryptedFields` as a fresh
 * AES-GCM blob and remove it from the plaintext tree. A leaf that is still a
 * stub (never decrypted this cycle) preserves its existing blob rather than
 * encrypting the placeholder — so a save that never decrypted cannot corrupt or
 * drop encrypted data. No-op when not in master-password mode.
 */
type Blobs = Record<string, { data: string }>;

/** Encrypt a present leaf, or carry its existing blob forward if it is a stub. */
async function encryptLeaf(
  fields: Blobs,
  existing: Blobs,
  pointer: string,
  value: unknown,
  password: string
): Promise<void> {
  if (isStub(value)) {
    if (Object.hasOwn(existing, pointer)) fields[pointer] = existing[pointer];
    return;
  }
  fields[pointer] = { data: await nodeCryptoProvider.encrypt(JSON.stringify(value), password) };
}

/**
 * Preserve blobs whose leaf is absent but whose parent container still exists
 * (a writer spread the at-rest config without decrypting that leaf).
 */
function preserveAbsentBlobs(config: RdcConfig, existing: Blobs, fields: Blobs): void {
  for (const [pointer, blob] of Object.entries(existing)) {
    if (Object.hasOwn(fields, pointer)) continue;
    if (getByPointer(config, pointer) !== undefined) continue;
    if (getByPointer(config, parentPointer(pointer)) !== undefined) fields[pointer] = blob;
  }
}

export async function encryptConfigFields(config: RdcConfig, password: string): Promise<RdcConfig> {
  if (!isMasterPassword(config)) return config;
  const existing: Blobs = config.encryption?.encryptedFields ?? {};

  const leaves = [...walkSensitive(config)].filter(
    (e) => e.meta.encryptAtRest && e.value !== undefined
  );

  let result: RdcConfig = config;
  const encryptedFields: Blobs = {};
  for (const { pointer, value } of leaves) {
    await encryptLeaf(encryptedFields, existing, pointer, value, password);
    result = setByPointer(result, pointer, undefined) as RdcConfig;
  }

  preserveAbsentBlobs(result, existing, encryptedFields);
  return { ...result, encryption: { mode: 'master-password', encryptedFields } };
}

/**
 * Restore every encrypted leaf back into the plaintext tree (overwriting stubs).
 * Returns the config with `encryptedFields` cleared in memory (still mode
 * master-password so a subsequent save re-encrypts). No-op when not in
 * master-password mode or when there is nothing to decrypt.
 */
export async function decryptConfigFields(config: RdcConfig, password: string): Promise<RdcConfig> {
  if (!isMasterPassword(config)) return config;
  const encryptedFields = config.encryption?.encryptedFields;
  if (!encryptedFields || Object.keys(encryptedFields).length === 0) return config;

  let result: RdcConfig = config;
  for (const [pointer, blob] of Object.entries(encryptedFields)) {
    const json = await nodeCryptoProvider.decrypt(blob.data, password);
    result = setByPointer(result, pointer, JSON.parse(json)) as RdcConfig;
  }

  return { ...result, encryption: { mode: 'master-password', encryptedFields: {} } };
}

/**
 * Serialize-for-push view: strip the entire `state` bucket and any encrypted
 * field whose pointer targets `/state/*`. The status half never enters the
 * remote config store (spec 04 §1.3 property 1).
 */
export function stripStateForPush(config: RdcConfig): RdcConfig {
  const { state: _state, ...rest } = config;
  void _state;
  if (rest.encryption?.encryptedFields) {
    const kept: Record<string, { data: string }> = {};
    for (const [pointer, blob] of Object.entries(rest.encryption.encryptedFields)) {
      if (!pointer.startsWith('/state/')) kept[pointer] = blob;
    }
    rest.encryption = { ...rest.encryption, encryptedFields: kept };
  }
  return rest;
}
