/**
 * CEK Key Slots — LUKS-style multi-method CEK wrapping.
 *
 * Every slot, whatever its method, boils down to a 32-byte `slotSecret` that
 * feeds the UNCHANGED pipeline deriveWrappingKey(slotSecret, serverSecret) →
 * cekWrap/cekUnwrap. What varies per method is only how the slotSecret is
 * obtained:
 *
 * - passkey:  WebAuthn PRF output evaluated with prfEvalSalt() (no KDF here —
 *             the authenticator already did the work)
 * - password: PBKDF2-SHA256, 600k iterations, random 16-byte salt
 * - recovery: HKDF-SHA256 over a 160-bit Crockford base32 code (no stretching —
 *             the code is high-entropy by construction)
 *
 * kdfParams is PUBLIC per-slot metadata (stored server-side in the clear); it
 * must never contain secret material, only salts and iteration counts.
 */

import { fromBase64, randomBytes, toBase64 } from './aes.js';
import { cekUnwrap, cekWrap, deriveWrappingKey } from './cek.js';
import { HKDF_INFO } from './constants.js';
import { hkdfDeriveRaw } from './hkdf.js';

export type SlotMethod = 'passkey' | 'password' | 'recovery';

/** Public, non-secret KDF metadata stored alongside each slot. */
export type SlotKdfParams =
  | { method: 'passkey' }
  | { method: 'password'; algorithm: 'PBKDF2-SHA256'; iterations: number; salt: string }
  | { method: 'recovery'; algorithm: 'HKDF-SHA256'; salt: string };

/** OWASP-recommended floor for PBKDF2-SHA256, locked by plan decision. */
export const PASSWORD_PBKDF2_ITERATIONS = 600_000;

/** Mint kdfParams for a NEW password slot (fresh random 16-byte salt). */
export function newPasswordSlotParams(): SlotKdfParams {
  return {
    method: 'password',
    algorithm: 'PBKDF2-SHA256',
    iterations: PASSWORD_PBKDF2_ITERATIONS,
    salt: toBase64(randomBytes(16)),
  };
}

/** Mint kdfParams for a NEW recovery-code slot (fresh random 16-byte salt). */
export function newRecoverySlotParams(): SlotKdfParams {
  return {
    method: 'recovery',
    algorithm: 'HKDF-SHA256',
    salt: toBase64(randomBytes(16)),
  };
}

// ─── Recovery codes ─────────────────────────────────────────────────────────

/** Crockford base32 — no I, L, O, U; unambiguous to read back over the phone. */
const CROCKFORD_ALPHABET = '0123456789ABCDEFGHJKMNPQRSTVWXYZ';

const RECOVERY_PREFIX = 'RC1';
const RECOVERY_GROUPS = 4;
const RECOVERY_GROUP_LENGTH = 8;

/**
 * Generate a fresh recovery code: `RC1-` + 4 groups of 8 Crockford base32
 * chars, 160 bits of entropy. Shown to the user ONCE; only its derived slot
 * secret survives.
 */
export function generateRecoveryCode(): string {
  const groups: string[] = [];
  for (let g = 0; g < RECOVERY_GROUPS; g++) {
    let group = '';
    // One byte per char: 256 % 32 === 0, so a byte mod 32 is unbiased.
    const bytes = randomBytes(RECOVERY_GROUP_LENGTH);
    for (let i = 0; i < RECOVERY_GROUP_LENGTH; i++) {
      group += CROCKFORD_ALPHABET[bytes[i] % 32];
    }
    groups.push(group);
  }
  return `${RECOVERY_PREFIX}-${groups.join('-')}`;
}

/**
 * Normalize and validate a user-typed recovery code.
 *
 * Forgiving on input: case-insensitive, dashes/spaces optional, prefix
 * optional, Crockford aliases folded (O→0, I→1, L→1). Returns the canonical
 * `RC1-XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX` form, or throws on anything that
 * is not exactly 32 valid chars after normalization.
 */
