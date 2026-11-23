/**
 * Selective Encryption (envelope v3 and v4, reading v2 for one release).
 *
 * Separates config into a plaintext envelope (with per-field HMAC commitments) and an encrypted blob
 * carrying every other key of the `FullConfig` (config-schema/payload.ts decides what that is: the
 * whole synced document).
 *
 * The server reads the envelope for authorization, versioning, and precondition enforcement. It
 * never sees the blob's plaintext, and since v3 it no longer sees the document's pointer names
 * either: commitment keys are blinded (commitments.ts).
 *
 * ─── Binding (envelope v3) ─────────────────────────────────────────────────
 * Both AES-GCM layers authenticate `envelopeAad(binding, envelope)`:
 *
 *   'rediacc-config-aad-v3' NUL canonical({
 *     v: 3, storeId, configId, teamId | null, version, sdkEpoch,
 *     commitments: SHA-256(canonical({ alg, fckSalt, fields })),
 *   })
 *
 * A reader rebuilds it from its own pointer (`ConfigBinding`) plus the envelope it was handed, so a
 * blob served for another config or team, under another version or epoch, or next to edited
 * commitments, fails the CEK layer's tag (F1). The version is therefore authentic, which is what
 * makes a client-side high-water mark meaningful. The v2 blob HMAC is retired: it authenticated the
 * blob bytes only, which the GCM tag already does, and it used the raw CEK as an HMAC key (F15).
 *
 * ─── Per-config content key (envelope v4, D56) ─────────────────────────────
 * A v4 blob is sealed under the config's own content key (config-key.ts), which the envelope carries
 * wrapped under the CEK (`wrappedConfigKey`, `configKeyVersion`, `cekGeneration`). The blob AAD is
 * the v3 one under the domain 'rediacc-config-aad-v4' with `v: 4` and `configKeyVersion` added. The
 * field-commitment key and the pointer-blinding key derive from the content key, not the CEK, so a
 * holder of one config's content key (an agent grant) reads and writes that config and no other.
 */

import { canonicalize } from './canonical.js';
import {
  blindPointer,
  commitField,
  commitmentsDigest,
  computeCommitments,
  deriveFieldCommitmentKey,
  derivePointerBlindingKey,
  type FieldCommitment,
  type FieldCommitments,
  generateFckSalt,
} from './commitments.js';
import { type ConfigContentKey, unwrapConfigKey, wrapConfigKey } from './config-key.js';
import {
  CONFIG_KEY_ENVELOPE_VERSION,
  ENVELOPE_FIELDS,
  ENVELOPE_VERSION,
  LEGACY_ENVELOPE_VERSION,
} from './constants.js';
import { ConfigEnvelopeTooNewError, ConfigIntegrityError } from './errors.js';
import { hmacVerify } from './hmac.js';
import { configDecrypt, configEncrypt } from './layers.js';
import type {
  ConfigBinding,
  ConfigEnvelope,
  ConfigSensitiveData,
  EncryptedConfigPayload,
  FullConfig,
} from './types.js';

/** The plaintext envelope's keys; everything else in a FullConfig is encrypted. */
const ENVELOPE_KEYS: ReadonlySet<string> = new Set<string>([
  ...ENVELOPE_FIELDS,
  'envelopeVersion',
  'commitments',
  'wrappedConfigKey',
  'configKeyVersion',
  'cekGeneration',
]);

const AAD_DOMAIN = new TextEncoder().encode('rediacc-config-aad-v3\0');
const AAD_DOMAIN_V4 = new TextEncoder().encode('rediacc-config-aad-v4\0');

/** A pointer/value pair, committed (or tombstoned) by its HMAC. */
interface CommitEntry {
  pointer: string;
  value: unknown;
}

/**
 * The envelope the server holds for the config being pushed, as this device last saw it: needed to
 * delete a committed path (a tombstone is the STORED commitment, recomputed under the stored salt)
 * and, when the stored envelope keys its commitments differently from the one pushed (a v2 or v3
 * store pushed as v4, or a v4 store whose content key rotates), to hand the server the key map.
 */
