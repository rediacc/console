/**
 * The rate grammar, row for row with renet's private/renet/pkg/bwrate/bwrate_test.go. The CLI converts a strategy's or a flag's rate to bytes/second before renet sees it, and renet parses the same strings when an operator types the verb by hand; if the two tables drift, one cap means two speeds.
 */
import { describe, expect, it } from 'vitest';
import {
  bandwidthToBytesPerSecond,
  effectiveBandwidthLimit,
} from '../backup/backup-strategy-validate.js';

const OK: [string, number | undefined][] = [
  ['', undefined],
  ['0', undefined],
  ['12500000', 12_500_000],
  ['12500000B/s', 12_500_000],
  ['12.5M', 12_500_000],
  ['12.5MB', 12_500_000],
  ['12.5MB/s', 12_500_000],
  ['12.5m', 12_500_000],
  ['6M', 6_000_000],
  ['500K', 500_000],
  ['1G', 1_000_000_000],
  ['6Mi', 6 * 2 ** 20],
  ['6MiB', 6 * 2 ** 20],
  ['6MiB/s', 6 * 2 ** 20],
  ['100Mbit', 12_500_000],
  ['100Mbps', 12_500_000],
  ['100Mbit/s', 12_500_000],
  ['100 Mbps', 12_500_000],
  ['1Gbps', 125_000_000],
  ['800Kbit', 100_000],
  ['800bps', 100],
];

const BAD = ['fast', '100Mb', '6iB', '6Mibit', '-5M', '12.5 MB per second', '1bit', 'M'] as const;

describe('bandwidth rate grammar (mirrors renet pkg/bwrate)', () => {
  it.each(OK)('%s -> %s bytes/second', (input, want) => {
    expect(bandwidthToBytesPerSecond(input)).toBe(want);
  });

  it.each(BAD)('refuses %s', (input) => {
    expect(() => bandwidthToBytesPerSecond(input)).toThrow(/Bandwidth limit/);
  });
});

describe('effectiveBandwidthLimit: every set cap binds and the tightest wins', () => {
  it('keeps the strategy cap when a destination cap is looser', () => {
    expect(effectiveBandwidthLimit({ bandwidthLimit: '100Mbps' }, [{ bandwidthLimit: '1G' }])).toBe(
      12_500_000
    );
  });
  it('takes a destination cap tighter than the strategy cap', () => {
    expect(effectiveBandwidthLimit({ bandwidthLimit: '100Mbps' }, [{ bandwidthLimit: '6M' }])).toBe(
      6_000_000
    );
  });
  it('applies the strategy cap to destinations without one', () => {
    expect(effectiveBandwidthLimit({ bandwidthLimit: '12.5M' }, [{}, {}])).toBe(12_500_000);
  });
  it('is unlimited only when no cap is set anywhere', () => {
    expect(effectiveBandwidthLimit({}, [{}])).toBeUndefined();
  });
});
