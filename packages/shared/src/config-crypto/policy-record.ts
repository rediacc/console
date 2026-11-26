/**
 * The policy record: the authorization policy of one config entry, sealed in its own record instead
 * of inside the config blob (agent/plans/PLAN-rmcp-policy-record.md Design 1).
 *
 * The record travels as `{version, cekGeneration, blob}` (Design 3), with no SDK epoch, so the blob
 * is one AES-256-GCM layer; the server adds the org-passphrase layer at rest as it does for configs.
 *
 * KEY. The blob is sealed under a per-pointer policy key derived from the store CEK
 * (agent/plans/PLAN-rmcp-agent-grants.md AG-P1):
 *
 *   policyKey = HKDF-SHA256(CEK, salt = empty,
 *                 info = 'rediacc-policy-key-v1' NUL canonical({ storeId, configId, teamId | null, cekGeneration }))
 *
 * A holder of the CEK derives it on the spot, so every caller still passes the CEK. A holder of one
 * derived key (an agent grant carries the keys of its own team config and of the org-level config,
 * agent-grant.ts) opens that pointer's records under that generation and no other, and never learns
 * the CEK.
 *
 * AAD. The AAD binds the blob to its record:
 *
 *   'rediacc-policy-aad-v2' NUL canonical({ v: 2, storeId, configId, teamId | null, version, cekGeneration })
 *
 * A reader rebuilds it from its OWN pointer plus the version and generation the record carries, so
 * a blob served for another store, config or team, under another version (a replay of an older
 * record under a newer number) or another CEK generation fails the GCM tag. The version is
 * therefore authentic, which is what makes a client-side high-water mark meaningful. A v1 blob
 * (sealed under the CEK itself with the v1 AAD) does not open: clean break.
 *
 * Like the rest of config-crypto this module does not know the policy shape: it seals and opens a
 * JSON value, and the caller parses it with `PolicyDocumentSchema` (packages/shared/src/policy).
 */

import { aesDecryptFromString, aesEncryptToString, exportAesKey, importAesKey } from './aes.js';
import { canonicalize } from './canonical.js';

const POLICY_AAD_DOMAIN = new TextEncoder().encode('rediacc-policy-aad-v2\0');
const POLICY_KEY_DOMAIN = new TextEncoder().encode('rediacc-policy-key-v1\0');

/** Extract ArrayBuffer from Uint8Array for Web Crypto API compatibility. */
function buf(data: Uint8Array): ArrayBuffer {
  if (data.byteOffset === 0 && data.byteLength === data.buffer.byteLength) {
    return data.buffer as ArrayBuffer;
  }
  return data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength) as ArrayBuffer;
}

function concat(a: Uint8Array, b: Uint8Array): Uint8Array {
  const out = new Uint8Array(a.byteLength + b.byteLength);
  out.set(a, 0);
  out.set(b, a.byteLength);
  return out;
}

/** What a policy blob is sealed for. */
export interface PolicyRecordBinding {
  storeId: string;
  configId: string;
  /** The config's team, or null/absent for the org-level config. */
  teamId?: string | null;
  /** The record version the blob is written as (1 for the first save). */
  version: number;
  /** The store's CEK generation the blob is sealed under. */
  cekGeneration: number;
}

/** What a policy key is derived for: one record pointer under one CEK generation. */
export interface PolicyKeyBinding {
  storeId: string;
  configId: string;
  /** The config's team, or null/absent for the org-level config. */
  teamId?: string | null;
  /** The store's CEK generation the key is derived for. */
  cekGeneration: number;
}

/**
 * A derived policy key: opens the records of one pointer under one CEK generation. Tagged so that
 * `decryptPolicyRecord` tells it apart from a CEK, which is an AES-GCM key of the same shape.
 */
export interface PolicyKey {
  readonly kind: 'policy-key';
  readonly key: CryptoKey;
}

/** The record as the account server stores and serves it (Design 3). */
export interface PolicyRecord {
  version: number;
  cekGeneration: number;
  blob: string;
}

/**
 * The policy blob did not open under this key and binding: another store, config, team, version or
 * CEK generation, a different key, a v1 blob, or a damaged blob.
 */
export class PolicyRecordIntegrityError extends Error {
  constructor(
    message = 'Policy record integrity check failed: the record was not sealed for this config, version and key.'
  ) {
    super(message);
    this.name = 'PolicyRecordIntegrityError';
  }
}

function assertGeneration(cekGeneration: number): void {
  if (!Number.isInteger(cekGeneration) || cekGeneration < 0) {
    throw new Error(
      `Policy record cekGeneration must be a non-negative integer (got ${cekGeneration})`
    );
  }
}

