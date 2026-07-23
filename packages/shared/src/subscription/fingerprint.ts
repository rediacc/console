/**
 * Public-key fingerprint
 *
 * Deterministic identifier for an Ed25519 public key, shared by the account
 * server (signing), renet (validation), and the CLI (per-signer license
 * paths). Must produce byte-identical output to the Go implementation in
 * `private/renet/pkg/subscription/fingerprint.go`; a divergence between the
 * two produces an infinite reissue loop (the CLI writes the license under
 * name A, renet looks it up under name B, finds nothing, reissues forever).
 *
 * Definition: lowercase hex(SHA-256(raw 32-byte Ed25519 public key))[0:16]
 * (first 8 bytes, 16 hex chars). The input is a base64 SPKI-wrapped key; the
 * raw 32-byte key is the final 32 bytes of the DER. Bare 32-byte input is
 * accepted too, mirroring Go's `ParsePublicKey`.
 */

/** Regex every valid fingerprint must match: 16 lowercase hex chars. */
export const PUBLIC_KEY_ID_PATTERN = /^[0-9a-f]{16}$/;

/**
 * Extract the raw 32-byte Ed25519 public key from a base64-encoded input.
 * Accepts either an SPKI-wrapped key (12-byte prefix + 32-byte key) or a bare
 * 32-byte raw key. Throws when the decoded length is below 32 bytes.
 */
function extractRawKey(publicKeyBase64: string): Uint8Array<ArrayBuffer> {
  const decoded = Uint8Array.from(atob(publicKeyBase64), (c) => c.charCodeAt(0));
  if (decoded.length < 32) {
    throw new Error(
      `invalid Ed25519 public key: expected at least 32 bytes, got ${decoded.length}`
    );
  }
  // Raw key is always the final 32 bytes (Ed25519 SPKI is a fixed 12-byte
  // prefix; a bare 32-byte key is its own final 32 bytes). Copy into a fresh
  // ArrayBuffer-backed view so the digest input is a plain BufferSource.
  const raw = new Uint8Array(new ArrayBuffer(32));
  raw.set(decoded.subarray(decoded.length - 32));
  return raw;
}

/**
 * Compute the fingerprint identifier for an Ed25519 public key.
 * @param publicKeyBase64 - Base64 SPKI-wrapped key (or bare 32-byte raw key).
 * @returns 16-char lowercase hex fingerprint matching {@link PUBLIC_KEY_ID_PATTERN}.
 */
export async function computePublicKeyId(publicKeyBase64: string): Promise<string> {
  const rawKey = extractRawKey(publicKeyBase64);
  const digest = await crypto.subtle.digest('SHA-256', rawKey);
  const bytes = new Uint8Array(digest);
  let hex = '';
  for (let i = 0; i < 8; i++) {
    hex += bytes[i].toString(16).padStart(2, '0');
  }
  return hex;
}

/**
 * Whether a string is a well-formed public-key fingerprint.
 */
export function isValidPublicKeyId(value: string): boolean {
  return PUBLIC_KEY_ID_PATTERN.test(value);
}
