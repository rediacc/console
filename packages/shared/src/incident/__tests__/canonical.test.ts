import { describe, expect, it } from 'vitest';
import { canonicalize, canonicalSha256 } from '../canonical.js';

describe('canonical JSON', () => {
  it('gives the same hash for any key order and spacing', async () => {
    const a = JSON.parse('{"b": 1, "a": {"y": [1, 2], "x": "v"}}');
    const b = JSON.parse('{\n "a":{"x":"v","y":[1,2]},\t"b":1 }');
    expect(canonicalize(a)).toBe('{"a":{"x":"v","y":[1,2]},"b":1}');
    expect(await canonicalSha256(a)).toBe(await canonicalSha256(b));
  });

  it('keeps whitespace inside strings and array order', async () => {
    expect(canonicalize({ a: 'x  y' })).toBe('{"a":"x  y"}');
    expect(await canonicalSha256([1, 2])).not.toBe(await canonicalSha256([2, 1]));
  });

  it('refuses a fraction and accepts a decimal string', () => {
    expect(() => canonicalize({ a: 1.5 })).toThrow(/integers only/);
    expect(() => canonicalize({ a: Number.NaN })).toThrow(/integers only/);
    expect(canonicalize({ a: '1.5' })).toBe('{"a":"1.5"}');
  });

  it('drops undefined members and normalizes negative zero', () => {
    expect(canonicalize({ a: undefined, b: -0 })).toBe('{"b":0}');
  });

  it('hashes known bytes to a known digest', async () => {
    expect(await canonicalSha256({})).toBe(
      '44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a'
    );
  });

  it('refuses a Date or class instance instead of hashing it as {}', () => {
    expect(() => canonicalize(new Date(0) as never)).toThrow(TypeError);
    expect(() => canonicalize(new (class A {})() as never)).toThrow(TypeError);
    expect(canonicalize(Object.create(null) as never)).toBe('{}');
  });
});
