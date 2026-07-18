/**
 * Config Storage Encryption Constants
 */

/** Default SDK time window in seconds (5 minutes) */
export const SDK_WINDOW_SECONDS = 300;

/** HKDF info strings — domain separation for different derivations */
export const HKDF_INFO = {
  SDK_DERIVE: 'rediacc-config-sdk-v1',
  WRAPPING_KEY: 'rediacc-config-wrapping-key-v1',
  FIELD_COMMITMENT: 'rediacc-config-fck-v1',
  RECOVERY_SLOT: 'rediacc-recovery-slot-v1',
} as const;

/**
 * The ONE canonical passkey PRF evaluation salt.
 *
 * Every PRF ceremony (setup, unlock, member add/accept, rotation) must evaluate
 * the passkey with this exact salt, or it derives a different passkey_secret
 * and the wrapped CEK becomes garbage. v1 shipped with two divergent literals
 * ('rediacc-secret-v1' at setup vs 32 zero bytes at unlock/rotate), which is
 * exactly the failure this constant exists to make impossible.
 */
export const PRF_EVAL_SALT_VALUE = 'rediacc-prf-eval-v2';

/** UTF-8 bytes of {@link PRF_EVAL_SALT_VALUE}, as the WebAuthn prf.eval input wants. */
export function prfEvalSalt(): Uint8Array {
  return new TextEncoder().encode(PRF_EVAL_SALT_VALUE);
}

/** HMAC info */
export const HMAC_ALGORITHM = 'SHA-256';

/** Config envelope fields — stored in plaintext for server-side operations */
export const ENVELOPE_FIELDS = [
  'id',
  'version',
  'teamId',
  'orgId',
  'lastModified',
  'sdkEpoch',
] as const;

/**
 * Config sensitive fields — encrypted with triple-layer encryption.
 *
 * `policy` belongs here even though it holds no credential. The authorization
 * rules are what the executor enforces, and the executor can only ever see what
 * the blob carries: a field left out of this list is dropped on push and is
 * simply absent on pull. Omitting `policy` is what made every store-backed
 * deployment silently fall back to the missing-document default, with the rules
 * an org had authored never reaching the thing that enforces them.
 *
 * Encrypting it also keeps the rules unreadable to us, which is the claim the
 * whole enforcement story rests on.
 */
export const SENSITIVE_FIELDS = [
  // Top-level sections with committed pointers (/account/userEmail,
  // /defaults/universalUser, /infra/certEmail, /infra/cfDnsZoneId). The CLI
  // pushes its on-disk document with only `state` stripped, so these pointers
  // enter every push's commitment set — leaving the sections out of the blob
  // made the next editor re-push commit fewer pointers and fail the server's
  // anti-downgrade check ("someone else changed this config").
  //
  // Deliberately NOT here: `remote` (host-local store pointer, commit:false in
  // the sensitivity registry — not synced, therefore not committed), `state`
  // (runtime half, stripped before push), `encryption` (host-local at-rest
  // metadata), `renetPath` (host-local binary override, public/uncommitted).
  'account',
  'defaults',
  'infra',
  'machines',
  'repositories',
  'storages',
  // The remaining v3 resource families. Their leaves are public topology (no
  // committed secrets except deletedRepositories below), but a family absent
  // from this list is silently dropped on push and simply absent on pull —
  // which is real data loss for anyone syncing datastore/cluster/backup
  // definitions through the store.
  'datastores',
  'clusters',
  'backupStrategies',
  // Archived repos carry COMMITTED credential pointers (sensitivity registry:
  // /resources/deletedRepositories/*/credential, sshPrivateKey). Committed
  // means it must travel, or the round trip drops the values and the re-push
  // commits fewer pointers than the server expects — anti-downgrade bricks
  // config push for the org.
  'deletedRepositories',
  'ssh',
  'policy',
  // Org secrets that the sensitivity registry COMMITS. Anything committed must
  // also travel in the blob, or a push/rotation round trip drops it: the secret
  // is lost, and the re-push commits fewer pointers than before, which the
  // server's anti-downgrade check rejects — bricking config push for the org.
  // The invariant "commit set == round-trip-surviving set" is pinned by
  // config-schema/__tests__/commit-encrypt-parity.test.ts.
  'cloudProviders',
  'cfDnsApiToken',
] as const;

/** Re-export shared encryption constants */
export { ENCRYPTION_CONFIG } from '../encryption/constants.js';
