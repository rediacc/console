/**
 * Encryption utility using Web Crypto API with AES-256-GCM
 *
 * Algorithm specifications for portability:
 * - Key derivation: PBKDF2 with SHA-256, 100000 iterations, 256-bit key
 * - Encryption: AES-256-GCM with 96-bit random IV
 * - Output format: base64(salt + IV + encrypted data + auth tag)
 * - Salt: Random 16 bytes per encryption (included in output)
 *
 * Python equivalent: cryptography library with PBKDF2HMAC, AES-GCM
 * C++ equivalent: OpenSSL with PKCS5_PBKDF2_HMAC, EVP_aes_256_gcm
 *
 * IMPORTANT: This implementation is compatible with CLI (Python) and Bridge (C++)
 */

// Encryption configuration constants
const ENCRYPTION_CONFIG = {
  SALT_LENGTH: 16, // 128 bits for PBKDF2 salt
  ITERATIONS: 100000,
  KEY_LENGTH: 256,
  IV_LENGTH: 12, // 96 bits for GCM
  TAG_LENGTH: 16 // 128 bits for GCM
} as const

/**
 * Derives a cryptographic key from a password using PBKDF2
 */
async function deriveKey(password: string, salt: Uint8Array): Promise<CryptoKey> {
  const passwordBuffer = new TextEncoder().encode(password);

  const baseKey = await crypto.subtle.importKey(
    'raw',
    passwordBuffer,
    'PBKDF2',
    false,
    ['deriveBits', 'deriveKey']
  );

  return crypto.subtle.deriveKey(
    {
      name: 'PBKDF2',
      salt: salt,
      iterations: ENCRYPTION_CONFIG.ITERATIONS,
      hash: 'SHA-256'
    },
    baseKey,
    { name: 'AES-GCM', length: ENCRYPTION_CONFIG.KEY_LENGTH },
    false,
    ['encrypt', 'decrypt']
  );
}

/**
 * Encrypts a string using AES-256-GCM
 * @returns base64 encoded string containing salt + IV + ciphertext + auth tag
 */
export async function encryptString(plaintext: string, password: string): Promise<string> {
  const salt = generateSalt();
  const key = await deriveKey(password, salt);
  const iv = generateInitializationVector();
  const encodedText = new TextEncoder().encode(plaintext);

  const ciphertext = await performEncryption(key, iv, encodedText);
  const combined = combineSaltIvAndCiphertext(salt, iv, ciphertext);

  return arrayToBase64(combined);
}

function generateSalt(): Uint8Array {
  return crypto.getRandomValues(new Uint8Array(ENCRYPTION_CONFIG.SALT_LENGTH));
}

function generateInitializationVector(): Uint8Array {
  return crypto.getRandomValues(new Uint8Array(ENCRYPTION_CONFIG.IV_LENGTH));
}

async function performEncryption(
  key: CryptoKey,
  iv: Uint8Array,
  data: Uint8Array
): Promise<ArrayBuffer> {
  return crypto.subtle.encrypt(
    {
      name: 'AES-GCM',
      iv: iv,
      tagLength: ENCRYPTION_CONFIG.TAG_LENGTH * 8 // in bits
    },
    key,
    data
  );
}

function combineSaltIvAndCiphertext(salt: Uint8Array, iv: Uint8Array, ciphertext: ArrayBuffer): Uint8Array {
  const combined = new Uint8Array(salt.length + iv.length + ciphertext.byteLength);
  combined.set(salt, 0);
  combined.set(iv, salt.length);
  combined.set(new Uint8Array(ciphertext), salt.length + iv.length);
  return combined;
}

function arrayToBase64(array: Uint8Array): string {
  return btoa(String.fromCharCode(...array));
}

/**
 * Decrypts a string encrypted with encryptString
 * @param encrypted base64 encoded string containing salt + IV + ciphertext + auth tag
 * @returns decrypted plaintext string
 */
export async function decryptString(encrypted: string, password: string): Promise<string> {
  const combined = base64ToArray(encrypted);
  const { salt, iv, ciphertext } = extractSaltIvAndCiphertext(combined);
  const key = await deriveKey(password, salt);

  const decrypted = await performDecryption(key, iv, ciphertext);

  return new TextDecoder().decode(decrypted);
}

