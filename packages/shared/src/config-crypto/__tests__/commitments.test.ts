/**
 * Field commitment tests — FCK derivation, HMAC determinism, anti-downgrade.
 */

import { describe, expect, it } from 'vitest';
import { generateCek } from '../cek.js';
import { canonicalize, valueKind } from '../canonical.js';
import {
  commitField,
  computeCommitments,
  deriveFieldCommitmentKey,
  generateFckSalt,
  verifyCommitment,
} from '../commitments.js';

describe('canonicalize', () => {
  it('is stable across object key-insertion-order differences', () => {
    const a = canonicalize({ x: 1, y: 'hi', z: null });
    const b = canonicalize({ z: null, y: 'hi', x: 1 });
    expect(Buffer.from(a).toString('hex')).toBe(Buffer.from(b).toString('hex'));
  });

  it('distinguishes null from missing, empty-string from empty-array', () => {
    const nullB = canonicalize(null);
    const strB = canonicalize('');
    const arrB = canonicalize([]);
    const missB = canonicalize(undefined);
    const bufs = [nullB, strB, arrB, missB].map((u) => Buffer.from(u).toString('hex'));
    expect(new Set(bufs).size).toBe(4);
  });

  it('distinguishes numbers from numeric strings', () => {
    const num = Buffer.from(canonicalize(42)).toString('hex');
    const str = Buffer.from(canonicalize('42')).toString('hex');
    expect(num).not.toBe(str);
  });

  it('rejects non-finite numbers', () => {
    expect(() => canonicalize(Infinity)).toThrow();
    expect(() => canonicalize(NaN)).toThrow();
  });
});

describe('valueKind', () => {
  it('distinguishes all typed kinds', () => {
    expect(valueKind(undefined)).toBe('missing');
    expect(valueKind(null)).toBe('null');
    expect(valueKind(true)).toBe('boolean');
    expect(valueKind(42)).toBe('number');
    expect(valueKind('hi')).toBe('string');
    expect(valueKind([])).toBe('array');
    expect(valueKind({})).toBe('object');
    expect(valueKind(new Uint8Array([1, 2, 3]))).toBe('bytes');
  });
});

describe('deriveFieldCommitmentKey', () => {
  it('produces stable FCK for same CEK + salt', async () => {
    const cek = await generateCek();
    const salt = generateFckSalt();
    const fck1 = await deriveFieldCommitmentKey(cek, salt);
    const fck2 = await deriveFieldCommitmentKey(cek, salt);
    const sig1 = await commitField(fck1, '/test', 'value');
    const sig2 = await commitField(fck2, '/test', 'value');
    expect(sig1.hmac).toBe(sig2.hmac);
  });

  it('produces different FCKs for different salts', async () => {
    const cek = await generateCek();
    const salt1 = generateFckSalt();
    const salt2 = generateFckSalt();
    expect(salt1).not.toBe(salt2);
    const fck1 = await deriveFieldCommitmentKey(cek, salt1);
    const fck2 = await deriveFieldCommitmentKey(cek, salt2);
    const sig1 = await commitField(fck1, '/test', 'value');
    const sig2 = await commitField(fck2, '/test', 'value');
    expect(sig1.hmac).not.toBe(sig2.hmac);
  });
});

describe('commitField', () => {
  it('is deterministic for same pointer + value', async () => {
    const cek = await generateCek();
    const fck = await deriveFieldCommitmentKey(cek, generateFckSalt());
    const a = await commitField(fck, '/foo', 'bar');
    const b = await commitField(fck, '/foo', 'bar');
    expect(a.hmac).toBe(b.hmac);
    expect(a.kind).toBe('string');
  });

  it('produces different HMACs for same value under different pointers (path-swap resistance)', async () => {
    const cek = await generateCek();
    const fck = await deriveFieldCommitmentKey(cek, generateFckSalt());
    const a = await commitField(fck, '/foo', 'shared');
    const b = await commitField(fck, '/bar', 'shared');
    expect(a.hmac).not.toBe(b.hmac);
  });

  it('produces different HMACs for null vs missing at same pointer', async () => {
    const cek = await generateCek();
    const fck = await deriveFieldCommitmentKey(cek, generateFckSalt());
    const a = await commitField(fck, '/foo', null);
    const b = await commitField(fck, '/foo', undefined);
    expect(a.hmac).not.toBe(b.hmac);
    expect(a.kind).toBe('null');
    expect(b.kind).toBe('missing');
  });
});

describe('computeCommitments round-trip', () => {
  it('computes, submits, verifies — matching values pass', async () => {
    const cek = await generateCek();
    const salt = generateFckSalt();
    const fck = await deriveFieldCommitmentKey(cek, salt);
    const entries = [
      { pointer: '/a/b', value: 'hello' },
      { pointer: '/x/y', value: 42 },
      { pointer: '/z', value: null },
    ];
    const commitments = await computeCommitments(fck, salt, entries);
    expect(commitments.fckSalt).toBe(salt);
    expect(Object.keys(commitments.fields).length).toBe(3);

    for (const { pointer, value } of entries) {
      const ok = await verifyCommitment(fck, pointer, value, commitments.fields[pointer]);
      expect(ok).toBe(true);
    }
  });

  it('rejects a tampered value', async () => {
    const cek = await generateCek();
    const salt = generateFckSalt();
    const fck = await deriveFieldCommitmentKey(cek, salt);
    const commitments = await computeCommitments(fck, salt, [
      { pointer: '/foo', value: 'original' },
    ]);
    const ok = await verifyCommitment(fck, '/foo', 'tampered', commitments.fields['/foo']);
    expect(ok).toBe(false);
  });

  it('rejects a kind change even if HMAC could somehow match (sanity)', async () => {
    const cek = await generateCek();
    const salt = generateFckSalt();
    const fck = await deriveFieldCommitmentKey(cek, salt);
    const commitments = await computeCommitments(fck, salt, [
      { pointer: '/foo', value: 'original' },
    ]);
    // Inject a commitment whose kind says "null" but HMAC is the string HMAC.
    // verifyCommitment checks kind first → must fail.
    const fake = { ...commitments.fields['/foo'], kind: 'null' as const };
    const ok = await verifyCommitment(fck, '/foo', 'original', fake);
    expect(ok).toBe(false);
  });
});
