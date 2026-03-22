/**
 * E2E Encryption Constants
 *
 * Protocol constants for application-layer encryption between CLI and account server.
 * Uses X25519 ECDH key exchange + AES-256-GCM symmetric encryption.
 */

/** Protocol version for the encrypted envelope */
export const E2E_VERSION = 1;

/** Content-Type header for encrypted requests/responses */
export const E2E_CONTENT_TYPE = 'application/x-rediacc-encrypted';

/** HKDF info string for key derivation */
export const E2E_HKDF_INFO = 'rediacc-e2e-v1';

/**
 * Re-export shared encryption constants for E2E module consumers.
 * Values: SALT_LENGTH=16, IV_LENGTH=12, KEY_LENGTH_BITS=256, TAG_LENGTH=16.
 */
export { ENCRYPTION_CONFIG } from '../encryption/constants.js';
