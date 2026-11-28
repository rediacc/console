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
 * - recovery: HKDF-SHA256 over a 160-bit Crockford base32 code (no stretching —
 *             the code is high-entropy by construction)
 *
 * There is no password method (agent/programs/remote-mcp/02-decisions.md D39):
 * every slot secret comes from an authenticator or from a generated code, never
 * from a human-chosen secret an attacker holding a wrap could guess offline.
 *
 * A machine secret (D46) is not a slot: it lives in its own server table so it
 * never counts as a member or key holder. It wraps the CEK the same way, with a
 * generated `RM1-` code and its own HKDF info.
 *
 * kdfParams is PUBLIC per-slot metadata (stored server-side in the clear); it
 * must never contain secret material, only salts and identifiers.
 */

import { z } from 'zod';
import { fromBase64, randomBytes, toBase64 } from './aes.js';
import { cekUnwrap, cekWrap, deriveWrappingKey } from './cek.js';
import { HKDF_INFO } from './constants.js';
import { hkdfDeriveRaw } from './hkdf.js';

export const SLOT_METHODS = ['passkey', 'recovery'] as const;
export type SlotMethod = (typeof SLOT_METHODS)[number];

/** WebAuthn authenticator transports (AuthenticatorTransport); `hybrid` is a phone over QR (D45). */
export const PASSKEY_TRANSPORTS = [
  'usb',
  'nfc',
  'ble',
  'smart-card',
  'hybrid',
  'internal',
] as const;
export type PasskeyTransport = (typeof PASSKEY_TRANSPORTS)[number];

/**
 * Public, non-secret KDF metadata stored alongside each slot, as a parser: a stored object with any
 * other method (a `password` slot from before D39 included) fails to parse.
 *
 * A passkey slot records the credential it was enrolled with and the transport it used, so unlock
 * asks for that credential over that transport (D45). Both are absent on a passkey slot enrolled
 * before D45; such a slot unlocks with any of the user's credentials, as it always did.
 */
export const SlotKdfParamsSchema = z.discriminatedUnion('method', [
  z.strictObject({
    method: z.literal('passkey'),
    credentialId: z.string().min(1).optional(),
    transport: z.enum(PASSKEY_TRANSPORTS).optional(),
  }),
  z.strictObject({
    method: z.literal('recovery'),
    algorithm: z.literal('HKDF-SHA256'),
    salt: z.string().min(1),
  }),
]);
type SlotKdfParams = z.infer<typeof SlotKdfParamsSchema>;

export type { SlotKdfParams };

/** Parse stored kdfParams; throws on an unknown method (`password` included) or a malformed object. */
export function parseSlotKdfParams(value: unknown): SlotKdfParams {
  return SlotKdfParamsSchema.parse(value);
}

/** Mint kdfParams for a NEW passkey slot, recording its credential and transport (D45). */
export function newPasskeySlotParams(
  credentialId: string,
  transport: PasskeyTransport
): SlotKdfParams {
  return { method: 'passkey', credentialId, transport };
}

/** Mint kdfParams for a NEW recovery-code slot (fresh random 16-byte salt). */
export function newRecoverySlotParams(): SlotKdfParams {
  return {
    method: 'recovery',
    algorithm: 'HKDF-SHA256',
    salt: toBase64(randomBytes(16)),
  };
}

/** Public KDF metadata of a machine secret (D46): stored beside its wrapped CEK, never secret. */
export const MachineSecretKdfParamsSchema = z.strictObject({
  algorithm: z.literal('HKDF-SHA256'),
  salt: z.string().min(1),
});
type MachineSecretKdfParams = z.infer<typeof MachineSecretKdfParamsSchema>;

export type { MachineSecretKdfParams };

/** Mint kdfParams for a NEW machine secret (fresh random 16-byte salt). */
export function newMachineSecretParams(): MachineSecretKdfParams {
  return { algorithm: 'HKDF-SHA256', salt: toBase64(randomBytes(16)) };
}

// ─── Generated codes (recovery codes, machine secrets) ──────────────────────

/** Crockford base32: the letters that read as digits or as each other are left out, so a code reads back unambiguously over the phone. */
const CROCKFORD_ALPHABET = '0123456789ABCDEFGHJKMNPQRSTVWXYZ';

