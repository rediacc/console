/**
 * E2E Crypto Primitives
 *
 * X25519 ECDH key exchange + AES-256-GCM encryption using Web Crypto API.
 * Works on both Node.js 22+ and Cloudflare Workers.
 */

import { E2E_HKDF_INFO, ENCRYPTION_CONFIG } from './constants.js';

/** Extract ArrayBuffer from Uint8Array for Web Crypto API compatibility. */
function buf(data: Uint8Array): ArrayBuffer {
  if (data.byteOffset === 0 && data.byteLength === data.buffer.byteLength) {
    return data.buffer as ArrayBuffer;
  }
  return data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength) as ArrayBuffer;
}

// ─── Base64 helpers ──────────────────────────────────────────────────────────

export function toBase64(data: Uint8Array): string {
  return btoa(String.fromCharCode(...data));
}

export function fromBase64(b64: string): Uint8Array {
  return Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
}

// ─── X25519 Key Operations ───────────────────────────────────────────────────

/**
 * Generate an ephemeral X25519 key pair.
 * Uses crypto.subtle.generateKey (Node.js 22+).
 * Only called by the CLI — the server only imports static keys.
 */
export async function generateEphemeralKeyPair(): Promise<{
  privateKey: CryptoKey;
  publicKey: CryptoKey;
  publicKeyRaw: Uint8Array;
}> {
  const keyPair = (await crypto.subtle.generateKey({ name: 'X25519' }, true, [
    'deriveBits',
  ])) as unknown as { publicKey: CryptoKey; privateKey: CryptoKey };

  // Extract raw 32-byte public key from SPKI export
  const spkiBuffer = await crypto.subtle.exportKey('spki', keyPair.publicKey);
  const spkiBytes = new Uint8Array(spkiBuffer);
  const publicKeyRaw = spkiBytes.slice(12); // 12-byte SPKI header + 32-byte key

  return {
    privateKey: keyPair.privateKey,
    publicKey: keyPair.publicKey,
    publicKeyRaw,
  };
}

/** Import an X25519 public key from base64-encoded SPKI format. */
export async function importX25519PublicKey(base64Spki: string): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    'spki',
    buf(fromBase64(base64Spki)),
    { name: 'X25519' },
    false,
    []
  );
}

/** Import an X25519 public key from raw 32 bytes. */
export async function importX25519PublicKeyRaw(raw: Uint8Array): Promise<CryptoKey> {
  return crypto.subtle.importKey('raw', buf(raw), { name: 'X25519' }, false, []);
}

/** Import an X25519 private key from base64-encoded PKCS8 format. */
export async function importX25519PrivateKey(base64Pkcs8: string): Promise<CryptoKey> {
  return crypto.subtle.importKey('pkcs8', buf(fromBase64(base64Pkcs8)), { name: 'X25519' }, false, [
    'deriveBits',
  ]);
}

// ─── Key Derivation ──────────────────────────────────────────────────────────

/** Derive shared secret via X25519 ECDH. Returns raw 32-byte shared secret. */
export async function deriveSharedSecret(
  privateKey: CryptoKey,
  publicKey: CryptoKey
): Promise<ArrayBuffer> {
  return crypto.subtle.deriveBits({ name: 'X25519', public: publicKey }, privateKey, 256);
}

/** Derive AES-256-GCM key from shared secret using HKDF-SHA256. */
export async function deriveAesKey(
  sharedSecret: ArrayBuffer,
  salt: Uint8Array
): Promise<CryptoKey> {
  const hkdfKey = await crypto.subtle.importKey('raw', sharedSecret, 'HKDF', false, ['deriveKey']);

  return crypto.subtle.deriveKey(
    {
      name: 'HKDF',
      hash: 'SHA-256',
      salt: buf(salt),
      info: buf(new TextEncoder().encode(E2E_HKDF_INFO)),
    },
    hkdfKey,
    { name: 'AES-GCM', length: ENCRYPTION_CONFIG.KEY_LENGTH_BITS },
    false,
    ['encrypt', 'decrypt']
  );
}

// ─── AES-256-GCM Encryption ─────────────────────────────────────────────────

/** Encrypt plaintext with AES-256-GCM. Returns { iv, ct } where ct includes auth tag. */
export async function encrypt(
  aesKey: CryptoKey,
  plaintext: Uint8Array
): Promise<{ iv: Uint8Array; ct: Uint8Array }> {
  const iv = crypto.getRandomValues(new Uint8Array(ENCRYPTION_CONFIG.IV_LENGTH));

  const ciphertext = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv: buf(iv) },
    aesKey,
    buf(plaintext)
  );

  return { iv, ct: new Uint8Array(ciphertext) };
}

/** Decrypt ciphertext with AES-256-GCM. The ct must include the auth tag. */
export async function decrypt(
  aesKey: CryptoKey,
  iv: Uint8Array,
  ct: Uint8Array
): Promise<Uint8Array> {
  const plaintext = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: buf(iv) }, aesKey, buf(ct));
  return new Uint8Array(plaintext);
}
