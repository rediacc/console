import { describe, expect, it } from 'vitest';
import { parseWaitTimeoutMs } from '../duration.js';

describe('parseWaitTimeoutMs', () => {
  it('parses a bare number as seconds and the s/m/h suffixes', () => {
    expect(parseWaitTimeoutMs('90')).toBe(90_000);
    expect(parseWaitTimeoutMs('90s')).toBe(90_000);
    expect(parseWaitTimeoutMs('5m')).toBe(300_000);
    expect(parseWaitTimeoutMs('2h')).toBe(7_200_000);
  });

  it('refuses a malformed value', () => {
    expect(parseWaitTimeoutMs('soon')).toBeUndefined();
    expect(parseWaitTimeoutMs('-5')).toBeUndefined();
  });

  it('refuses a value above the Node timer limit instead of letting it fire at once', () => {
    expect(parseWaitTimeoutMs('2500000')).toBeUndefined();
    expect(parseWaitTimeoutMs('2147483s')).toBe(2_147_483_000);
    expect(parseWaitTimeoutMs('2147484s')).toBeUndefined();
  });
});
