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

/** Config sensitive fields — encrypted with triple-layer encryption */
export const SENSITIVE_FIELDS = ['machines', 'repositories', 'storages', 'ssh'] as const;

/** Re-export shared encryption constants */
export { ENCRYPTION_CONFIG } from '../encryption/constants.js';