export interface PriorEnvelope {
  envelopeVersion: 2 | 3 | 4;
  /** The stored envelope's `commitments.fckSalt`. */
  fckSalt: string;
  /** The committed paths this push drops, each with the value the device saw (the proof input). */
  removed: CommitEntry[];
  /**
   * A v4 store only: the content key the stored envelope was sealed under, when it differs from the
   * one this push uses (a content-key rotation). Omitted, the push's own content key is assumed.
   */
  configKey?: CryptoKey;
}

/**
 * Options for envelope construction.
 *
 * `fckSalt` may be reused across pushes or regenerated on each push (the default): a fresh salt
 * keeps the server from telling which values changed between versions.
 *
 * `commitEntries` are the `{pointer, value}` pairs to commit; the caller selects them with the
 * schema walker (packages/shared/src/config-schema/walker.ts::pathsToCommit).
 */
export interface SelectiveEncryptOptions {
  sdkEpoch: number;
  /** The store the config lives in: part of the AAD binding. */
  storeId: string;
  /** Reuse a prior salt, or omit to generate a fresh one. */
  fckSalt?: string;
  /** Pointers + values whose HMACs are stored in the envelope. */
  commitEntries: CommitEntry[];
  /** What the server holds now; omitted for a first push (nothing to delete or migrate). */
  prior?: PriorEnvelope;
  /**
   * The config's content key: present, the push is sealed as envelope v4 under it (the key unwrapped
   * from the pulled envelope, or a fresh `generateConfigKey()` at version 1 for a config's first v4
   * push). Absent, the push is envelope v3 under the CEK.
   */
  configKey?: ConfigContentKey;
}

function withDomain(domain: Uint8Array, body: Uint8Array): Uint8Array {
  const out = new Uint8Array(domain.length + body.length);
  out.set(domain, 0);
  out.set(body, domain.length);
  return out;
}

/**
 * The additional authenticated data of an envelope v3 blob: the binding the reader expects plus the
 * envelope fields that decide what the blob means (version, epoch, commitment state).
 */
export async function envelopeAad(
  binding: ConfigBinding,
  envelope: Pick<ConfigEnvelope, 'version' | 'sdkEpoch' | 'commitments'>
): Promise<Uint8Array> {
  const body = canonicalize({
    v: ENVELOPE_VERSION,
    storeId: binding.storeId,
    configId: binding.configId,
    teamId: binding.teamId ?? null,
    version: envelope.version,
    sdkEpoch: envelope.sdkEpoch,
    commitments: await commitmentsDigest(envelope.commitments),
  });
  return withDomain(AAD_DOMAIN, body);
}

/** The additional authenticated data of an envelope v4 blob: the v3 fields plus `configKeyVersion`. */
export async function envelopeAadV4(
  binding: ConfigBinding,
  envelope: Pick<ConfigEnvelope, 'version' | 'sdkEpoch' | 'commitments'> & {
    configKeyVersion: number;
  }
): Promise<Uint8Array> {
  const body = canonicalize({
    v: CONFIG_KEY_ENVELOPE_VERSION,
    storeId: binding.storeId,
    configId: binding.configId,
    teamId: binding.teamId ?? null,
    version: envelope.version,
    sdkEpoch: envelope.sdkEpoch,
    configKeyVersion: envelope.configKeyVersion,
    commitments: await commitmentsDigest(envelope.commitments),
  });
  return withDomain(AAD_DOMAIN_V4, body);
}

/** The keys a commitment map is derived under: the CEK through v3, the content key in v4. */
interface CommitmentKeys {
  /** Root of the field-commitment key and the pointer-blinding key. */
  root: CryptoKey;
  /** Whether pointers are blinded (v3 and v4) or stored plain (v2). */
  blinded: boolean;
}

