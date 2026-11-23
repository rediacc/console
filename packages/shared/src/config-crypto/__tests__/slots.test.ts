/**
 * Key Slot Tests — wrap/unwrap per method, KDF params round-trip and parsing, recovery code and
 * machine secret format and normalization.
 */

import { describe, expect, it } from 'vitest';
import {
  deriveMachineSecretSlotSecret,
  deriveRecoverySlotSecret,
  exportAesKey,
  generateCek,
  generateMachineSecret,
  generateRecoveryCode,
  generateServerSecret,
  newMachineSecretParams,
  newPasskeySlotParams,
  newRecoverySlotParams,
  parseMachineSecret,
  parseRecoveryCode,
  parseSlotKdfParams,
  randomBytes,
  SLOT_METHODS,
  toBase64,
  unwrapCekForSlot,
  wrapCekForSlot,
} from '../index.js';

// One group of the Crockford base32 alphabet: the ten digits and the 22 unambiguous letters.
const GROUP = '[0-9A-HJKMNP-TV-Z]{8}';
const RECOVERY_FORMAT = new RegExp(`^RC1-${GROUP}-${GROUP}-${GROUP}-${GROUP}$`);
const MACHINE_FORMAT = new RegExp(`^RM1-${GROUP}-${GROUP}-${GROUP}-${GROUP}$`);

describe('slot kdfParams', () => {
  it('has exactly the passkey and recovery methods', () => {
    expect([...SLOT_METHODS]).toEqual(['passkey', 'recovery']);
  });

  it('newRecoverySlotParams mints HKDF params with a fresh 16-byte salt', () => {
    const p = newRecoverySlotParams();
    expect(p).toMatchObject({ method: 'recovery', algorithm: 'HKDF-SHA256' });
    if (p.method !== 'recovery') throw new Error('unreachable');
    expect(atob(p.salt).length).toBe(16);
    const q = newRecoverySlotParams();
    if (q.method !== 'recovery') throw new Error('unreachable');
    expect(q.salt).not.toBe(p.salt);
  });

  it('newPasskeySlotParams records the credential and the transport', () => {
    expect(newPasskeySlotParams('cred-1', 'hybrid')).toEqual({
      method: 'passkey',
      credentialId: 'cred-1',
      transport: 'hybrid',
    });
  });

  it('parses every kdfParams a slot can carry', () => {
    expect(parseSlotKdfParams({ method: 'passkey' })).toEqual({ method: 'passkey' });
    expect(
      parseSlotKdfParams({ method: 'passkey', credentialId: 'c', transport: 'internal' })
    ).toEqual({ method: 'passkey', credentialId: 'c', transport: 'internal' });
    const recovery = newRecoverySlotParams();
    expect(parseSlotKdfParams(JSON.parse(JSON.stringify(recovery)))).toEqual(recovery);
  });

  it('refuses a password kdfParams object (D39)', () => {
    expect(() =>
      parseSlotKdfParams({
        method: 'password',
        algorithm: 'PBKDF2-SHA256',
        iterations: 600_000,
        salt: 'oKGio6SlpqeoqaqrrK2urw==',
      })
    ).toThrow();
  });

  it('refuses an unknown transport, an extra field and a recovery slot without a salt', () => {
    expect(() => parseSlotKdfParams({ method: 'passkey', transport: 'carrier-pigeon' })).toThrow();
    expect(() => parseSlotKdfParams({ method: 'passkey', secret: 'x' })).toThrow();
    expect(() => parseSlotKdfParams({ method: 'recovery', algorithm: 'HKDF-SHA256' })).toThrow();
  });

  it('params survive a JSON round-trip and derive the same secret', async () => {
    const rParams = newRecoverySlotParams();
    const code = generateRecoveryCode();
    const r1 = await deriveRecoverySlotSecret(code, rParams);
    const r2 = await deriveRecoverySlotSecret(code, JSON.parse(JSON.stringify(rParams)));
    expect(toBase64(r1)).toBe(toBase64(r2));
  });

  it('deriveRecoverySlotSecret rejects passkey params', async () => {
    await expect(
      deriveRecoverySlotSecret(generateRecoveryCode(), { method: 'passkey' })
    ).rejects.toThrow(/Expected recovery kdfParams/);
  });
});

describe('recovery codes', () => {
  it('generateRecoveryCode matches the RC1 Crockford format', () => {
    for (let i = 0; i < 20; i++) {
      expect(generateRecoveryCode()).toMatch(RECOVERY_FORMAT);
    }
  });

  it('two generated codes differ', () => {
    expect(generateRecoveryCode()).not.toBe(generateRecoveryCode());
  });

  it('parseRecoveryCode is identity on canonical codes', () => {
    const code = generateRecoveryCode();
    expect(parseRecoveryCode(code)).toBe(code);
  });

  it('normalizes case, separators, prefix, and Crockford aliases', () => {
    const canonical = 'RC1-00000000-11111111-ABCDEFGH-JKMNPQRS';
    expect(parseRecoveryCode('rc1-OOOOOOOO-IIIILLLL-abcdefgh-jkmnpqrs')).toBe(canonical);
    expect(parseRecoveryCode('00000000111111 11ABCDEFGHJKMNPQRS')).toBe(canonical);
  });

  it('rejects wrong length and invalid characters', () => {
    expect(() => parseRecoveryCode('RC1-SHORT')).toThrow(/must have 32 characters/);
    expect(() => parseRecoveryCode('U'.repeat(32))).toThrow(/invalid character/);
  });

  it('aliased and canonical spellings derive the same secret', async () => {
    const params = newRecoverySlotParams();
    const s1 = await deriveRecoverySlotSecret('RC1-00000000-11111111-ABCDEFGH-JKMNPQRS', params);
    const s2 = await deriveRecoverySlotSecret('oooooooo iiiillll abcdefgh jkmnpqrs', params);
    expect(toBase64(s1)).toBe(toBase64(s2));
  });
});

