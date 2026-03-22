/**
 * E2E Encryption Module
 *
 * Application-layer encryption for CLI ↔ account server communication.
 * Uses X25519 ECDH key exchange + AES-256-GCM symmetric encryption.
 */

export { E2E_CONTENT_TYPE, E2E_HKDF_INFO, E2E_VERSION } from './constants.js';
export {
  decrypt,
  deriveAesKey,
  deriveSharedSecret,
  encrypt,
  fromBase64,
  generateEphemeralKeyPair,
  importX25519PrivateKey,
  importX25519PublicKey,
  importX25519PublicKeyRaw,
  toBase64,
} from './crypto.js';
export type {
  E2eInnerRequest,
  E2eRequestEnvelope,
  E2eResponseEnvelope,
} from './envelope.js';
export { openRequest, openResponse, sealRequest, sealResponse } from './envelope.js';
export { CURRENT_SERVER_E2E_KEY, SERVER_E2E_KEYS } from './keys.js';
export type { ServerE2eKey } from './keys.js';