async function sameKey(a: CryptoKey, b: CryptoKey): Promise<boolean> {
  if (a === b) return true;
  const [ra, rb] = await Promise.all([
    crypto.subtle.exportKey('raw', a),
    crypto.subtle.exportKey('raw', b),
  ]);
  const x = new Uint8Array(ra);
  const y = new Uint8Array(rb);
  return x.length === y.length && x.every((byte, i) => byte === y[i]);
}

/** The keys the STORED envelope's commitments are under. */
function storedCommitmentKeys(
  cek: CryptoKey,
  prior: PriorEnvelope,
  pushRoot: CryptoKey
): CommitmentKeys {
  if (prior.envelopeVersion === LEGACY_ENVELOPE_VERSION) return { root: cek, blinded: false };
  if (prior.envelopeVersion === ENVELOPE_VERSION) return { root: cek, blinded: true };
  return { root: prior.configKey ?? pushRoot, blinded: true };
}

/** The tombstones and, when the stored keys differ from the pushed ones, the key map; see commitments.ts. */
async function priorBlocks(
  cek: CryptoKey,
  configId: string,
  push: CommitmentKeys,
  prior: PriorEnvelope,
  committed: CommitEntry[]
): Promise<Pick<FieldCommitments, 'removed' | 'migrated'>> {
  const out: Pick<FieldCommitments, 'removed' | 'migrated'> = {};
  const stored = storedCommitmentKeys(cek, prior, push.root);
  const storedBlinding = stored.blinded
    ? await derivePointerBlindingKey(stored.root, configId)
    : null;
  const storedKeyOf = (pointer: string): Promise<string> | string =>
    storedBlinding ? blindPointer(storedBlinding, pointer) : pointer;

  if (prior.removed.length > 0) {
    const storedFck = await deriveFieldCommitmentKey(stored.root, prior.fckSalt);
    const removed: Record<string, FieldCommitment> = {};
    for (const { pointer, value } of prior.removed) {
      removed[await storedKeyOf(pointer)] = await commitField(storedFck, pointer, value);
    }
    out.removed = removed;
  }

  const keysMatch = stored.blinded && (await sameKey(stored.root, push.root));
  if (!keysMatch) {
    const pushBlinding = await derivePointerBlindingKey(push.root, configId);
    const migrated: Record<string, string> = {};
    for (const { pointer } of committed) {
      migrated[await storedKeyOf(pointer)] = await blindPointer(pushBlinding, pointer);
    }
    out.migrated = migrated;
  }
  return out;
}

/** The plaintext envelope of `config`, sealed as `envelopeVersion`. */
function envelopeOf(
  config: FullConfig,
  envelopeVersion: 3 | 4,
  sdkEpoch: number,
  commitments: FieldCommitments
): ConfigEnvelope {
  const envelope: ConfigEnvelope = {
    envelopeVersion,
    id: config.id,
    version: config.version,
    sdkEpoch,
    commitments,
  };
  if (config.teamId) envelope.teamId = config.teamId;
  if (config.orgId) envelope.orgId = config.orgId;
  if (config.lastModified) envelope.lastModified = config.lastModified;
  return envelope;
}

/**
 * Every key that is not envelope rides in the blob. The projection (toFullConfig) is where the one
 * exclusion list applies; a second list here is how `policy` once never reached the executor.
 */
function blobSections(config: FullConfig): ConfigSensitiveData {
  const sensitive: ConfigSensitiveData = {};
  for (const [field, value] of Object.entries(config)) {
    if (ENVELOPE_KEYS.has(field)) continue;
    // Omit-if-undefined, never write an undefined-valued key: the sensitivity walker treats a present-but-undefined key as a committed pointer, so a config rebuilt from this object would commit a path the blob cannot back.
    if (value !== undefined) sensitive[field] = value;
  }
  return sensitive;
}

/**
 * Encrypt a full config into an envelope + encrypted blob: v4 under `options.configKey` when given,
 * else v3 under the CEK.
 */
