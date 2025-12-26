/**
 * Shared encryption configuration constants
 * Must be consistent across all components (CLI, Web, Desktop)
 */
export const ENCRYPTION_CONFIG = {
  /** Salt length in bytes */
  SALT_LENGTH: 16,
  /** PBKDF2 iteration count */
  ITERATIONS: 100000,
  /** Key length in bytes (for Node.js crypto) */
  KEY_LENGTH_BYTES: 32,
  /** Key length in bits (for Web Crypto API) */
  KEY_LENGTH_BITS: 256,
  /** IV/Nonce length in bytes */
  IV_LENGTH: 12,
  /** Authentication tag length in bytes */
  TAG_LENGTH: 16,
  /** Algorithm name for Node.js crypto */
  ALGORITHM: 'aes-256-gcm',
  /** Algorithm name for Web Crypto API */
  ALGORITHM_WEB: 'AES-GCM',
  /** Hash algorithm for Node.js crypto */
  HASH: 'sha256',
  /** Hash algorithm for Web Crypto API */
  HASH_WEB: 'SHA-256',
} as const;

/**
 * Static salt for password hashing
 * Must match database sfHash function (db_middleware_000_functions.sql)
 * Used to ensure even common passwords produce unique hashes
 */
export const PASSWORD_SALT = 'Rd!@cc111$ecur3P@$$w0rd$@lt#H@$h';
