/**
 * CEK (Client Encryption Key) Management
 *
 * CEK is a random 256-bit key shared by all team members.
 * It's wrapped (encrypted) per-user with a wrapping key derived from
 * passkey_secret + server_secret via HKDF.
 */

import {
  aesDecryptFromString,
  aesEncryptToString,
  exportAesKey,
  generateAesKey,
  importAesKey,
  randomBytes,
} from './aes.js';
import { HKDF_INFO } from './constants.js';
import { hkdfDeriveKey } from './hkdf.js';

/**
 * Generate a new random CEK.
 * Called once during config store setup.
 *
 * @returns CryptoKey for AES-256-GCM
 */
export async function generateCek(): Promise<CryptoKey> {
  return generateAesKey();
}

/**
 * Derive a wrapping key from passkey_secret + server_secret.
 *
 * wrappingKey = HKDF(passkey_secret || server_secret, salt, info)
 *
 * @param passkeySecret - Client-side secret from passkey PRF (raw bytes)
 * @param serverSecret - Server-side secret (raw bytes)
 * @returns Wrapping key for CEK wrap/unwrap
 */
export async function deriveWrappingKey(
  passkeySecret: Uint8Array,
  serverSecret: Uint8Array
): Promise<CryptoKey> {
  // Concatenate the two secrets as input key material
  const combined = new Uint8Array(passkeySecret.byteLength + serverSecret.byteLength);
  combined.set(passkeySecret, 0);
  combined.set(serverSecret, passkeySecret.byteLength);

  // Use a fixed salt for wrapping key derivation (domain separation via info string)
  const salt = new TextEncoder().encode('rediacc-wrapping-salt-v1');
  return hkdfDeriveKey(combined, salt, HKDF_INFO.WRAPPING_KEY);
}

/**
 * Wrap (encrypt) a CEK with a wrapping key.
 *
 * @param cek - The CEK to wrap
 * @param wrappingKey - The wrapping key (from deriveWrappingKey)
 * @returns Base64-encoded wrapped CEK
 */
export async function cekWrap(cek: CryptoKey, wrappingKey: CryptoKey): Promise<string> {
  const cekRaw = await exportAesKey(cek);
  return aesEncryptToString(wrappingKey, cekRaw);
}

/**
 * Unwrap (decrypt) a CEK with a wrapping key.
 *
 * @param wrappedCek - Base64-encoded wrapped CEK
 * @param wrappingKey - The wrapping key (from deriveWrappingKey)
 * @returns The unwrapped CEK
 */
export async function cekUnwrap(wrappedCek: string, wrappingKey: CryptoKey): Promise<CryptoKey> {
  const cekRaw = await aesDecryptFromString(wrappingKey, wrappedCek);
  return importAesKey(cekRaw);
}

/**
 * Generate a random server secret (32 bytes).
 * Called once during config store setup. Stored encrypted on the server.
 */
export function generateServerSecret(): Uint8Array {
  return randomBytes(32);
}