function base64ToArray(base64: string): Uint8Array {
  return Uint8Array.from(atob(base64), c => c.charCodeAt(0));
}

function extractSaltIvAndCiphertext(combined: Uint8Array): {
  salt: Uint8Array;
  iv: Uint8Array;
  ciphertext: Uint8Array
} {
  const salt = combined.slice(0, ENCRYPTION_CONFIG.SALT_LENGTH);
  const iv = combined.slice(ENCRYPTION_CONFIG.SALT_LENGTH, ENCRYPTION_CONFIG.SALT_LENGTH + ENCRYPTION_CONFIG.IV_LENGTH);
  const ciphertext = combined.slice(ENCRYPTION_CONFIG.SALT_LENGTH + ENCRYPTION_CONFIG.IV_LENGTH);
  return { salt, iv, ciphertext };
}

async function performDecryption(
  key: CryptoKey,
  iv: Uint8Array,
  ciphertext: Uint8Array
): Promise<ArrayBuffer> {
  return crypto.subtle.decrypt(
    {
      name: 'AES-GCM',
      iv: iv,
      tagLength: ENCRYPTION_CONFIG.TAG_LENGTH * 8
    },
    key,
    ciphertext
  );
}

/**
 * Recursively encrypts all fields with "vault" in their name
 */
export async function encryptVaultFields(
  obj: any,
  password: string
): Promise<any> {
  if (!password || !obj) return obj;

  if (typeof obj === 'string') {
    return obj;
  }

  if (Array.isArray(obj)) {
    return Promise.all(obj.map(item => encryptVaultFields(item, password)));
  }

  if (typeof obj === 'object' && obj !== null) {
    return encryptObjectFields(obj, password);
  }

  return obj;
}

/**
 * Recursively decrypts all fields with "vault" in their name
 */
export async function decryptVaultFields(
  obj: any,
  password: string
): Promise<any> {
  if (!password || !obj) return obj;

  if (typeof obj === 'string') {
    return obj;
  }

  if (Array.isArray(obj)) {
    return Promise.all(obj.map(item => decryptVaultFields(item, password)));
  }

  if (typeof obj === 'object' && obj !== null) {
    return decryptObjectFields(obj, password);
  }

  return obj;
}

async function decryptObjectFields(obj: any, password: string): Promise<any> {
  const result: any = {};

  for (const [key, value] of Object.entries(obj)) {
    if (shouldDecryptField(key, value)) {
      result[key] = await tryDecryptField(key, value as string, password);
    } else if (typeof value === 'object') {
      result[key] = await decryptVaultFields(value, password);
    } else {
      result[key] = value;
    }
  }

  return result;
}

function shouldDecryptField(key: string, value: any): boolean {
  return key.toLowerCase().includes('vault') &&
         typeof value === 'string' &&
         value.length > 0;
}

async function tryDecryptField(_key: string, value: string, password: string): Promise<string> {
  try {
    if (isBase64Encrypted(value)) {
      return await decryptString(value, password);
    }
    return value; // Not encrypted, keep as is
  } catch (error) {
    return value; // Keep encrypted on error
  }
}

function isBase64Encrypted(value: string): boolean {
  return /^[A-Za-z0-9+/]+=*$/.test(value);
}

async function encryptObjectFields(obj: any, password: string): Promise<any> {
  const result: any = {};

  for (const [key, value] of Object.entries(obj)) {
    if (shouldEncryptField(key, value)) {
      result[key] = await tryEncryptField(key, value as string, password);
    } else if (typeof value === 'object') {
      result[key] = await encryptVaultFields(value, password);
    } else {
      result[key] = value;
    }
  }

  return result;
}

function shouldEncryptField(key: string, value: any): boolean {
  return key.toLowerCase().includes('vault') &&
         typeof value === 'string' &&
         value.length > 0;
}

async function tryEncryptField(_key: string, value: string, password: string): Promise<string> {
  try {
    return await encryptString(value, password);
  } catch (error) {
    return value; // Keep original on error
  }
}

/**
 * Test if the Web Crypto API is available
 */
export function isCryptoAvailable(): boolean {
  return typeof crypto !== 'undefined' &&
         crypto.subtle !== undefined &&
         typeof crypto.subtle.encrypt === 'function';
}
