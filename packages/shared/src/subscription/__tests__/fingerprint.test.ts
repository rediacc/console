import { describe, expect, it } from 'vitest';
import { computePublicKeyId, isValidPublicKeyId, PUBLIC_KEY_ID_PATTERN } from '../fingerprint.js';

// Cross-language fixture — MUST stay byte-identical to the Go side
// (private/renet/pkg/subscription/fingerprint_test.go) and the account
// integration copy. A divergence here vs. Go produces an infinite license
// reissue loop in production.
const FIXTURE = {
  spki: 'MCowBQYDK2VwAyEAlNAlNC16kCqsgeublscCu3MrLEELek5uszZN9ikM0Zw=',
  raw: 'lNAlNC16kCqsgeublscCu3MrLEELek5uszZN9ikM0Zw=',
  fingerprint: '7f476ea2d0a3eb2d',
} as const;

describe('computePublicKeyId', () => {
  it('matches the known cross-language vector for SPKI input', async () => {
    expect(await computePublicKeyId(FIXTURE.spki)).toBe(FIXTURE.fingerprint);
  });

  it('produces the same fingerprint for bare 32-byte raw input', async () => {
    expect(await computePublicKeyId(FIXTURE.raw)).toBe(FIXTURE.fingerprint);
  });

  it('SPKI and raw inputs are equivalent', async () => {
    const fromSpki = await computePublicKeyId(FIXTURE.spki);
    const fromRaw = await computePublicKeyId(FIXTURE.raw);
    expect(fromSpki).toBe(fromRaw);
  });

  it('always returns a 16-char lowercase hex string', async () => {
    const id = await computePublicKeyId(FIXTURE.spki);
    expect(id).toMatch(PUBLIC_KEY_ID_PATTERN);
    expect(id).toHaveLength(16);
  });

  it('throws on input shorter than 32 bytes', async () => {
    // 16 zero bytes, base64
    const tooShort = btoa(String.fromCharCode(...new Array(16).fill(0)));
    await expect(computePublicKeyId(tooShort)).rejects.toThrow(/at least 32 bytes/);
  });
});

describe('isValidPublicKeyId', () => {
  it('accepts a well-formed fingerprint', () => {
    expect(isValidPublicKeyId(FIXTURE.fingerprint)).toBe(true);
  });

  it('rejects legacy/short/uppercase ids', () => {
    expect(isValidPublicKeyId('default')).toBe(false);
    expect(isValidPublicKeyId('v1')).toBe(false);
    expect(isValidPublicKeyId('7F476EA2D0A3EB2D')).toBe(false);
    expect(isValidPublicKeyId('7f476ea2d0a3eb2')).toBe(false); // 15 chars
    expect(isValidPublicKeyId('7f476ea2d0a3eb2dd')).toBe(false); // 17 chars
  });
});
