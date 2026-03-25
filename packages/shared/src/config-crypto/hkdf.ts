/**
 * HKDF Key Derivation (Web Crypto API)
 *
 * Used for:
 * - SDK time-windowed key derivation: HKDF(sdkMaster, epoch)
 * - Wrapping key derivation: HKDF(passkeySecret || serverSecret)
 */

import { ENCRYPTION_CONFIG } from './constants.js';

/** Extract ArrayBuffer from Uint8Array. */
function buf(data: Uint8Array): ArrayBuffer {
  if (data.byteOffset === 0 && data.byteLength === data.buffer.byteLength) {
    return data.buffer as ArrayBuffer;
  }
  return data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength) as ArrayBuffer;
}

/**
 * Derive an AES-256-GCM key using HKDF-SHA256.
 *
 * @param inputKeyMaterial - The input key material (raw bytes)
 * @param salt - Salt for HKDF (raw bytes)
 * @param info - Context/application-specific info string
 * @returns Derived AES-256-GCM CryptoKey
 */
export async function hkdfDeriveKey(
  inputKeyMaterial: Uint8Array,
  salt: Uint8Array,
  info: string
): Promise<CryptoKey> {
  const hkdfKey = await crypto.subtle.importKey('raw', buf(inputKeyMaterial), 'HKDF', false, [
    'deriveKey',
  ]);

  return crypto.subtle.deriveKey(
    {
      name: 'HKDF',
      hash: 'SHA-256',
      salt: buf(salt),
      info: buf(new TextEncoder().encode(info)),
    },
    hkdfKey,
    { name: 'AES-GCM', length: ENCRYPTION_CONFIG.KEY_LENGTH_BITS },
    true, // extractable — needed for CEK wrapping
    ['encrypt', 'decrypt']
  );
}

/**
 * Derive raw key bytes using HKDF-SHA256.
 *
 * @param inputKeyMaterial - The input key material (raw bytes)
 * @param salt - Salt for HKDF (raw bytes)
 * @param info - Context/application-specific info string
 * @returns Derived raw bytes (32 bytes / 256 bits)
 */
export async function hkdfDeriveRaw(
  inputKeyMaterial: Uint8Array,
  salt: Uint8Array,
  info: string
): Promise<Uint8Array> {
  const hkdfKey = await crypto.subtle.importKey('raw', buf(inputKeyMaterial), 'HKDF', false, [
    'deriveBits',
  ]);

  const derived = await crypto.subtle.deriveBits(
    {
      name: 'HKDF',
      hash: 'SHA-256',
      salt: buf(salt),
      info: buf(new TextEncoder().encode(info)),
    },
    hkdfKey,
    ENCRYPTION_CONFIG.KEY_LENGTH_BITS
  );

  return new Uint8Array(derived);
}
