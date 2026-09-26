/**
 * Selective Encryption (envelope v3, reading v2 for one release).
 *
 * Separates config into a plaintext envelope (with per-field HMAC commitments) and an encrypted blob
 * carrying every other key of the `FullConfig` (config-schema/payload.ts decides what that is: the
 * whole synced document).
 *
 * The server reads the envelope for authorization, versioning, and precondition enforcement. It
 * never sees the blob's plaintext, and in v3 it no longer sees the document's pointer names either:
 * commitment keys are blinded (commitments.ts).
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
import { ENVELOPE_FIELDS, ENVELOPE_VERSION, LEGACY_ENVELOPE_VERSION } from './constants.js';
import { ConfigIntegrityError } from './errors.js';
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
]);

const AAD_DOMAIN = new TextEncoder().encode('rediacc-config-aad-v3\0');

/** A pointer/value pair, committed (or tombstoned) by its HMAC. */
interface CommitEntry {
  pointer: string;
  value: unknown;
}

/**
 * The envelope the server holds for the config being pushed, as this device last saw it: needed to
 * delete a committed path (a tombstone is the STORED commitment, recomputed under the stored salt)
 * and, on a v2 store, to hand the server the v2 -> v3 key map.
 */
export interface PriorEnvelope {
  envelopeVersion: 2 | 3;
  /** The stored envelope's `commitments.fckSalt`. */
  fckSalt: string;
  /** The committed paths this push drops, each with the value the device saw (the proof input). */
  removed: CommitEntry[];
}

/**
 * Options for envelope v3 construction.
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
  const out = new Uint8Array(AAD_DOMAIN.length + body.length);
  out.set(AAD_DOMAIN, 0);
  out.set(body, AAD_DOMAIN.length);
  return out;
}

/** The tombstones and (on a v2 store) the key map a push hands the server; see commitments.ts. */
async function priorBlocks(
  cek: CryptoKey,
  blindingKey: CryptoKey,
  prior: PriorEnvelope,
  committed: CommitEntry[]
): Promise<Pick<FieldCommitments, 'removed' | 'migrated'>> {
  const out: Pick<FieldCommitments, 'removed' | 'migrated'> = {};
  const storedIsV3 = prior.envelopeVersion === ENVELOPE_VERSION;
  if (prior.removed.length > 0) {
    const storedFck = await deriveFieldCommitmentKey(cek, prior.fckSalt);
    const removed: Record<string, FieldCommitment> = {};
    for (const { pointer, value } of prior.removed) {
      const key = storedIsV3 ? await blindPointer(blindingKey, pointer) : pointer;
      removed[key] = await commitField(storedFck, pointer, value);
    }
    out.removed = removed;
  }
  if (!storedIsV3) {
    const migrated: Record<string, string> = {};
    for (const { pointer } of committed)
      migrated[pointer] = await blindPointer(blindingKey, pointer);
    out.migrated = migrated;
  }
  return out;
}

/** The plaintext envelope of `config`, sealed as envelope v3. */
function envelopeOf(
  config: FullConfig,
  sdkEpoch: number,
  commitments: FieldCommitments
): ConfigEnvelope {
  const envelope: ConfigEnvelope = {
    envelopeVersion: ENVELOPE_VERSION,
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
 * Encrypt a full config into a v3 envelope + encrypted blob.
 */
export async function selectiveEncrypt(
  config: FullConfig,
  sdkDerived: CryptoKey,
  cek: CryptoKey,
  options: SelectiveEncryptOptions
): Promise<EncryptedConfigPayload> {
  const fckSalt = options.fckSalt ?? generateFckSalt();
  const fck = await deriveFieldCommitmentKey(cek, fckSalt);
  const blindingKey = await derivePointerBlindingKey(cek, config.id);
  const commitments = await computeCommitments(fck, fckSalt, options.commitEntries, blindingKey);
  const envelope = envelopeOf(config, options.sdkEpoch, commitments);

  const aad = await envelopeAad(
    { storeId: options.storeId, configId: config.id, teamId: config.teamId ?? null },
    envelope
  );
  const encryptedBlob = await configEncrypt(
    JSON.stringify(blobSections(config)),
    sdkDerived,
    cek,
    aad
  );

  // The push-only blocks go on AFTER the AAD: they are not commitment state, and the server drops them.
  if (options.prior) {
    Object.assign(
      commitments,
      await priorBlocks(cek, blindingKey, options.prior, options.commitEntries)
    );
  }

  return { envelope, encryptedBlob };
}

/**
 * Decrypt an encrypted config payload back into a full config.
 *
 * A v3 envelope opens only under the reader's own `binding` (see the header); a v2 envelope, read
 * for one release (ruling D2), opens under its blob HMAC and carries no binding. The caller decides
 * what a v2 read may do (the CLI warns, and refuses one after it has seen v3 for the config). Any
 * other version is refused.
 *
 * @throws ConfigIntegrityError when the blob is not the one sealed for `binding` and this envelope,
 *   or not sealed under `cek`.
 */
export async function selectiveDecrypt(
  payload: EncryptedConfigPayload,
  cek: CryptoKey,
  sdkDerived: CryptoKey,
  binding: ConfigBinding
): Promise<FullConfig> {
  const version = payload.envelope.envelopeVersion as number;
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
  } else {
    throw new Error(
      `Unsupported envelope version: ${String((payload.envelope as { envelopeVersion?: unknown }).envelopeVersion)}. This client reads envelope v${LEGACY_ENVELOPE_VERSION} and v${ENVELOPE_VERSION}.`
    );
  }

  const sensitive = JSON.parse(sensitiveJson) as ConfigSensitiveData;
  return {
    ...payload.envelope,
    ...sensitive,
    // The id is the one the reader asked for (and, in v3, the one the AAD proved).
    id: binding.configId,
  };
}