export async function selectiveEncrypt(
  config: FullConfig,
  sdkDerived: CryptoKey,
  cek: CryptoKey,
  options: SelectiveEncryptOptions
): Promise<EncryptedConfigPayload> {
  const configKey = options.configKey;
  const push: CommitmentKeys = { root: configKey ? configKey.key : cek, blinded: true };
  const fckSalt = options.fckSalt ?? generateFckSalt();
  const fck = await deriveFieldCommitmentKey(push.root, fckSalt);
  const blindingKey = await derivePointerBlindingKey(push.root, config.id);
  const commitments = await computeCommitments(fck, fckSalt, options.commitEntries, blindingKey);
  const binding: ConfigBinding = {
    storeId: options.storeId,
    configId: config.id,
    teamId: config.teamId ?? null,
  };
  const plaintext = JSON.stringify(blobSections(config));

  let envelope: ConfigEnvelope;
  let encryptedBlob: string;
  if (configKey) {
    envelope = envelopeOf(config, CONFIG_KEY_ENVELOPE_VERSION, options.sdkEpoch, commitments);
    envelope.configKeyVersion = configKey.version;
    envelope.cekGeneration = configKey.cekGeneration;
    envelope.wrappedConfigKey = await wrapConfigKey(configKey.key, cek, {
      ...binding,
      configKeyVersion: configKey.version,
      cekGeneration: configKey.cekGeneration,
    });
    const aad = await envelopeAadV4(binding, {
      version: envelope.version,
      sdkEpoch: envelope.sdkEpoch,
      commitments,
      configKeyVersion: configKey.version,
    });
    encryptedBlob = await configEncrypt(plaintext, sdkDerived, configKey.key, aad);
  } else {
    envelope = envelopeOf(config, ENVELOPE_VERSION, options.sdkEpoch, commitments);
    encryptedBlob = await configEncrypt(
      plaintext,
      sdkDerived,
      cek,
      await envelopeAad(binding, envelope)
    );
  }

  // The push-only blocks go on AFTER the AAD: they are not commitment state, and the server drops them.
  if (options.prior) {
    Object.assign(
      commitments,
      await priorBlocks(cek, config.id, push, options.prior, options.commitEntries)
    );
  }

  return { envelope, encryptedBlob };
}

function mergeDecrypted(
  payload: EncryptedConfigPayload,
  sensitiveJson: string,
  binding: ConfigBinding
): FullConfig {
  const sensitive = JSON.parse(sensitiveJson) as ConfigSensitiveData;
  return {
    ...payload.envelope,
    ...sensitive,
    // The id is the one the reader asked for (and, since v3, the one the AAD proved).
    id: binding.configId,
  };
}

/** The v4 key fields of an envelope, or a ConfigIntegrityError when one is missing or malformed. */
function v4Fields(envelope: ConfigEnvelope): {
  wrappedConfigKey: string;
  configKeyVersion: number;
  cekGeneration: number;
} {
  const { wrappedConfigKey, configKeyVersion, cekGeneration } = envelope;
  if (
    typeof wrappedConfigKey !== 'string' ||
    wrappedConfigKey.length === 0 ||
    !Number.isInteger(configKeyVersion) ||
    !Number.isInteger(cekGeneration)
  ) {
    throw new ConfigIntegrityError(
      'Config integrity check failed: an envelope v4 must carry wrappedConfigKey, configKeyVersion and cekGeneration.'
    );
  }
  return {
    wrappedConfigKey,
    configKeyVersion: configKeyVersion as number,
    cekGeneration: cekGeneration as number,
  };
}

/**
 * Unwrap a v4 envelope's content key with the CEK, bound to the reader's own pointer.
 *
 * @throws ConfigIntegrityError when the envelope is not v4-shaped or the wrap does not open.
 */