const RECOVERY_PREFIX = 'RC1';
const MACHINE_SECRET_PREFIX = 'RM1';
const CODE_GROUPS = 4;
const CODE_GROUP_LENGTH = 8;

/** `<prefix>-` + 4 groups of 8 Crockford base32 chars: 160 bits of entropy. */
function generateCode(prefix: string): string {
  const groups: string[] = [];
  for (let g = 0; g < CODE_GROUPS; g++) {
    let group = '';
    // One byte per char: 256 % 32 === 0, so a byte mod 32 is unbiased.
    const bytes = randomBytes(CODE_GROUP_LENGTH);
    for (let i = 0; i < CODE_GROUP_LENGTH; i++) {
      group += CROCKFORD_ALPHABET[bytes[i] % 32];
    }
    groups.push(group);
  }
  return `${prefix}-${groups.join('-')}`;
}

/**
 * Normalize and validate a typed code: case-insensitive, dashes and spaces optional, prefix
 * optional, and the Crockford aliases folded (the letters that look like 0 and 1 become those
 * digits). Returns the canonical `<prefix>-XXXXXXXX-...` form, or throws on anything that is not
 * exactly 32 valid chars after normalization.
 */
function parseCode(input: string, prefix: string, label: string): string {
  let s = input.toUpperCase().replaceAll(/[\s-]/g, '');
  if (s.startsWith(prefix)) s = s.slice(prefix.length);
  s = s.replaceAll('O', '0').replaceAll(/[IL]/g, '1');

  const expected = CODE_GROUPS * CODE_GROUP_LENGTH;
  if (s.length !== expected) {
    throw new Error(`${label} must have ${expected} characters (got ${s.length})`);
  }
  for (const ch of s) {
    if (!CROCKFORD_ALPHABET.includes(ch)) {
      throw new Error(`${label} contains an invalid character: ${ch}`);
    }
  }

  const groups: string[] = [];
  for (let g = 0; g < CODE_GROUPS; g++) {
    groups.push(s.slice(g * CODE_GROUP_LENGTH, (g + 1) * CODE_GROUP_LENGTH));
  }
  return `${prefix}-${groups.join('-')}`;
}

/**
 * Generate a fresh recovery code: `RC1-` + 4 groups of 8 Crockford base32
 * chars, 160 bits of entropy. Shown to the user ONCE, on the recovery kit
 * (recovery-kit.ts); only its derived slot secret survives.
 */
export function generateRecoveryCode(): string {
  return generateCode(RECOVERY_PREFIX);
}

/**
 * Normalize and validate a user-typed recovery code. Forgiving on input (see `parseCode`); returns
 * the canonical `RC1-XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX` form.
 */
export function parseRecoveryCode(input: string): string {
  return parseCode(input, RECOVERY_PREFIX, 'Recovery code');
}

/**
 * Generate a fresh machine secret (D46): `RM1-` + 4 groups of 8 Crockford base32 chars, 160 bits.
 * Shown once in the portal and handed to the machine out of band.
 */
export function generateMachineSecret(): string {
  return generateCode(MACHINE_SECRET_PREFIX);
}

/** Normalize and validate a machine secret; returns the canonical `RM1-...` form. */
export function parseMachineSecret(input: string): string {
  return parseCode(input, MACHINE_SECRET_PREFIX, 'Machine secret');
}

// ─── Slot secret derivation ─────────────────────────────────────────────────

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

/**
 * Derive the 32-byte wrapping secret of a machine secret: HKDF-SHA256 over the canonical `RM1-`
 * string with the secret's public salt, under its own info string, so a machine secret and a
 * recovery code with the same characters never derive the same secret.
 */
export async function deriveMachineSecretSlotSecret(
  machineSecret: string,
  params: MachineSecretKdfParams
): Promise<Uint8Array> {
  const parsed = MachineSecretKdfParamsSchema.parse(params);
  const canonical = parseMachineSecret(machineSecret);
  return hkdfDeriveRaw(
    new TextEncoder().encode(canonical),
    fromBase64(parsed.salt),
    HKDF_INFO.MACHINE_SECRET
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
