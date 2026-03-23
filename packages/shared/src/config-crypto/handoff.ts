/**
 * CEK Handoff — X25519 Key Distribution Between Members
 *
 * When an admin adds a team member, the CEK is encrypted with the
 * new member's X25519 public key. The server only relays opaque blobs.
 *
 * Uses the same X25519 + HKDF + AES-256-GCM pattern as the E2E module.
 */

import { ENCRYPTION_CONFIG } from './constants.js';
import { fromBase64, randomBytes, toBase64 } from './aes.js';
import type { CekHandoffBlob } from './types.js';

/** Extract ArrayBuffer from Uint8Array. */
function buf(data: Uint8Array): ArrayBuffer {
  if (data.byteOffset === 0 && data.byteLength === data.buffer.byteLength) {
    return data.buffer as ArrayBuffer;
  }
  return data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength) as ArrayBuffer;
}

const HANDOFF_HKDF_INFO = 'rediacc-cek-handoff-v1';

/**
 * Encrypt a CEK for a recipient using their X25519 public key.
 * Admin's browser calls this to distribute CEK to a new member.
 *
 * @param cekRaw - Raw CEK bytes (32 bytes)
 * @param recipientPublicKey - Recipient's X25519 public key (CryptoKey)
 * @returns Handoff blob (JSON-serializable, opaque to server)
 */
export async function cekHandoffEncrypt(
  cekRaw: Uint8Array,
  recipientPublicKey: CryptoKey
): Promise<CekHandoffBlob> {
  // Generate ephemeral X25519 key pair
  const ephKeyPair = (await crypto.subtle.generateKey({ name: 'X25519' }, true, [
    'deriveBits',
  ])) as unknown as { publicKey: CryptoKey; privateKey: CryptoKey };

  // Export ephemeral public key
  const ephPublicSpki = new Uint8Array(await crypto.subtle.exportKey('spki', ephKeyPair.publicKey));

  // Derive shared secret via ECDH
  const sharedSecret = await crypto.subtle.deriveBits(
    { name: 'X25519', public: recipientPublicKey },
    ephKeyPair.privateKey,
    256
  );

  // Derive AES key from shared secret via HKDF
  const salt = randomBytes(ENCRYPTION_CONFIG.SALT_LENGTH);
  const hkdfKey = await crypto.subtle.importKey('raw', sharedSecret, 'HKDF', false, ['deriveKey']);
  const aesKey = await crypto.subtle.deriveKey(
    {
      name: 'HKDF',
      hash: 'SHA-256',
      salt: buf(salt),
      info: buf(new TextEncoder().encode(HANDOFF_HKDF_INFO)),
    },
    hkdfKey,
    { name: 'AES-GCM', length: ENCRYPTION_CONFIG.KEY_LENGTH_BITS },
    false,
    ['encrypt']
  );

  // Encrypt CEK with derived AES key
  const iv = randomBytes(ENCRYPTION_CONFIG.IV_LENGTH);
  const ct = await crypto.subtle.encrypt({ name: 'AES-GCM', iv: buf(iv) }, aesKey, buf(cekRaw));

  return {
    v: 1,
    eph: toBase64(ephPublicSpki),
    salt: toBase64(salt),
    iv: toBase64(iv),
    ct: toBase64(new Uint8Array(ct)),
  };
}

/**
 * Decrypt a CEK handoff blob using the recipient's X25519 private key.
 * New member's browser calls this to receive the CEK.
 *
 * @param blob - The handoff blob from cekHandoffEncrypt
 * @param recipientPrivateKey - Recipient's X25519 private key (CryptoKey)
 * @returns Raw CEK bytes (32 bytes)
 */
export async function cekHandoffDecrypt(
  blob: CekHandoffBlob,
  recipientPrivateKey: CryptoKey
): Promise<Uint8Array> {
  // Import ephemeral public key
  const ephPublicKey = await crypto.subtle.importKey(
    'spki',
    buf(fromBase64(blob.eph)),
    { name: 'X25519' },
    false,
    []
  );

  // Derive shared secret via ECDH
  const sharedSecret = await crypto.subtle.deriveBits(
    { name: 'X25519', public: ephPublicKey },
    recipientPrivateKey,
    256
  );

  // Derive AES key from shared secret via HKDF
  const hkdfKey = await crypto.subtle.importKey('raw', sharedSecret, 'HKDF', false, ['deriveKey']);
  const aesKey = await crypto.subtle.deriveKey(
    {
      name: 'HKDF',
      hash: 'SHA-256',
      salt: buf(fromBase64(blob.salt)),
      info: buf(new TextEncoder().encode(HANDOFF_HKDF_INFO)),
    },
    hkdfKey,
    { name: 'AES-GCM', length: ENCRYPTION_CONFIG.KEY_LENGTH_BITS },
    false,
    ['decrypt']
  );

  // Decrypt CEK
  const plaintext = await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv: buf(fromBase64(blob.iv)) },
    aesKey,
    buf(fromBase64(blob.ct))
  );

  return new Uint8Array(plaintext);
}