export function unwrapEnvelopeConfigKey(
  envelope: ConfigEnvelope,
  cek: CryptoKey,
  binding: ConfigBinding
): Promise<CryptoKey> {
  const fields = v4Fields(envelope);
  return unwrapConfigKey(fields.wrappedConfigKey, cek, {
    storeId: binding.storeId,
    configId: binding.configId,
    teamId: binding.teamId ?? null,
    configKeyVersion: fields.configKeyVersion,
    cekGeneration: fields.cekGeneration,
  });
}

/**
 * Open an envelope v4 payload with the config's content key alone: the reader that holds one
 * config's key and not the CEK (an agent grant). Refuses any other envelope version.
 *
 * @throws ConfigIntegrityError when the blob is not the one sealed for `binding`, this envelope and
 *   this content key.
 */
export async function selectiveDecryptWithConfigKey(
  payload: EncryptedConfigPayload,
  configKey: CryptoKey,
  sdkDerived: CryptoKey,
  binding: ConfigBinding
): Promise<FullConfig> {
  const version = payload.envelope.envelopeVersion as number;
  if (version !== CONFIG_KEY_ENVELOPE_VERSION) {
    throw new Error(
      `A content key opens only envelope v${CONFIG_KEY_ENVELOPE_VERSION} (got v${String(version)}).`
    );
  }
  const { configKeyVersion } = v4Fields(payload.envelope);
  const aad = await envelopeAadV4(binding, {
    version: payload.envelope.version,
    sdkEpoch: payload.envelope.sdkEpoch,
    commitments: payload.envelope.commitments,
    configKeyVersion,
  });
  const sensitiveJson = await configDecrypt(payload.encryptedBlob, configKey, sdkDerived, aad);
  return mergeDecrypted(payload, sensitiveJson, binding);
}

/**
 * Decrypt an encrypted config payload back into a full config.
 *
 * A v4 envelope opens through its content key, unwrapped with `cek` under the reader's own
 * `binding`; a v3 envelope opens under `cek` and `binding` directly; a v2 envelope, read for one
 * release (ruling D2), opens under its blob HMAC and carries no binding. The caller decides what a v2
 * read may do (the CLI warns, and refuses one after it has seen v3 for the config). Any other
 * version is refused.
 *
 * @throws ConfigIntegrityError when the blob is not the one sealed for `binding` and this envelope,
 *   or not sealed under `cek` (or, in v4, under the content key `cek` wraps).
 */
export async function selectiveDecrypt(
  payload: EncryptedConfigPayload,
  cek: CryptoKey,
  sdkDerived: CryptoKey,
  binding: ConfigBinding
): Promise<FullConfig> {
  const version = payload.envelope.envelopeVersion as number;
  if (version === CONFIG_KEY_ENVELOPE_VERSION) {
    const configKey = await unwrapEnvelopeConfigKey(payload.envelope, cek, binding);
    return selectiveDecryptWithConfigKey(payload, configKey, sdkDerived, binding);
  }
  let sensitiveJson: string;
  if (version === ENVELOPE_VERSION) {
    const aad = await envelopeAad(binding, payload.envelope);
    sensitiveJson = await configDecrypt(payload.encryptedBlob, cek, sdkDerived, aad);
  } else if (version === LEGACY_ENVELOPE_VERSION) {
    const hmacValid =
      typeof payload.hmac === 'string' &&
      payload.hmac.length > 0 &&
      (await hmacVerify(payload.encryptedBlob, cek, payload.hmac));
    if (!hmacValid) throw new ConfigIntegrityError();
    sensitiveJson = await configDecrypt(payload.encryptedBlob, cek, sdkDerived);
  } else if (typeof version === 'number' && version > CONFIG_KEY_ENVELOPE_VERSION) {
    throw new ConfigEnvelopeTooNewError(version);
  } else {
    throw new Error(
      `Unsupported envelope version: ${String((payload.envelope as { envelopeVersion?: unknown }).envelopeVersion)}. This client reads envelope v${LEGACY_ENVELOPE_VERSION} to v${CONFIG_KEY_ENVELOPE_VERSION}.`
    );
  }
  return mergeDecrypted(payload, sensitiveJson, binding);
}
