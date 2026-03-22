/**
 * E2E Envelope
 *
 * Sealed request/response envelopes for encrypted CLI ↔ account server communication.
 * Each request uses a fresh ephemeral X25519 key pair for forward secrecy.
 */

import { E2E_VERSION, ENCRYPTION_CONFIG } from './constants.js';
import {
  decrypt,
  deriveAesKey,
  deriveSharedSecret,
  encrypt,
  fromBase64,
  generateEphemeralKeyPair,
  importX25519PublicKeyRaw,
  toBase64,
} from './crypto.js';

// ─── Types ───────────────────────────────────────────────────────────────────

/** Encrypted request envelope sent over the wire (CLI → Server). */
export interface E2eRequestEnvelope {
  /** Protocol version */
  v: number;
  /** Key ID — identifies which server key was used */
  kid: string;
  /** Base64 ephemeral X25519 public key (32 bytes raw) */
  eph: string;
  /** Base64 HKDF salt (16 bytes) */
  salt: string;
  /** Base64 AES-GCM IV (12 bytes) */
  iv: string;
  /** Base64 AES-GCM ciphertext + auth tag */
  ct: string;
}

/** Decrypted inner request (plaintext inside the envelope). */
export interface E2eInnerRequest {
  method: string;
  path: string;
  headers: Record<string, string>;
  body: unknown;
}

/** Encrypted response envelope sent over the wire (Server → CLI). */
export interface E2eResponseEnvelope {
  /** Protocol version */
  v: number;
  /** Base64 AES-GCM IV (12 bytes) */
  iv: string;
  /** Base64 AES-GCM ciphertext + auth tag */
  ct: string;
  /** Original HTTP status code */
  status: number;
}

// ─── Client-side (CLI) ───────────────────────────────────────────────────────

/**
 * Seal a request for the server.
 *
 * @param serverPublicKey - Server's static X25519 CryptoKey
 * @param keyId - Key ID for the server key being used
 * @param method - Original HTTP method (GET, POST, etc.)
 * @param path - Original request path (e.g. /account/api/v1/licenses/status)
 * @param headers - Request headers (including Authorization)
 * @param body - Request body (null for GET)
 * @returns The encrypted envelope and the derived AES key (needed to decrypt the response)
 */
export async function sealRequest(
  serverPublicKey: CryptoKey,
  keyId: string,
  method: string,
  path: string,
  headers: Record<string, string>,
  body: unknown
): Promise<{ envelope: E2eRequestEnvelope; aesKey: CryptoKey }> {
  // 1. Generate ephemeral key pair
  const ephemeral = await generateEphemeralKeyPair();

  // 2. Derive shared secret
  const sharedSecret = await deriveSharedSecret(ephemeral.privateKey, serverPublicKey);

  // 3. Derive AES key
  const salt = crypto.getRandomValues(new Uint8Array(ENCRYPTION_CONFIG.SALT_LENGTH));
  const aesKey = await deriveAesKey(sharedSecret, salt);

  // 4. Encrypt inner request
  const innerRequest: E2eInnerRequest = { method, path, headers, body };
  const plaintext = new TextEncoder().encode(JSON.stringify(innerRequest));
  const { iv, ct } = await encrypt(aesKey, plaintext);

  // 5. Build envelope
  const envelope: E2eRequestEnvelope = {
    v: E2E_VERSION,
    kid: keyId,
    eph: toBase64(ephemeral.publicKeyRaw),
    salt: toBase64(salt),
    iv: toBase64(iv),
    ct: toBase64(ct),
  };

  return { envelope, aesKey };
}

/**
 * Open (decrypt) a response from the server.
 *
 * @param aesKey - The AES key from sealRequest (same shared secret)
 * @param envelope - The encrypted response envelope
 * @returns Decrypted response body as string and the HTTP status code
 */
export async function openResponse(
  aesKey: CryptoKey,
  envelope: E2eResponseEnvelope
): Promise<{ status: number; body: string }> {
  const iv = fromBase64(envelope.iv);
  const ct = fromBase64(envelope.ct);
  const plaintext = await decrypt(aesKey, iv, ct);
  const body = new TextDecoder().decode(plaintext);

  return { status: envelope.status, body };
}

// ─── Server-side ─────────────────────────────────────────────────────────────

/**
 * Open (decrypt) a request from the CLI.
 *
 * @param serverPrivateKey - Server's static X25519 private CryptoKey
 * @param envelope - The encrypted request envelope
 * @returns Decrypted inner request and the derived AES key (needed to encrypt the response)
 */
export async function openRequest(
  serverPrivateKey: CryptoKey,
  envelope: E2eRequestEnvelope
): Promise<{ innerRequest: E2eInnerRequest; aesKey: CryptoKey }> {
  // 1. Import the client's ephemeral public key
  const ephPublicKeyRaw = fromBase64(envelope.eph);
  const ephPublicKey = await importX25519PublicKeyRaw(ephPublicKeyRaw);

  // 2. Derive the same shared secret
  const sharedSecret = await deriveSharedSecret(serverPrivateKey, ephPublicKey);

  // 3. Derive the same AES key
  const salt = fromBase64(envelope.salt);
  const aesKey = await deriveAesKey(sharedSecret, salt);

  // 4. Decrypt
  const iv = fromBase64(envelope.iv);
  const ct = fromBase64(envelope.ct);
  const plaintext = await decrypt(aesKey, iv, ct);
  const innerRequest = JSON.parse(new TextDecoder().decode(plaintext)) as E2eInnerRequest;

  return { innerRequest, aesKey };
}

/**
 * Seal a response for the CLI.
 *
 * @param aesKey - The AES key from openRequest (same shared secret)
 * @param status - HTTP status code
 * @param body - Response body string (JSON)
 * @returns Encrypted response envelope
 */
export async function sealResponse(
  aesKey: CryptoKey,
  status: number,
  body: string
): Promise<E2eResponseEnvelope> {
  const plaintext = new TextEncoder().encode(body);
  const { iv, ct } = await encrypt(aesKey, plaintext);

  return {
    v: E2E_VERSION,
    iv: toBase64(iv),
    ct: toBase64(ct),
    status,
  };
}
