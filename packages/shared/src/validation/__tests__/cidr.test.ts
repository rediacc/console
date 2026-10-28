import { describe, expect, it } from 'vitest';
import { HOSTED_EXECUTOR_SOURCE_RANGES } from '../../config/network.js';
import { SourceRangesSchema } from '../../config-schema/schemas.js';
import { canonicalCidr, cidrContains, isNetworkAddress, parseCidr } from '../cidr.js';

/** Executor source addresses observed in use (PLAN-ssh-key-source-ranges, The ranges). */
const OBSERVED = [
  '104.28.154.80',
  '104.28.163.155',
  '104.28.163.183',
  '104.28.156.1',
  '2a09:bac1:5540:28::3e4:28',
  '2a09:bac5:4e3e:270f::3e4:28',
];

function issues(value: unknown): string[] {
  const result = SourceRangesSchema.safeParse(value);
  return result.success ? [] : result.error.issues.map((i) => i.message);
}

describe('parseCidr', () => {
  it('parses both families and clears host bits into network', () => {
    const v4 = parseCidr('104.28.1.0/16');
    expect(v4).toMatchObject({ family: 4, prefix: 16 });
    expect(v4 && isNetworkAddress(v4)).toBe(false);
    const v6 = parseCidr('2a09:bac0::/29');
    expect(v6).toMatchObject({ family: 6, prefix: 29 });
    expect(v6 && isNetworkAddress(v6)).toBe(true);
  });

  it('refuses what is not a CIDR range', () => {
    for (const bad of [
      '104.28.0.0',
      '104.28.0.0/33',
      '256.0.0.0/8',
      '01.2.3.0/24',
      '104.28.0.0/016',
      '2a09:bac0::/129',
      '2a09::bac0::/29',
      '1:2:3:4:5:6:7:8:9/64',
      'fe80::1%eth0/64',
      '104.28.0.0/16/1',
      'not-a-range',
    ]) {
      expect(parseCidr(bad), bad).toBeNull();
    }
  });

  it('parses /0 (refusing it is the schema policy, not syntax)', () => {
    expect(parseCidr('0.0.0.0/0')).toMatchObject({ prefix: 0 });
  });
});

describe('canonicalCidr', () => {
  it.each([
    ['104.28.1.0/16', '104.28.0.0/16'],
    ['104.28.0.0/16', '104.28.0.0/16'],
    ['10.1.2.3/32', '10.1.2.3/32'],
    ['2a09:bac0::/29', '2a09:bac0::/29'],
    ['2A09:BAC0:0000::/29', '2a09:bac0::/29'],
    ['2a09:bac5:4e3e:270f::3e4:28/29', '2a09:bac0::/29'],
    ['2001:db8:0:0:1:0:0:1/128', '2001:db8::1:0:0:1/128'],
    ['2001:db8:0:1:1:1:1:1/128', '2001:db8:0:1:1:1:1:1/128'],
    ['::ffff:1.2.3.4/128', '::ffff:102:304/128'],
  ])('%s -> %s', (input, canonical) => {
    expect(canonicalCidr(input)).toBe(canonical);
  });

  it('is null for a non-range', () => {
    expect(canonicalCidr('104.28.0.0')).toBeNull();
  });
});

describe('cidrContains', () => {
  const ranges = [...HOSTED_EXECUTOR_SOURCE_RANGES.ipv4, ...HOSTED_EXECUTOR_SOURCE_RANGES.ipv6];
  const inHosted = (address: string) => ranges.some((range) => cidrContains(range, address));

  it.each(OBSERVED)('admits the observed executor source %s under the hosted defaults', (a) => {
    expect(inHosted(a)).toBe(true);
  });

  it.each(['104.29.0.1', '2a09:bac8::1', '104.27.255.255', '2a09:bab7:ffff::1'])(
    'refuses %s, outside the hosted defaults',
    (a) => {
      expect(inHosted(a)).toBe(false);
    }
  );

  it('is false across families and for garbage', () => {
    expect(cidrContains('104.28.0.0/16', '2a09:bac1::1')).toBe(false);
    expect(cidrContains('2a09:bac0::/29', '104.28.0.1')).toBe(false);
    expect(cidrContains('104.28.0.0/16', 'nope')).toBe(false);
    expect(cidrContains('nope', '104.28.0.1')).toBe(false);
  });

  it('matches an IPv4-mapped IPv6 address as its IPv4 address', () => {
    expect(cidrContains('104.28.0.0/16', '::ffff:104.28.163.183')).toBe(true);
    expect(cidrContains('104.28.0.0/16', '::ffff:104.29.0.1')).toBe(false);
  });
});

describe('SourceRangesSchema', () => {
  it('accepts the hosted defaults', () => {
    expect(issues(HOSTED_EXECUTOR_SOURCE_RANGES)).toEqual([]);
  });

  it('refuses host bits and names the canonical form', () => {
    expect(issues({ ipv4: ['104.28.1.0/16'] })).toEqual([
      '104.28.1.0/16 is not a network address; use 104.28.0.0/16',
    ]);
    expect(issues({ ipv6: ['2a09:bac5::/29'] })).toEqual([
      '2a09:bac5::/29 is not a network address; use 2a09:bac0::/29',
    ]);
  });

  it('refuses a /0', () => {
    expect(issues({ ipv4: ['0.0.0.0/0'] })[0]).toMatch(/prefix length above 0/);
    expect(issues({ ipv6: ['::/0'] })[0]).toMatch(/prefix length above 0/);
  });

  it('refuses an IPv4 range in the IPv6 list, and the reverse', () => {
    expect(issues({ ipv6: ['104.28.0.0/16'] })).toEqual([
      '104.28.0.0/16 is an IPv4 range; list it under ipv4',
    ]);
    expect(issues({ ipv4: ['2a09:bac0::/29'] })).toEqual([
      '2a09:bac0::/29 is an IPv6 range; list it under ipv6',
    ]);
  });

  it('refuses a bare address', () => {
    expect(issues({ ipv4: ['104.28.0.1'] })).toEqual(['104.28.0.1 is not an IPv4 CIDR range']);
  });

  it('refuses duplicates after canonicalisation', () => {
    expect(issues({ ipv6: ['2a09:bac0::/29', '2A09:BAC0:0::/29'] })).toEqual([
      '2A09:BAC0:0::/29 duplicates 2a09:bac0::/29 (both are 2a09:bac0::/29)',
    ]);
  });

  it('refuses an empty declaration', () => {
    expect(issues({})).toEqual(['sourceRanges needs at least one ipv4 or ipv6 range']);
    expect(issues({ ipv4: [], ipv6: [] })).toEqual([
      'sourceRanges needs at least one ipv4 or ipv6 range',
    ]);
  });

  it('caps each list at 32 entries', () => {
    const list = (n: number) => Array.from({ length: n }, (_, i) => `10.${i}.0.0/16`);
    expect(issues({ ipv4: list(32) })).toEqual([]);
    expect(issues({ ipv4: list(33) })).toHaveLength(1);
  });
});
