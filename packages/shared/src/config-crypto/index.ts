/**
 * Config Storage Encryption Library
 *
 * Triple-layer encryption for secure config storage:
 * Layer 1 (Inner — SDK):  Time-windowed server-controlled key
 * Layer 2 (Middle — CEK): Client-controlled key (split-key derivation)
 * Layer 3 (Outer — Org):  Server-side org passphrase
 *
 * Works on Node.js 22+, Cloudflare Workers, and browsers (Web Crypto API only).
 */

// AES-256-GCM primitives
export {
  aesDecrypt,
  aesDecryptFromString,
  aesEncrypt,
  aesEncryptToString,
  exportAesKey,
  fromBase64,
  generateAesKey,
  importAesKey,
  randomBytes,
  toBase64,
} from './aes.js';

// HKDF key derivation
export { hkdfDeriveKey, hkdfDeriveRaw } from './hkdf.js';

// SDK time-windowed derivation
export { generateSdkMaster, sdkDerive, sdkGetEpoch } from './sdk.js';

// CEK management
export { cekUnwrap, cekWrap, deriveWrappingKey, generateCek, generateServerSecret } from './cek.js';

// Triple-layer encryption
export { configDecrypt, configEncrypt, orgDecrypt, orgEncrypt } from './layers.js';

// HMAC tamper detection
export { hmacCompute, hmacVerify } from './hmac.js';

// X25519 CEK handoff
export { cekHandoffDecrypt, cekHandoffEncrypt } from './handoff.js';

// Selective encryption
export { selectiveDecrypt, selectiveEncrypt } from './selective.js';

// Canonical serialization for field-commitment HMACs
export { canonicalize, valueKind } from './canonical.js';
export type { CommitmentValueKind } from './canonical.js';

// Field commitments (server-side precondition enforcement)
export {
  commitField,
  computeCommitments,
  deriveFieldCommitmentKey,
  generateFckSalt,
  verifyCommitment,
} from './commitments.js';
export type { FieldCommitment, FieldCommitments } from './commitments.js';

// Constants
export {
  ENVELOPE_FIELDS,
  HKDF_INFO,
  HMAC_ALGORITHM,
  SDK_WINDOW_SECONDS,
  SENSITIVE_FIELDS,
} from './constants.js';

// Types
export type {
  AesEncryptResult,
  CekHandoffBlob,
  ConfigEnvelope,
  ConfigSensitiveData,
  EncryptedConfigPayload,
  EncryptedString,
  FullConfig,
} from './types.js';
