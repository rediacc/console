/**
 * The per-build signature of an offline bundle. No Rediacc release key exists in the CLI and the
 * bundle is assembled on the customer's own online machine, so the builder makes one Ed25519 key
 * per build, signs `manifest.json` with it, ships `manifest.sig` and `signer.pub` and prints the
 * public key's fingerprint. The operator carries the fingerprint to the air-gapped side by a path
 * other than the bundle, and `--signer <fingerprint>` refuses any bundle signed by another key.
 * Sums that travel beside the files prove nothing alone; the signature binds them.
 */

import { createHash, createPublicKey, generateKeyPairSync, sign, verify } from 'node:crypto';

export const SIGNATURE_FILE = 'manifest.sig';
export const SIGNER_FILE = 'signer.pub';

/** DER prefix of an Ed25519 SubjectPublicKeyInfo; the raw 32-byte key follows it. */
const SPKI_PREFIX = Buffer.from('302a300506032b6570032100', 'hex');
const RAW_KEY_BYTES = 32;

export interface BuildSignature {
  /** base64 of the Ed25519 signature over the manifest text. */
  signature: string;
  /** base64 of the raw 32-byte public key (the content of `signer.pub`). */
  publicKey: string;
  /** Lowercase hex sha256 of the raw public key. */
  fingerprint: string;
}

/** Lowercase hex sha256 of the raw public key; null when `publicKey` is not a 32-byte base64 key. */
export function fingerprintOf(publicKey: string): string | null {
  const raw = Buffer.from(publicKey.trim(), 'base64');
  if (raw.length !== RAW_KEY_BYTES) return null;
  return createHash('sha256').update(raw).digest('hex');
}

/** The form a fingerprint is compared in: hex, any case, an optional `sha256:` label, colons allowed. */
export function normaliseFingerprint(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/^sha256:/, '')
    .replaceAll(':', '');
}

/** Sign `manifestText` with a key made for this one build; the private half is not kept. */
export function signBuild(manifestText: string): BuildSignature {
  const { publicKey, privateKey } = generateKeyPairSync('ed25519');
  const raw = publicKey.export({ type: 'spki', format: 'der' }).subarray(SPKI_PREFIX.length);
  const publicB64 = raw.toString('base64');
  const fingerprint = fingerprintOf(publicB64);
  if (!fingerprint) throw new Error('ed25519 public key is not 32 bytes');
  return {
    signature: sign(null, Buffer.from(manifestText), privateKey).toString('base64'),
    publicKey: publicB64,
    fingerprint,
  };
}

/** Whether `signature` is `publicKey`'s Ed25519 signature over `manifestText`. */
export function signatureHolds(
  manifestText: string,
  signature: string,
  publicKey: string
): boolean {
  const raw = Buffer.from(publicKey.trim(), 'base64');
  if (raw.length !== RAW_KEY_BYTES) return false;
  const key = createPublicKey({
    key: Buffer.concat([SPKI_PREFIX, raw]),
    format: 'der',
    type: 'spki',
  });
  return verify(null, Buffer.from(manifestText), key, Buffer.from(signature.trim(), 'base64'));
}
