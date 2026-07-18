/**
 * Key Slot Tests — wrap/unwrap per method, KDF params round-trip, recovery
 * code format and normalization.
 */

import { describe, expect, it } from 'vitest';
import {
  derivePasswordSlotSecret,
  deriveRecoverySlotSecret,
  exportAesKey,
  generateCek,
  generateRecoveryCode,
  generateServerSecret,
  newPasswordSlotParams,
  newRecoverySlotParams,
  PASSWORD_PBKDF2_ITERATIONS,
  parseRecoveryCode,
  randomBytes,
  toBase64,
  unwrapCekForSlot,
  wrapCekForSlot,
} from '../index.js';

// Crockford base32: 0-9 + A-Z minus I, L, O, U.
const RECOVERY_FORMAT =
  /^RC1-[0-9A-HJKMNP-TV-Z]{8}-[0-9A-HJKMNP-TV-Z]{8}-[0-9A-HJKMNP-TV-Z]{8}-[0-9A-HJKMNP-TV-Z]{8}$/;

describe('slot kdfParams', () => {
  it('newPasswordSlotParams mints PBKDF2 params with a fresh 16-byte salt', () => {
    const p1 = newPasswordSlotParams();
    const p2 = newPasswordSlotParams();
    expect(p1).toMatchObject({
      method: 'password',
      algorithm: 'PBKDF2-SHA256',
      iterations: PASSWORD_PBKDF2_ITERATIONS,
    });
    if (p1.method !== 'password' || p2.method !== 'password') throw new Error('unreachable');
    expect(atob(p1.salt).length).toBe(16);
    expect(p1.salt).not.toBe(p2.salt);
  });

  it('newRecoverySlotParams mints HKDF params with a fresh 16-byte salt', () => {
    const p = newRecoverySlotParams();
    expect(p).toMatchObject({ method: 'recovery', algorithm: 'HKDF-SHA256' });
    if (p.method !== 'recovery') throw new Error('unreachable');
    expect(atob(p.salt).length).toBe(16);
  });

  it('params survive a JSON round-trip and derive the same secret', async () => {
    const params = newPasswordSlotParams();
    const restored = JSON.parse(JSON.stringify(params));
    const s1 = await derivePasswordSlotSecret('hunter2 but longer', params);
    const s2 = await derivePasswordSlotSecret('hunter2 but longer', restored);
    expect(toBase64(s1)).toBe(toBase64(s2));

    const rParams = newRecoverySlotParams();
    const code = generateRecoveryCode();
    const r1 = await deriveRecoverySlotSecret(code, rParams);
    const r2 = await deriveRecoverySlotSecret(code, JSON.parse(JSON.stringify(rParams)));
    expect(toBase64(r1)).toBe(toBase64(r2));
  });

  it('derive functions reject params for a different method', async () => {
    await expect(derivePasswordSlotSecret('pw', newRecoverySlotParams())).rejects.toThrow(
      /Expected password kdfParams/
    );
    await expect(
      deriveRecoverySlotSecret(generateRecoveryCode(), newPasswordSlotParams())
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

describe('wrapCekForSlot / unwrapCekForSlot', () => {
  it('passkey-style slot: raw PRF secret wraps and unwraps', async () => {
    const cek = await generateCek();
    const serverSecret = generateServerSecret();
    const prfSecret = randomBytes(32);

    const wrapped = await wrapCekForSlot(cek, prfSecret, serverSecret);
    const unwrapped = await unwrapCekForSlot(wrapped, prfSecret, serverSecret);
    expect(toBase64(await exportAesKey(unwrapped))).toBe(toBase64(await exportAesKey(cek)));
  });

  it('password slot: derived secret wraps and unwraps', async () => {
    const cek = await generateCek();
    const serverSecret = generateServerSecret();
    const params = newPasswordSlotParams();
    const secret = await derivePasswordSlotSecret('a sufficiently long passphrase', params);

    const wrapped = await wrapCekForSlot(cek, secret, serverSecret);
    const unwrapped = await unwrapCekForSlot(wrapped, secret, serverSecret);
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

  it('wrong password fails cleanly (GCM auth error, no partial plaintext)', async () => {
    const cek = await generateCek();
    const serverSecret = generateServerSecret();
    const params = newPasswordSlotParams();
    const right = await derivePasswordSlotSecret('the right password', params);
    const wrong = await derivePasswordSlotSecret('the wrong password', params);

    const wrapped = await wrapCekForSlot(cek, right, serverSecret);
    await expect(unwrapCekForSlot(wrapped, wrong, serverSecret)).rejects.toThrow();
  });

  it('right secret against the wrong server secret fails', async () => {
    const cek = await generateCek();
    const params = newPasswordSlotParams();
    const secret = await derivePasswordSlotSecret('the right password', params);

    const wrapped = await wrapCekForSlot(cek, secret, generateServerSecret());
    await expect(unwrapCekForSlot(wrapped, secret, generateServerSecret())).rejects.toThrow();
  });
});
