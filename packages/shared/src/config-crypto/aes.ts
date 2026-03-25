/**
 * AES-256-GCM Encryption/Decryption (Web Crypto API)
 *
 * Low-level primitives used by all encryption layers.
 * Works on Node.js 22+, Cloudflare Workers, and browsers.
 */

import { ENCRYPTION_CONFIG } from './constants.js';
import type { AesEncryptResult } from './types.js';

/** Extract ArrayBuffer from Uint8Array for Web Crypto API compatibility. */
function buf(data: Uint8Array): ArrayBuffer {
  if (data.byteOffset === 0 && data.byteLength === data.buffer.byteLength) {
    return data.buffer as ArrayBuffer;
  }
  return data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength) as ArrayBuffer;
}

/** Generate a random AES-256 key. */
export async function generateAesKey(): Promise<CryptoKey> {
  return crypto.subtle.generateKey(
    { name: 'AES-GCM', length: ENCRYPTION_CONFIG.KEY_LENGTH_BITS },
    true,
    ['encrypt', 'decrypt']
  );
}

/** Import raw key bytes as an AES-256-GCM CryptoKey. */
export async function importAesKey(
  rawBytes: Uint8Array,
  usages: ('encrypt' | 'decrypt')[] = ['encrypt', 'decrypt']
): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    'raw',
    buf(rawBytes),
    { name: 'AES-GCM', length: 256 },
    true,
    usages
  );
}

/** Export a CryptoKey to raw bytes. */
export async function exportAesKey(key: CryptoKey): Promise<Uint8Array> {
  const raw = await crypto.subtle.exportKey('raw', key);
  return new Uint8Array(raw);
}

/** Encrypt plaintext with AES-256-GCM. Returns IV + ciphertext (ct includes auth tag). */
export async function aesEncrypt(key: CryptoKey, plaintext: Uint8Array): Promise<AesEncryptResult> {
  const iv = crypto.getRandomValues(new Uint8Array(ENCRYPTION_CONFIG.IV_LENGTH));
  const ct = await crypto.subtle.encrypt({ name: 'AES-GCM', iv: buf(iv) }, key, buf(plaintext));
  return { iv, ct: new Uint8Array(ct) };
}

/** Decrypt ciphertext with AES-256-GCM. The ct must include the auth tag. */
export async function aesDecrypt(
  key: CryptoKey,
  iv: Uint8Array,
  ct: Uint8Array
): Promise<Uint8Array> {
  const plaintext = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: buf(iv) }, key, buf(ct));
  return new Uint8Array(plaintext);
}

// ─── Serialization helpers ──────────────────────────────────────────────────

/** Encode Uint8Array to base64. */
export function toBase64(data: Uint8Array): string {
  return btoa(String.fromCharCode(...data));
}

/** Decode base64 to Uint8Array. */
export function fromBase64(b64: string): Uint8Array {
  return Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
}

/** Encrypt and serialize to base64 string: base64(iv + ct). */
export async function aesEncryptToString(key: CryptoKey, plaintext: Uint8Array): Promise<string> {
  const { iv, ct } = await aesEncrypt(key, plaintext);
  const combined = new Uint8Array(iv.byteLength + ct.byteLength);
  combined.set(iv, 0);
  combined.set(ct, iv.byteLength);
  return toBase64(combined);
}

/** Decrypt from base64 string: base64(iv + ct) → plaintext. */
export async function aesDecryptFromString(key: CryptoKey, encrypted: string): Promise<Uint8Array> {
  const combined = fromBase64(encrypted);
  const iv = combined.slice(0, ENCRYPTION_CONFIG.IV_LENGTH);
  const ct = combined.slice(ENCRYPTION_CONFIG.IV_LENGTH);
  return aesDecrypt(key, iv, ct);
}

/** Generate random bytes. */
export function randomBytes(length: number): Uint8Array {
  return crypto.getRandomValues(new Uint8Array(length));
}