describe('machine secrets (D46)', () => {
  it('generateMachineSecret matches the RM1 Crockford format and differs per call', () => {
    for (let i = 0; i < 20; i++) expect(generateMachineSecret()).toMatch(MACHINE_FORMAT);
    expect(generateMachineSecret()).not.toBe(generateMachineSecret());
  });

  it('parseMachineSecret normalizes like a recovery code, under its own prefix', () => {
    expect(parseMachineSecret('rm1 oooooooo iiiillll abcdefgh jkmnpqrs')).toBe(
      'RM1-00000000-11111111-ABCDEFGH-JKMNPQRS'
    );
    expect(() => parseMachineSecret('RM1-SHORT')).toThrow(/Machine secret must have 32/);
  });

  it('a machine secret wraps and unwraps the CEK', async () => {
    const cek = await generateCek();
    const serverSecret = generateServerSecret();
    const params = newMachineSecretParams();
    const secret = generateMachineSecret();
    const slotSecret = await deriveMachineSecretSlotSecret(secret, params);
    const wrapped = await wrapCekForSlot(cek, slotSecret, serverSecret);
    const again = await deriveMachineSecretSlotSecret(secret.toLowerCase(), params);
    const unwrapped = await unwrapCekForSlot(wrapped, again, serverSecret);
    expect(toBase64(await exportAesKey(unwrapped))).toBe(toBase64(await exportAesKey(cek)));
  });

  it('the same characters as a recovery code derive a different secret (domain separation)', async () => {
    const body = '00000000-11111111-ABCDEFGH-JKMNPQRS';
    const salt = 'sLGys7S1tre4ubq7vL2+vw==';
    const machine = await deriveMachineSecretSlotSecret(`RM1-${body}`, {
      algorithm: 'HKDF-SHA256',
      salt,
    });
    const recovery = await deriveRecoverySlotSecret(`RC1-${body}`, {
      method: 'recovery',
      algorithm: 'HKDF-SHA256',
      salt,
    });
    expect(toBase64(machine)).not.toBe(toBase64(recovery));
  });

  it('refuses malformed machine-secret params', async () => {
    await expect(
      deriveMachineSecretSlotSecret(generateMachineSecret(), {
        algorithm: 'PBKDF2-SHA256',
        salt: 'x',
      } as never)
    ).rejects.toThrow();
  });
});

describe('wrapCekForSlot / unwrapCekForSlot', () => {
  it('passkey-style slot: raw PRF secret wraps and unwraps', async () => {
    const cek = await generateCek();
    const serverSecret = generateServerSecret();
    const prfSecret = randomBytes(32);

    const wrapped = await wrapCekForSlot(cek, prfSecret, serverSecret);
    const unwrapped = await unwrapCekForSlot(wrapped, prfSecret, serverSecret);
    expect(toBase64(await exportAesKey(unwrapped))).toBe(toBase64(await exportAesKey(cek)));
  });

  it('recovery slot: generated code wraps and unwraps', async () => {
    const cek = await generateCek();
    const serverSecret = generateServerSecret();
    const params = newRecoverySlotParams();
    const code = generateRecoveryCode();
    const secret = await deriveRecoverySlotSecret(code, params);

    const wrapped = await wrapCekForSlot(cek, secret, serverSecret);
    // Simulate the user typing the code back later, sloppily.
    const retyped = await deriveRecoverySlotSecret(code.toLowerCase().replaceAll('-', ' '), params);
    const unwrapped = await unwrapCekForSlot(wrapped, retyped, serverSecret);
    expect(toBase64(await exportAesKey(unwrapped))).toBe(toBase64(await exportAesKey(cek)));
  });

  it('a wrong recovery code fails cleanly (GCM auth error, no partial plaintext)', async () => {
    const cek = await generateCek();
    const serverSecret = generateServerSecret();
    const params = newRecoverySlotParams();
    const right = await deriveRecoverySlotSecret(generateRecoveryCode(), params);
    const wrong = await deriveRecoverySlotSecret(generateRecoveryCode(), params);

    const wrapped = await wrapCekForSlot(cek, right, serverSecret);
    await expect(unwrapCekForSlot(wrapped, wrong, serverSecret)).rejects.toThrow();
  });

  it('right secret against the wrong server secret fails', async () => {
    const cek = await generateCek();
    const secret = await deriveRecoverySlotSecret(generateRecoveryCode(), newRecoverySlotParams());

    const wrapped = await wrapCekForSlot(cek, secret, generateServerSecret());
    await expect(unwrapCekForSlot(wrapped, secret, generateServerSecret())).rejects.toThrow();
  });
});
