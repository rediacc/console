/**
 * Air-gapped Delegation Cert Renewal Manifest
 *
 * Used by the offline renewal flow:
 *   1. On-premise admin downloads a signed manifest containing the local
 *      chain head, the currently delegated public key, and a tamper-evident
 *      signature from the on-prem private key.
 *   2. Customer carries the manifest (USB / SCP / encrypted email) to the
 *      upstream account portal.
 *   3. Upstream admin (or org owner via the portal) uploads the manifest to
 *      the process-renewal-request endpoint, which verifies the signature
 *      against the active cert's `delegatedPublicKey`, calls the existing
 *      `renew()` flow, and returns a fresh signed cert.
 *   4. Customer carries the new cert back and uploads via the existing
 *      cert-upload endpoint.
 *
 * The whole loop never requires network egress from the on-prem.
 */

import { RENEWAL_MANIFEST_MAX_AGE_MS } from './constants.js';

export const RENEWAL_MANIFEST_SCHEMA_VERSION = 1;

export interface RenewalRequestManifest {
  schemaVersion: 1;
  /** ISO8601 timestamp of manifest generation. */
  generatedAt: string;
  subscriptionId: string;
  /** Current chain head from the on-prem's local issuance ledger. */
  currentChainHash: string;
  currentSequence: number;
  /**
   * The public key the new cert should re-authorize. Read directly from the
   * currently loaded cert payload — proves the new cert is for the same
   * delegated identity, not a key swap (which would require a fresh create).
   */
  delegatedPublicKey: string;
  /** Metadata for the upstream UI to display "you're renewing this cert". */
  currentCertValidUntil: string;
  currentCertPublicKeyId: string;
  /** Local DB id of the cert being renewed (informational only). */
  currentCertId: string | null;
}

export interface SignedRenewalRequestManifest {
  manifest: RenewalRequestManifest;
  /** Base64 Ed25519 signature of canonicalManifestBytes(manifest) by the on-prem private key. */
  signature: string;
  /** Public key id used for the signature. */
  publicKeyId: string;
}

/**
 * Canonical encoding of a manifest for signing/verification.
 *
 * Sorts top-level keys alphabetically and JSON.stringify's the result. This
 * guarantees both sides of the air gap (on-prem signer and upstream verifier)
 * compute identical bytes regardless of object construction order.
 */
export function canonicalManifestBytes(manifest: RenewalRequestManifest): Uint8Array {
  const sorted: Record<string, unknown> = {};
  for (const key of Object.keys(manifest).sort()) {
    sorted[key] = (manifest as unknown as Record<string, unknown>)[key];
  }
  return new TextEncoder().encode(JSON.stringify(sorted));
}

/**
 * Verify a signed manifest's Ed25519 signature against the given delegated
 * public key (base64 SPKI). Returns true on valid signature, false on any
 * failure (malformed key, malformed signature, mismatch).
 *
 * The caller is responsible for verifying that the delegatedPublicKeySpki
 * argument matches the active cert's `delegatedPublicKey` — this function
 * only checks "manifest was signed by the holder of the private key
 * corresponding to this public key."
 */
export async function verifyManifestSignature(
  signed: SignedRenewalRequestManifest,
  delegatedPublicKeySpki: string
): Promise<boolean> {
  try {
    // Wrap in a fresh ArrayBuffer to satisfy strict TS BufferSource typing
    // (Uint8Array<ArrayBufferLike> isn't assignable to BufferSource in newer TS).
    const keyBytes = base64ToBytes(delegatedPublicKeySpki);
    const publicKey = await crypto.subtle.importKey(
      'spki',
      keyBytes.buffer.slice(
        keyBytes.byteOffset,
        keyBytes.byteOffset + keyBytes.byteLength
      ) as ArrayBuffer,
      { name: 'Ed25519' },
      false,
      ['verify']
    );
    const bytes = canonicalManifestBytes(signed.manifest);
    const sig = base64ToBytes(signed.signature);
    return await crypto.subtle.verify(
      'Ed25519',
      publicKey,
      sig.buffer.slice(sig.byteOffset, sig.byteOffset + sig.byteLength) as ArrayBuffer,
      bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer
    );
  } catch {
    return false;
  }
}

/**
 * Returns true if the manifest is older than RENEWAL_MANIFEST_MAX_AGE_MS,
 * meaning the chain head it captures is too stale to safely renew against.
 */
export function isManifestExpired(
  manifest: RenewalRequestManifest,
  now: Date = new Date()
): boolean {
  const ageMs = now.getTime() - new Date(manifest.generatedAt).getTime();
  return ageMs > RENEWAL_MANIFEST_MAX_AGE_MS;
}

function base64ToBytes(b64: string): Uint8Array {
  return Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
}