function assertBinding(binding: PolicyRecordBinding): void {
  if (!Number.isInteger(binding.version) || binding.version < 1) {
    throw new Error(`Policy record version must be a positive integer (got ${binding.version})`);
  }
  assertGeneration(binding.cekGeneration);
}

/** The additional authenticated data of a policy blob (see the header). */
export function policyRecordAad(binding: PolicyRecordBinding): Uint8Array {
  assertBinding(binding);
  const body = canonicalize({
    v: 2,
    storeId: binding.storeId,
    configId: binding.configId,
    teamId: binding.teamId ?? null,
    version: binding.version,
    cekGeneration: binding.cekGeneration,
  });
  return concat(POLICY_AAD_DOMAIN, body);
}

/** The HKDF info of a policy key (see the header). */
export function policyKeyInfo(binding: PolicyKeyBinding): Uint8Array {
  assertGeneration(binding.cekGeneration);
  const body = canonicalize({
    storeId: binding.storeId,
    configId: binding.configId,
    teamId: binding.teamId ?? null,
    cekGeneration: binding.cekGeneration,
  });
  return concat(POLICY_KEY_DOMAIN, body);
}

/**
 * Derive the policy key of one pointer from the CEK (see the header). The key is extractable so the
 * browser can wrap it for an agent grant (agent-grant.ts `wrapPolicyKeyForAgentGrant`).
 */
export async function derivePolicyKey(
  cek: CryptoKey,
  binding: PolicyKeyBinding
): Promise<PolicyKey> {
  const info = policyKeyInfo(binding);
  const raw = await exportAesKey(cek);
  try {
    const ikm = await crypto.subtle.importKey('raw', buf(raw), 'HKDF', false, ['deriveBits']);
    const bits = new Uint8Array(
      await crypto.subtle.deriveBits(
        { name: 'HKDF', hash: 'SHA-256', salt: new ArrayBuffer(0), info: buf(info) },
        ikm,
        256
      )
    );
    try {
      return { kind: 'policy-key', key: await importAesKey(bits) };
    } finally {
      bits.fill(0);
    }
  } finally {
    raw.fill(0);
  }
}

function isPolicyKey(key: CryptoKey | PolicyKey): key is PolicyKey {
  return (key as Partial<PolicyKey>).kind === 'policy-key';
}

/**
 * Seal a policy document (any JSON value) for `binding`, under the policy key derived from `cek`.
 * Returns the record to PUT. Sealing takes the CEK only: a derived key opens records, never writes.
 */
export async function encryptPolicyRecord(
  document: unknown,
  cek: CryptoKey,
  binding: PolicyRecordBinding
): Promise<PolicyRecord> {
  const aad = policyRecordAad(binding);
  const { key } = await derivePolicyKey(cek, binding);
  const blob = await aesEncryptToString(
    key,
    new TextEncoder().encode(JSON.stringify(document)),
    aad
  );
  return { version: binding.version, cekGeneration: binding.cekGeneration, blob };
}

/**
 * Open a pulled policy record. The store, config and team come from the reader's own pointer; the
 * version and generation come from the record and are authenticated by the tag.
 *
 * `key` is either the CEK, from which the pointer's policy key is derived, or a policy key already
 * derived for this pointer and generation (an agent grant's, agent-grant.ts).
 *
 * @returns the parsed JSON value; the caller validates it with `PolicyDocumentSchema`.
 * @throws PolicyRecordIntegrityError when the blob does not open under `key` and that binding.
 * @throws the raw error of the key derivation when `key` is a CEK that cannot be derived from (a non-extractable one): a local failure, not a tampered record.
 */
export async function decryptPolicyRecord(
  record: PolicyRecord,
  key: CryptoKey | PolicyKey,
  pointer: Pick<PolicyRecordBinding, 'storeId' | 'configId' | 'teamId'>
): Promise<unknown> {
  let aad: Uint8Array;
  try {
    // A malformed served version or generation fails the binding check, which is a tamper signal too.
    aad = policyRecordAad({
      ...pointer,
      version: record.version,
      cekGeneration: record.cekGeneration,
    });
  } catch {
    throw new PolicyRecordIntegrityError();
  }
  // Deriving the key runs after the binding is proven well-formed and outside the try: a local failure (a non-extractable CEK) is the reader's own fault, not a tampered record.
  const policyKey = isPolicyKey(key)
    ? key.key
    : (await derivePolicyKey(key, { ...pointer, cekGeneration: record.cekGeneration })).key;
  let plaintext: Uint8Array;
  try {
    plaintext = await aesDecryptFromString(policyKey, record.blob, aad);
  } catch {
    throw new PolicyRecordIntegrityError();
  }
  return JSON.parse(new TextDecoder().decode(plaintext)) as unknown;
}
