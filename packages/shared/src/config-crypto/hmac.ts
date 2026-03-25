/**
 * HMAC-SHA256 for Tamper Detection
 *
 * Client computes HMAC over encrypted blob, keyed with CEK.
 * Verified on pull to detect tampering.
 */

import { exportAesKey, fromBase64, toBase64 } from './aes.js';
import { HMAC_ALGORITHM } from './constants.js';

/** Extract ArrayBuffer from Uint8Array. */
function buf(data: Uint8Array): ArrayBuffer {
  if (data.byteOffset === 0 && data.byteLength === data.buffer.byteLength) {
    return data.buffer as ArrayBuffer;
  }
  return data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength) as ArrayBuffer;
}

/**
 * Import a CryptoKey (AES-GCM) as an HMAC key.
 * Uses the raw key bytes — the AES key doubles as the HMAC key for simplicity.
 */
async function importHmacKey(cek: CryptoKey): Promise<CryptoKey> {
  const rawKey = await exportAesKey(cek);
  return crypto.subtle.importKey(
    'raw',
    buf(rawKey),
    { name: 'HMAC', hash: HMAC_ALGORITHM },
    false,
    ['sign', 'verify']
  );
}

/**
 * Compute HMAC-SHA256 over encrypted data, keyed with CEK.
 *
 * @param encryptedBlob - The encrypted config blob (base64 string)
 * @param cek - The CEK used as HMAC key
 * @returns Base64-encoded HMAC
 */
export async function hmacCompute(encryptedBlob: string, cek: CryptoKey): Promise<string> {
  const hmacKey = await importHmacKey(cek);
  const data = new TextEncoder().encode(encryptedBlob);
  const signature = await crypto.subtle.sign('HMAC', hmacKey, buf(data));
  return toBase64(new Uint8Array(signature));
}

/**
 * Verify HMAC-SHA256 over encrypted data.
 *
 * @param encryptedBlob - The encrypted config blob (base64 string)
 * @param cek - The CEK used as HMAC key
 * @param expectedHmac - The expected HMAC value (base64 string)
 * @returns true if HMAC matches, false if tampered
 */
export async function hmacVerify(
  encryptedBlob: string,
  cek: CryptoKey,
  expectedHmac: string
): Promise<boolean> {
  const hmacKey = await importHmacKey(cek);
  const data = new TextEncoder().encode(encryptedBlob);
  const expected = fromBase64(expectedHmac);
  return crypto.subtle.verify('HMAC', hmacKey, buf(expected), buf(data));
}
