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
 *     fields: Record<Key, { hmac: base64, kind: CommitmentValueKind }>,
 *     removed?: Record<Key, { hmac, kind }>,   // push only: tombstones
 *     migrated?: Record<JsonPointer, Key>,     // push only: the v2 -> v3 upgrade
 *   }
 *
 * `Key` is the JSON pointer itself in envelope v2, and the BLINDED pointer in v3:
 * base64(HMAC-SHA256(PBK, pointer)), where PBK = HKDF(CEK, salt = configId, info
 * 'rediacc-config-ptr-v1'). The blinding key is per config and does not depend on
 * `fckSalt`, so one pointer keeps one key across every push of a config (the
 * server's anti-downgrade rule compares keys), while the server no longer reads
 * machine, repo or storage names out of the envelope (F14, ruling D6).
 *
 * A tombstone (`removed[key]`) is the commitment the STORED envelope holds for a
 * path the push drops, recomputed by the client from the value it saw, under the
 * stored `fckSalt`. The server lets a stored key vanish only against a tombstone
 * equal to what it stored: to delete a value, the writer must know it (F2, ruling
 * D1). `migrated` maps each v2 pointer to its v3 key on the one push that upgrades
 * a store; the server checks continuity through it and stores neither block.
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

import { fromBase64, toBase64 } from './aes.js';
import { type CommitmentValueKind, canonicalize, valueKind } from './canonical.js';
import { HKDF_INFO } from './constants.js';
import { hkdfDeriveRaw } from './hkdf.js';

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
  /** Push only: the stored commitment of each path this push deletes (see the header). */
  removed?: Record<string, FieldCommitment>;
  /** Push only, on the v2 -> v3 upgrade: each committed v2 pointer and the v3 key it now has. */
  migrated?: Record<string, string>;
}

/**
 * Derive the per-config key that blinds commitment pointers (envelope v3). Deterministic in (CEK,
 * configId): every device of a config computes the same key for the same pointer, and a pointer of
 * another config under the same CEK gets an unrelated one, so the server cannot link names across
 * configs of a store.
 */
export async function derivePointerBlindingKey(
  cek: CryptoKey,
  configId: string
): Promise<CryptoKey> {
  const cekRaw = new Uint8Array(await crypto.subtle.exportKey('raw', cek));
  const salt = new TextEncoder().encode(configId);
  const raw = await hkdfDeriveRaw(cekRaw, salt, HKDF_INFO.POINTER_BLIND);
  return crypto.subtle.importKey('raw', buf(raw), { name: 'HMAC', hash: 'SHA-256' }, false, [
    'sign',
  ]);
}

/** The v3 envelope key of one JSON pointer: base64(HMAC-SHA256(blinding key, pointer)). */
export async function blindPointer(blindingKey: CryptoKey, pointer: string): Promise<string> {
  const sig = await crypto.subtle.sign('HMAC', blindingKey, buf(new TextEncoder().encode(pointer)));
  return toBase64(new Uint8Array(sig));
}

/**
 * SHA-256 over the canonical form of the commitment STATE (`alg`, `fckSalt`, `fields`), base64.
 * Envelope v3 authenticates it in the AAD, so a server that edits the stored commitments makes the
 * blob refuse to open. The push-only blocks (`removed`, `migrated`) are not state and are excluded:
 * the server drops them before storing.
 */
export async function commitmentsDigest(commitments: FieldCommitments): Promise<string> {
  const state = { alg: commitments.alg, fckSalt: commitments.fckSalt, fields: commitments.fields };
  const digest = await crypto.subtle.digest('SHA-256', buf(canonicalize(state)));
  return toBase64(new Uint8Array(digest));
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
  // Include the pointer in the signed bytes so two different paths holding the same value produce distinct HMACs (prevents path-swap attacks).
  const payload = concat([new TextEncoder().encode(`${pointer}\0`), canon]);
  const sig = await crypto.subtle.sign('HMAC', fck, buf(payload));
  return {
    hmac: toBase64(new Uint8Array(sig)),
    kind: valueKind(value),
  };
}

/**
 * Compute commitments for a list of pointer/value pairs. Caller is responsible
 * for selecting which pointers to commit (see packages/shared/src/config-schema/walker.ts).
 * With `blindingKey` (envelope v3) each entry is keyed by its blinded pointer; without it, by the
 * pointer itself (the v2 form, which only a store still on v2 holds).
 */
export async function computeCommitments(
  fck: CryptoKey,
  fckSaltB64: string,
  entries: { pointer: string; value: unknown }[],
  blindingKey?: CryptoKey
): Promise<FieldCommitments> {
  const fields: Record<string, FieldCommitment> = {};
  for (const { pointer, value } of entries) {
    const key = blindingKey ? await blindPointer(blindingKey, pointer) : pointer;
    fields[key] = await commitField(fck, pointer, value);
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
export function verifyCommitment(
  fck: CryptoKey,
  pointer: string,
  value: unknown,
  expected: FieldCommitment
): Promise<boolean> {
  if (valueKind(value) !== expected.kind) return Promise.resolve(false);
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
