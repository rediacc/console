/**
 * Config Storage Encryption Types
 */

import type { FieldCommitments } from './commitments.js';

/**
 * Plaintext envelope — server can read these fields without decryption.
 *
 * Envelope v2 adds per-field commitment HMACs so the server can enforce the
 * "knowledge-gates-capability" precondition on sensitive-field mutations
 * without ever seeing plaintext. The HMAC key (FCK) is derived client-side
 * from CEK via HKDF; the server cannot derive it.
 *
 * Server-stored envelope is the source of truth for the current commitment
 * state. On push, the client may submit a `precondition.expectedCommitments`
 * block that the server compares hex-string-for-hex-string against the
 * previously-stored envelope's `commitments.fields`.
 */
export interface ConfigEnvelope {
  envelopeVersion: 2;
  id: string;
  version: number;
  teamId?: string;
  orgId?: string;
  lastModified?: string;
  sdkEpoch: number;
  /**
   * Per-field commitment HMACs. Always present in v2 envelopes. The server
   * rejects v1 envelopes with HTTP 400 UnsupportedEnvelopeVersion.
   */
  commitments: FieldCommitments;
}

/**
 * The encrypted half of a config: the whole synced document (every key except the device-local
 * pointers, `DEVICE_LOCAL_POINTERS` in config-schema/sensitivity.ts) in the v2 wire encoding, where
 * `resources.*` and `credentials.*` ride one level up. The named fields are the ones callers read
 * today; the index signature is the rest (`state`, keys a newer CLI added), all carried.
 *
 * Committed leaves (account.userEmail, defaults.universalUser, infra.*, the org secrets, archived
 * repo credentials) must travel: a committed-but-not-carried field is dropped by the first pull,
 * and the re-push then commits fewer pointers than the server stored, which anti-downgrade rejects.
 */
export interface ConfigSensitiveData {
  [section: string]: unknown;
  account?: Record<string, unknown>;
  defaults?: Record<string, unknown>;
  infra?: Record<string, unknown>;
  machines?: Record<string, unknown>;
  repositories?: Record<string, unknown>;
  storages?: Record<string, unknown>;
  datastores?: Record<string, unknown>;
  clusters?: Record<string, unknown>;
  backupStrategies?: Record<string, unknown>;
  /** Archived repositories (an ARRAY, unlike the record families). */
  deletedRepositories?: unknown[];
  ssh?: Record<string, unknown>;
  cloudProviders?: Record<string, unknown>;
  cfDnsApiToken?: unknown;
  /**
   * The authorization rules the executor enforces. Typed `unknown` on purpose: config-crypto is a
   * generic crypto library and must not learn the shape of a Rediacc policy document.
   */
  policy?: unknown;
  /** Runtime state: repo network IDs, heads, the network-ID counter (T17: synced). */
  state?: Record<string, unknown>;
}

/** Result of selective encryption: plaintext envelope + encrypted blob */
export interface EncryptedConfigPayload {
  envelope: ConfigEnvelope;
  encryptedBlob: string; // base64(clientEnc_CEK(serverKeyEnc_SDK(sensitiveData)))
  hmac: string; // HMAC-SHA256 over encryptedBlob, keyed with CEK
}

/** Full config (envelope + sensitive data merged) */
export type FullConfig = ConfigEnvelope & ConfigSensitiveData;

/** Result of AES-256-GCM encryption: IV + ciphertext (includes auth tag) */
export interface AesEncryptResult {
  iv: Uint8Array;
  ct: Uint8Array;
}

/** Serialized encrypted data: base64(iv + ct) */
export type EncryptedString = string;

/** CEK handoff blob for X25519-based member key distribution */
export interface CekHandoffBlob {
  v: number; // protocol version
  eph: string; // base64 ephemeral X25519 public key
  salt: string; // base64 HKDF salt
  iv: string; // base64 AES-GCM IV
  ct: string; // base64 AES-GCM ciphertext (encrypted CEK)
}
