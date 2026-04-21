/**
 * Selective Encryption (envelope v2 with field commitments).
 *
 * Separates config into a plaintext envelope (v2 — adds per-field HMAC
 * commitments) and an encrypted blob (machines, repositories, storages, ssh).
 *
 * Server reads the envelope for authorization, versioning, and precondition
 * enforcement; it never sees the encrypted blob's plaintext.
 */

import { SENSITIVE_FIELDS } from './constants.js';
import { hmacCompute, hmacVerify } from './hmac.js';
import { configDecrypt, configEncrypt } from './layers.js';
import {
  computeCommitments,
  deriveFieldCommitmentKey,
  generateFckSalt,
  type FieldCommitments,
} from './commitments.js';
import type {
  ConfigEnvelope,
  ConfigSensitiveData,
  EncryptedConfigPayload,
  FullConfig,
} from './types.js';

/**
 * Options for envelope v2 construction.
 *
 * `fckSalt` may be reused across pushes (keeps commitment HMACs stable across
 * writes that don't change sensitive values) or regenerated on each push (a
 * "salt bump" forces the client to recompute all commitments — useful when
 * rotating CEK since the FCK is derived from it).
 *
 * `commitEntries` are the `{pointer, value}` pairs to commit — caller selects
 * these using the CLI-side walker (packages/cli/src/schema/walker.ts::pathsToCommit).
 */
export interface SelectiveEncryptOptions {
  sdkEpoch: number;
  /** Reuse a prior salt, or omit to generate a fresh one. */
  fckSalt?: string;
  /** Pointers + values whose HMACs are stored in the envelope. */
  commitEntries: Array<{ pointer: string; value: unknown }>;
}

/**
 * Encrypt a full config into a v2 envelope + encrypted blob.
 */
export async function selectiveEncrypt(
  config: FullConfig,
  sdkDerived: CryptoKey,
  cek: CryptoKey,
  options: SelectiveEncryptOptions
): Promise<EncryptedConfigPayload> {
  const fckSalt = options.fckSalt ?? generateFckSalt();
  const fck = await deriveFieldCommitmentKey(cek, fckSalt);
  const commitments: FieldCommitments = await computeCommitments(
    fck,
    fckSalt,
    options.commitEntries
  );

  const envelope: ConfigEnvelope = {
    envelopeVersion: 2,
    id: config.id,
    version: config.version,
    sdkEpoch: options.sdkEpoch,
    commitments,
  };
  if (config.teamId) envelope.teamId = config.teamId;
  if (config.orgId) envelope.orgId = config.orgId;
  if (config.lastModified) envelope.lastModified = config.lastModified;

  const sensitive: ConfigSensitiveData = {};
  for (const field of SENSITIVE_FIELDS) {
    if (config[field] !== undefined) {
      sensitive[field] = config[field];
    }
  }

  const sensitiveJson = JSON.stringify(sensitive);
  const encryptedBlob = await configEncrypt(sensitiveJson, sdkDerived, cek);
  const hmac = await hmacCompute(encryptedBlob, cek);

  return { envelope, encryptedBlob, hmac };
}

/**
 * Decrypt an encrypted config payload back into a full config.
 *
 * Rejects v1 envelopes (missing `envelopeVersion` or `envelopeVersion !== 2`).
 * This is intentional — the config-store wire format is v2-only as of this
 * release; there is no dual-accept window.
 */
export async function selectiveDecrypt(
  payload: EncryptedConfigPayload,
  cek: CryptoKey,
  sdkDerived: CryptoKey
): Promise<FullConfig> {
  if (payload.envelope.envelopeVersion !== 2) {
    throw new Error(
      `Unsupported envelope version: ${String((payload.envelope as { envelopeVersion?: unknown }).envelopeVersion)}. This CLI requires envelope v2.`
    );
  }

  const hmacValid = await hmacVerify(payload.encryptedBlob, cek, payload.hmac);
  if (!hmacValid) {
    throw new Error(
      'Config integrity check failed. The encrypted data may have been corrupted or tampered with.'
    );
  }

  const sensitiveJson = await configDecrypt(payload.encryptedBlob, cek, sdkDerived);
  const sensitive = JSON.parse(sensitiveJson) as ConfigSensitiveData;

  return {
    ...payload.envelope,
    ...sensitive,
  };
}
