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
  /** Envelope v3 and v4: the key that blinds commitment pointers (commitments.ts `derivePointerBlindingKey`). */
  POINTER_BLIND: 'rediacc-config-ptr-v1',
  RECOVERY_SLOT: 'rediacc-recovery-slot-v1',
  /** A machine secret's wrapping secret (slots.ts `deriveMachineSecretSlotSecret`, D46). */
  MACHINE_SECRET: 'rediacc-machine-secret-v1',
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

/**
 * The envelope version every client writes (D56, config-key.ts): the blob is sealed under the
 * config's own content key, which the envelope carries wrapped under the CEK (`wrappedConfigKey`,
 * `configKeyVersion`, `cekGeneration`), and the AES-GCM AAD binds it to its config (selective.ts
 * `envelopeAadV4`). The server refuses any other version on push.
 */
export const ENVELOPE_VERSION = 4;

/**
 * The CEK-bound envelope (selective.ts `envelopeAad`), READ only: a store still holding a v3
 * envelope opens under the CEK and upgrades to `ENVELOPE_VERSION` on its next push. No client
 * writes it.
 */
export const BOUND_ENVELOPE_VERSION = 3;

/**
 * The oldest envelope version, READ for one release (operator ruling D2): a store still holding a
 * v2 envelope opens with its blob HMAC and upgrades on its next push. Delete the v2 read path
 * (selective.ts) the release after.
 */
export const LEGACY_ENVELOPE_VERSION = 2;

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
