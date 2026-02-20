/**
 * Subscription Crypto
 *
 * Ed25519 signature verification for subscription blobs.
 * Uses Web Crypto API for browser compatibility.
 */

import { decodeSubscriptionPayload, validateSubscription } from './validation';
import type {
  SubscriptionData,
  SubscriptionValidationResult,
  SignedSubscriptionBlob,
} from './types';

/**
 * Known public keys for signature verification.
 * Keys are indexed by publicKeyId for rotation support.
 */
const knownPublicKeys: Map<string, CryptoKey> = new Map();

/**
 * Import a public key for verification.
 * @param publicKeyId - Identifier for this key (for rotation support)
 * @param publicKeyBase64 - Base64-encoded SPKI public key
 */
export async function importPublicKey(publicKeyId: string, publicKeyBase64: string): Promise<void> {
  const keyBytes = Uint8Array.from(atob(publicKeyBase64), (c) => c.charCodeAt(0));

  const key = await crypto.subtle.importKey(
    'spki',
    keyBytes,
    { name: 'Ed25519' },
    false, // not extractable
    ['verify']
  );

  knownPublicKeys.set(publicKeyId, key);
}

/**
 * Check if a public key is registered.
 */
export function hasPublicKey(publicKeyId: string): boolean {
  return knownPublicKeys.has(publicKeyId);
}

/**
 * Get all registered public key IDs.
 */
export function getPublicKeyIds(): string[] {
  return Array.from(knownPublicKeys.keys());
}

/**
 * Clear all registered public keys.
 */
export function clearPublicKeys(): void {
  knownPublicKeys.clear();
}

/**
 * Verify a signed subscription blob.
 * @param blob - The signed subscription blob
 * @returns True if signature is valid
 */
export async function verifySignature(blob: SignedSubscriptionBlob): Promise<boolean> {
  const publicKey = knownPublicKeys.get(blob.publicKeyId);
  if (!publicKey) {
    console.warn(`Unknown public key ID: ${blob.publicKeyId}`);
    return false;
  }

  try {
    const payloadBytes = new TextEncoder().encode(blob.payload);
    const signatureBytes = Uint8Array.from(atob(blob.signature), (c) => c.charCodeAt(0));

    return await crypto.subtle.verify({ name: 'Ed25519' }, publicKey, signatureBytes, payloadBytes);
  } catch (error) {
    console.error('Signature verification failed:', error);
    return false;
  }
}

/**
 * Verify and decode a signed subscription blob.
 * @param blob - The signed subscription blob
 * @returns Validation result with decoded subscription data if valid
 */
export async function verifyAndDecodeSubscription(
  blob: SignedSubscriptionBlob
): Promise<SubscriptionValidationResult> {
  // Verify signature first
  const signatureValid = await verifySignature(blob);
  if (!signatureValid) {
    return { valid: false, error: 'Invalid signature' };
  }

  // Decode payload
  const data = decodeSubscriptionPayload(blob.payload);
  if (!data) {
    return { valid: false, error: 'Invalid subscription payload' };
  }

  // Validate subscription data
  return validateSubscription(data);
}

/**
 * Sign a subscription payload (for account server use).
 * This requires having the private key available.
 *
 * @param payload - Base64 encoded subscription data
 * @param privateKey - CryptoKey for signing
 * @param publicKeyId - ID to include in the blob
 * @returns Signed subscription blob
 */
export async function signSubscriptionPayload(
  payload: string,
  privateKey: CryptoKey,
  publicKeyId: string
): Promise<SignedSubscriptionBlob> {
  const payloadBytes = new TextEncoder().encode(payload);

  const signatureBuffer = await crypto.subtle.sign({ name: 'Ed25519' }, privateKey, payloadBytes);

  const signatureBytes = new Uint8Array(signatureBuffer);
  const signature = btoa(String.fromCharCode(...signatureBytes));

  return {
    payload,
    signature,
    publicKeyId,
  };
}

/**
 * Import a private key for signing (account server only).
 * @param privateKeyBase64 - Base64-encoded PKCS8 private key
 * @returns CryptoKey for signing
 */
export async function importPrivateKey(privateKeyBase64: string): Promise<CryptoKey> {
  const keyBytes = Uint8Array.from(atob(privateKeyBase64), (c) => c.charCodeAt(0));

  return await crypto.subtle.importKey(
    'pkcs8',
    keyBytes,
    { name: 'Ed25519' },
    false, // not extractable
    ['sign']
  );
}

/**
 * Generate a new Ed25519 key pair.
 * @returns Object with base64-encoded public and private keys
 */
export async function generateKeyPair(): Promise<{
  publicKey: string;
  privateKey: string;
}> {
  const keyPair = (await crypto.subtle.generateKey(
    { name: 'Ed25519' },
    true, // extractable
    ['sign', 'verify']
  )) as unknown as { publicKey: CryptoKey; privateKey: CryptoKey };

  const publicKeyBuffer = await crypto.subtle.exportKey('spki', keyPair.publicKey);
  const privateKeyBuffer = await crypto.subtle.exportKey('pkcs8', keyPair.privateKey);

  return {
    publicKey: btoa(String.fromCharCode(...new Uint8Array(publicKeyBuffer))),
    privateKey: btoa(String.fromCharCode(...new Uint8Array(privateKeyBuffer))),
  };
}

/**
 * Create a complete signed subscription from subscription data.
 * This is a convenience function for the account server.
 */
export async function createSignedSubscription(
  data: SubscriptionData,
  privateKey: CryptoKey,
  publicKeyId: string
): Promise<SignedSubscriptionBlob> {
  const payload = btoa(JSON.stringify(data));
  return signSubscriptionPayload(payload, privateKey, publicKeyId);
}
