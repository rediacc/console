/**
 * Config Storage Encryption Types
 */

import type { FieldCommitments } from './commitments.js';

/**
 * Plaintext envelope — server can read these fields without decryption.
 *
 * Every client WRITES v3 and READS v2 for one release (operator ruling D2). v3 binds the blob to
 * `(storeId, configId, teamId, version, sdkEpoch, commitments)` through the AES-GCM AAD
 * (selective.ts `envelopeAad`), retires the blob HMAC, and keys the commitments by blinded pointers
 * (commitments.ts). The server refuses a v2 push.
 *
 * Envelope v2 added per-field commitment HMACs so the server can enforce the
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
  envelopeVersion: 2 | 3;
  id: string;
  version: number;
  teamId?: string;
  orgId?: string;
  lastModified?: string;
  sdkEpoch: number;
  /**
   * Per-field commitment HMACs. Always present (v2 and v3). The server rejects any
   * push that is not v3 with HTTP 400 `unsupported_envelope_version`.
   */
  commitments: FieldCommitments;
}

/**
 * What a reader expects a pulled blob to be sealed for, taken from its OWN pointer (the CLI's
 * `remote`, the portal's store and config choice, the executor's grant), never from the pull
 * response: the envelope v3 AAD is rebuilt from it, so a blob the server serves for another store,
 * config or team does not open.
 */
export interface ConfigBinding {
  storeId: string;
  configId: string;
  /** The config's team, or null/absent for the org-level config. */
  teamId?: string | null;
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
  /**
   * Envelope v2 only: HMAC-SHA256 over encryptedBlob, keyed with the CEK. A v3 payload carries none
   * (the GCM tag under the AAD authenticates the blob AND its binding, which the HMAC never did).
   */
  hmac?: string | null;
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