export function parseRecoveryCode(input: string): string {
  let s = input.toUpperCase().replaceAll(/[\s-]/g, '');
  if (s.startsWith(RECOVERY_PREFIX)) s = s.slice(RECOVERY_PREFIX.length);
  s = s.replaceAll('O', '0').replaceAll(/[IL]/g, '1');

  const expected = RECOVERY_GROUPS * RECOVERY_GROUP_LENGTH;
  if (s.length !== expected) {
    throw new Error(`Recovery code must have ${expected} characters (got ${s.length})`);
  }
  for (const ch of s) {
    if (!CROCKFORD_ALPHABET.includes(ch)) {
      throw new Error(`Recovery code contains an invalid character: ${ch}`);
    }
  }

  const groups: string[] = [];
  for (let g = 0; g < RECOVERY_GROUPS; g++) {
    groups.push(s.slice(g * RECOVERY_GROUP_LENGTH, (g + 1) * RECOVERY_GROUP_LENGTH));
  }
  return `${RECOVERY_PREFIX}-${groups.join('-')}`;
}

// ─── Slot secret derivation ─────────────────────────────────────────────────

/** Extract ArrayBuffer from Uint8Array. */
function buf(data: Uint8Array): ArrayBuffer {
  if (data.byteOffset === 0 && data.byteLength === data.buffer.byteLength) {
    return data.buffer as ArrayBuffer;
  }
  return data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength) as ArrayBuffer;
}

/**
 * Derive the 32-byte slot secret for a password slot.
 * PBKDF2-SHA256 with the slot's public salt and iteration count.
 */
export async function derivePasswordSlotSecret(
  password: string,
  params: SlotKdfParams
): Promise<Uint8Array> {
  if (params.method !== 'password') {
    throw new Error(`Expected password kdfParams, got '${params.method}'`);
  }
  const keyMaterial = await crypto.subtle.importKey(
    'raw',
    buf(new TextEncoder().encode(password)),
    'PBKDF2',
    false,
    ['deriveBits']
  );
  const derived = await crypto.subtle.deriveBits(
    {
      name: 'PBKDF2',
      hash: 'SHA-256',
      salt: buf(fromBase64(params.salt)),
      iterations: params.iterations,
    },
    keyMaterial,
    256
  );
  return new Uint8Array(derived);
}

/**
 * Derive the 32-byte slot secret for a recovery-code slot.
 * HKDF-SHA256 over the canonical code string — the code's 160 bits of entropy
 * make stretching unnecessary.
 */
export async function deriveRecoverySlotSecret(
  recoveryCode: string,
  params: SlotKdfParams
): Promise<Uint8Array> {
  if (params.method !== 'recovery') {
    throw new Error(`Expected recovery kdfParams, got '${params.method}'`);
  }
  const canonical = parseRecoveryCode(recoveryCode);
  return hkdfDeriveRaw(
    new TextEncoder().encode(canonical),
    fromBase64(params.salt),
    HKDF_INFO.RECOVERY_SLOT
  );
}

// ─── Wrap / unwrap composition ──────────────────────────────────────────────

/**
 * Wrap a CEK under a slot secret. Composes the existing pipeline unchanged:
 * deriveWrappingKey(slotSecret, serverSecret) → cekWrap.
 */
export async function wrapCekForSlot(
  cek: CryptoKey,
  slotSecret: Uint8Array,
  serverSecret: Uint8Array
): Promise<string> {
  const wrappingKey = await deriveWrappingKey(slotSecret, serverSecret);
  return cekWrap(cek, wrappingKey);
}

/**
 * Unwrap a CEK with a slot secret. Inverse of {@link wrapCekForSlot}; a wrong
 * secret surfaces as an AES-GCM auth failure from cekUnwrap.
 */
export async function unwrapCekForSlot(
  wrappedCek: string,
  slotSecret: Uint8Array,
  serverSecret: Uint8Array
): Promise<CryptoKey> {
  const wrappingKey = await deriveWrappingKey(slotSecret, serverSecret);
  return cekUnwrap(wrappedCek, wrappingKey);
}
