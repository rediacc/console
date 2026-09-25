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

/** Re-export shared encryption constants */
export { ENCRYPTION_CONFIG } from '../encryption/constants.js';
