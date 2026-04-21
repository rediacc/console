/**
 * Field commitment hashes for the server-side precondition envelope.
 *
 * ─── Security model ────────────────────────────────────────────────────────
 * Every sensitive field in the config blob has an HMAC commitment in the
 * plaintext envelope. The HMAC is keyed by a Field Commitment Key (FCK)
 * derived from CEK via HKDF — the server never holds FCK, so it can only
 * compare submitted HMACs against stored ones. Zero-knowledge invariant
 * preserved.
 *
 * ─── Wire format ───────────────────────────────────────────────────────────
 * The envelope gains a `commitments` block:
 *
 *   commitments: {
 *     alg: 'HMAC-SHA256',
 *     fckSalt: base64(16 random bytes),
 *     fields: Record<JsonPointer, { hmac: base64, kind: CommitmentValueKind }>
 *   }
 *
 * `fckSalt` rotates whenever the CEK rotates (or arbitrarily — the client owns
 * the rotation cadence). A fresh salt invalidates all prior commitments, so the
 * client must recompute them on every push that bumps the salt.
 *
 * ─── Why value kind is stored alongside HMAC ───────────────────────────────
 * Anti-downgrade. If only HMACs were stored, an agent could commit to
 * `null` (explicitly-absent sensitive field) and bypass the precondition check
 * for a field that was previously present. With the kind stored, the server
 * rejects any commitment whose `kind` is `'missing'` if the previous envelope's
 * kind was anything else — sensitive paths cannot be dropped.
 *
 * ─── Consumers ─────────────────────────────────────────────────────────────
 * - packages/cli/src/adapters/remote-config-adapter.ts: computes commitments
 *   before push, optionally submits `precondition: { expectedCommitments }`
 *   alongside.
 * - private/account/src/services/config.service.ts: validates submitted
 *   `precondition.expectedCommitments` against the stored envelope's
 *   `commitments.fields`.
 */

import { toBase64, fromBase64 } from './aes.js';
import { HKDF_INFO } from './constants.js';
import { hkdfDeriveRaw } from './hkdf.js';
import { canonicalize, valueKind, type CommitmentValueKind } from './canonical.js';

/** ArrayBuffer coercion helper (Web Crypto needs the underlying buffer). */
function buf(data: Uint8Array): ArrayBuffer {
  if (data.byteOffset === 0 && data.byteLength === data.buffer.byteLength) {
    return data.buffer as ArrayBuffer;
  }
  return data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength) as ArrayBuffer;
}

export interface FieldCommitment {
  hmac: string; // base64 HMAC-SHA256(FCK, canonicalize(value))
  kind: CommitmentValueKind; // typed value kind; anti-downgrade signal
}

export interface FieldCommitments {
  alg: 'HMAC-SHA256';
  fckSalt: string; // base64-encoded salt for HKDF(CEK → FCK)
  fields: Record<string, FieldCommitment>;
}

/** Generate a fresh random salt for FCK derivation. */
export function generateFckSalt(): string {
  const salt = new Uint8Array(16);
  crypto.getRandomValues(salt);
  return toBase64(salt);
}

/**
 * Derive the Field Commitment Key from CEK + a per-config salt.
 *
 * CEK is an AES-256 key; we export its raw bytes, feed them as HKDF IKM with
 * the given salt and a fixed `info` string for domain separation, then import
 * the output as an HMAC-SHA256 key.
 */
export async function deriveFieldCommitmentKey(
  cek: CryptoKey,
  fckSaltB64: string
): Promise<CryptoKey> {
  const cekRaw = new Uint8Array(await crypto.subtle.exportKey('raw', cek));
  const salt = fromBase64(fckSaltB64);
  const fckRaw = await hkdfDeriveRaw(cekRaw, salt, HKDF_INFO.FIELD_COMMITMENT);
  return crypto.subtle.importKey('raw', buf(fckRaw), { name: 'HMAC', hash: 'SHA-256' }, false, [
    'sign',
    'verify',
  ]);
}

/**
 * Compute a single field commitment (HMAC of canonicalized value).
 */
export async function commitField(
  fck: CryptoKey,
  pointer: string,
  value: unknown
): Promise<FieldCommitment> {
  const canon = canonicalize(value);
  // Include the pointer in the signed bytes so two different paths holding the
  // same value produce distinct HMACs (prevents path-swap attacks).
  const payload = concat([new TextEncoder().encode(`${pointer}\0`), canon]);
  const sig = await crypto.subtle.sign('HMAC', fck, buf(payload));
  return {
    hmac: toBase64(new Uint8Array(sig)),
    kind: valueKind(value),
  };
}

/**
 * Compute commitments for a list of pointer/value pairs. Caller is responsible
 * for selecting which pointers to commit (see packages/cli/src/schema/walker.ts).
 */
export async function computeCommitments(
  fck: CryptoKey,
  fckSaltB64: string,
  entries: Array<{ pointer: string; value: unknown }>
): Promise<FieldCommitments> {
  const fields: Record<string, FieldCommitment> = {};
  for (const { pointer, value } of entries) {
    fields[pointer] = await commitField(fck, pointer, value);
  }
  return { alg: 'HMAC-SHA256', fckSalt: fckSaltB64, fields };
}

/**
 * Verify a single commitment against an expected value (client side, pre-push,
 * for the knowledge-gate "--current" check).
 *
 * Server-side verification is a hex-string comparison, not an HMAC recompute,
 * because the server does not hold FCK.
 */
export async function verifyCommitment(
  fck: CryptoKey,
  pointer: string,
  value: unknown,
  expected: FieldCommitment
): Promise<boolean> {
  if (valueKind(value) !== expected.kind) return false;
  const canon = canonicalize(value);
  const payload = concat([new TextEncoder().encode(`${pointer}\0`), canon]);
  const expectedBytes = fromBase64(expected.hmac);
  return crypto.subtle.verify('HMAC', fck, buf(expectedBytes), buf(payload));
}

function concat(chunks: Uint8Array[]): Uint8Array {
  const total = chunks.reduce((n, c) => n + c.length, 0);
  const out = new Uint8Array(total);
  let offset = 0;
  for (const c of chunks) {
    out.set(c, offset);
    offset += c.length;
  }
  return out;
}
