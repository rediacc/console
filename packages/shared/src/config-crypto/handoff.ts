/**
 * CEK Handoff — X25519 Key Distribution Between Members
 *
 * When an admin adds a team member, the CEK is encrypted with the
 * new member's X25519 public key. The server only relays opaque blobs.
 *
 * Uses the same X25519 + HKDF + AES-256-GCM pattern as the E2E module.
 */

import { fromBase64, randomBytes, toBase64 } from './aes.js';
import { ENCRYPTION_CONFIG } from './constants.js';
import type { CekHandoffBlob } from './types.js';

/** Extract ArrayBuffer from Uint8Array. */
function buf(data: Uint8Array): ArrayBuffer {
  if (data.byteOffset === 0 && data.byteLength === data.buffer.byteLength) {
    return data.buffer as ArrayBuffer;
  }
  return data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength) as ArrayBuffer;
}

const HANDOFF_HKDF_INFO = 'rediacc-cek-handoff-v1';

async function requireX25519(): Promise<void> {
  try {
    await crypto.subtle.generateKey({ name: 'X25519' }, false, ['deriveBits']);
  } catch {
    throw new Error(
      'Your browser does not support X25519 encryption. ' +
        'Please update to Chrome 133+, Edge 133+, Firefox 130+, or Safari 17+.'
    );
  }
}

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
  await requireX25519();
  // Generate ephemeral X25519 key pair
  const ephKeyPair = await crypto.subtle.generateKey({ name: 'X25519' }, true, ['deriveBits']);

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
  await requireX25519();
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

// ─── CLI relay handoff: key fingerprint and pairing code ─────────────────────
// The CLI mints an ephemeral X25519 key pair and sends only the SHA-256 of its SPKI to the account server. The portal page recomputes both values from the key in the link, so a swapped key fails the server's hash check and the pairing code the user types from the terminal.

/** 32 symbols, exactly 5 bits each (no modulo bias), without the letters that read like the digits zero and one. */
const PAIRING_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
const PAIRING_SYMBOLS = 12;
const PAIRING_GROUP = 4;

async function spkiDigest(spki: Uint8Array): Promise<Uint8Array> {
  return new Uint8Array(await crypto.subtle.digest('SHA-256', buf(spki)));
}

function toBase64Url(bytes: Uint8Array): string {
  return toBase64(bytes).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

/** base64url (no padding) of SHA-256(spki): always 43 characters. */
export async function handoffKeyHash(spki: Uint8Array): Promise<string> {
  return toBase64Url(await spkiDigest(spki));
}

/**
 * The first 60 bits of SHA-256(spki), 5 bits per symbol over
 * `ABCDEFGHJKLMNPQRSTUVWXYZ23456789`, formatted `XXXX-XXXX-XXXX`.
 */
export async function handoffPairingCode(spki: Uint8Array): Promise<string> {
  const digest = await spkiDigest(spki);
  let symbols = '';
  for (let i = 0; i < PAIRING_SYMBOLS; i++) {
    const bit = i * 5;
    const byte = bit >> 3;
    // Two bytes always cover the 5-bit window; digest has 32 bytes, so byte+1 exists.
    const window = (digest[byte] << 8) | digest[byte + 1];
    const value = (window >> (11 - (bit & 7))) & 0x1f;
    symbols += PAIRING_ALPHABET[value];
  }
  const groups: string[] = [];
  for (let i = 0; i < PAIRING_SYMBOLS; i += PAIRING_GROUP) {
    groups.push(symbols.slice(i, i + PAIRING_GROUP));
  }
  return groups.join('-');
}

/**
 * The verifier the account server stores for a relay poll secret S: base64url (no padding) of SHA-256 over
 * the 32 RAW bytes of S, not over the base64url text the CLI sends as `{pollSecret}`. 43 characters.
 * Mirrors `pollVerifierOf` in private/account/src/services/device-code.service.ts.
 */
export async function handoffPollVerifier(pollSecret: Uint8Array): Promise<string> {
  return toBase64Url(new Uint8Array(await crypto.subtle.digest('SHA-256', buf(pollSecret))));
}
