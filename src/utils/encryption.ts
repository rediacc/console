/**
 * Encryption utility using Web Crypto API with AES-256-GCM
 * 
 * Algorithm specifications for portability:
 * - Key derivation: PBKDF2 with SHA-256, 100000 iterations, 256-bit key
 * - Encryption: AES-256-GCM with 96-bit random IV
 * - Output format: base64(IV + encrypted data + auth tag)
 * - Salt: Fixed string "rediacc-vault-2024" (for simplicity and consistency)
 * 
 * Python equivalent: cryptography library with PBKDF2HMAC, AES-GCM
 * C++ equivalent: OpenSSL with PKCS5_PBKDF2_HMAC, EVP_aes_256_gcm
 */

const SALT = new TextEncoder().encode('rediacc-vault-2024');
const ITERATIONS = 100000;
const KEY_LENGTH = 256;
const IV_LENGTH = 12; // 96 bits for GCM
const TAG_LENGTH = 16; // 128 bits for GCM

/**
 * Derives a cryptographic key from a password using PBKDF2
 */
async function deriveKey(password: string): Promise<CryptoKey> {
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
      salt: SALT,
      iterations: ITERATIONS,
      hash: 'SHA-256'
    },
    baseKey,
    { name: 'AES-GCM', length: KEY_LENGTH },
    false,
    ['encrypt', 'decrypt']
  );
}

/**
 * Encrypts a string using AES-256-GCM
 * @returns base64 encoded string containing IV + ciphertext + auth tag
 */
export async function encryptString(plaintext: string, password: string): Promise<string> {
  try {
    const key = await deriveKey(password);
    const iv = crypto.getRandomValues(new Uint8Array(IV_LENGTH));
    const encodedText = new TextEncoder().encode(plaintext);

    const ciphertext = await crypto.subtle.encrypt(
      {
        name: 'AES-GCM',
        iv: iv,
        tagLength: TAG_LENGTH * 8 // in bits
      },
      key,
      encodedText
    );

    // Combine IV + ciphertext (which includes auth tag)
    const combined = new Uint8Array(iv.length + ciphertext.byteLength);
    combined.set(iv, 0);
    combined.set(new Uint8Array(ciphertext), iv.length);

    // Convert to base64
    return btoa(String.fromCharCode(...combined));
  } catch (error) {
    console.error('Encryption failed:', error);
    throw new Error('Failed to encrypt data');
  }
}

/**
 * Decrypts a string encrypted with encryptString
 * @param encrypted base64 encoded string containing IV + ciphertext + auth tag
 * @returns decrypted plaintext string
 */
export async function decryptString(encrypted: string, password: string): Promise<string> {
  try {
    const key = await deriveKey(password);
    
    // Decode from base64
    const combined = Uint8Array.from(atob(encrypted), c => c.charCodeAt(0));
    
    // Extract IV and ciphertext
    const iv = combined.slice(0, IV_LENGTH);
    const ciphertext = combined.slice(IV_LENGTH);

    const decrypted = await crypto.subtle.decrypt(
      {
        name: 'AES-GCM',
        iv: iv,
        tagLength: TAG_LENGTH * 8
      },
      key,
      ciphertext
    );

    return new TextDecoder().decode(decrypted);
  } catch (error) {
    console.error('Decryption failed:', error);
    throw new Error('Failed to decrypt data - invalid password or corrupted data');
  }
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
    const result: any = {};
    
    for (const [key, value] of Object.entries(obj)) {
      if (key.toLowerCase().includes('vault') && typeof value === 'string' && value) {
        try {
          result[key] = await encryptString(value, password);
        } catch (error) {
          console.error(`Failed to encrypt field ${key}:`, error);
          result[key] = value; // Keep original on error
        }
      } else if (typeof value === 'object') {
        result[key] = await encryptVaultFields(value, password);
      } else {
        result[key] = value;
      }
    }
    
    return result;
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
    const result: any = {};
    
    for (const [key, value] of Object.entries(obj)) {
      if (key.toLowerCase().includes('vault') && typeof value === 'string' && value) {
        try {
          // Check if it looks like base64 encrypted data
          if (value.match(/^[A-Za-z0-9+/]+=*$/)) {
            result[key] = await decryptString(value, password);
          } else {
            result[key] = value; // Not encrypted, keep as is
          }
        } catch (error) {
          console.error(`Failed to decrypt field ${key}:`, error);
          result[key] = value; // Keep encrypted on error
        }
      } else if (typeof value === 'object') {
        result[key] = await decryptVaultFields(value, password);
      } else {
        result[key] = value;
      }
    }
    
    return result;
  }

  return obj;
}

/**
 * Test if the Web Crypto API is available
 */
export function isCryptoAvailable(): boolean {
  return typeof crypto !== 'undefined' && 
         crypto.subtle !== undefined &&
         typeof crypto.subtle.encrypt === 'function';
}