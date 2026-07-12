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
} as const;

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
  'machines',
  'repositories',
  'storages',
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
