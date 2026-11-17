import { describe, expect, it } from 'vitest';
import { GIB } from '../largeRepoBudget';
import { parseDfAvailBytes, storeSpaceVerdict } from '../storeSpace';

const LOCAL = 'http://127.0.0.1:9100';

describe('storeSpaceVerdict', () => {
  it('fails with the named message when the local store has less free space than needed', () => {
    const v = storeSpaceVerdict({ endpoint: LOCAL, neededBytes: 7 * GIB, freeBytes: 1_900_000 });
    expect(v.kind).toBe('full');
    if (v.kind === 'full') {
      expect(v.message).toContain('backup store disk is full');
      expect(v.message).toContain('account-config-rustfs:/data');
      expect(v.message).toContain('docker builder prune');
    }
  });

  it('passes when the local store has enough', () => {
    expect(
      storeSpaceVerdict({ endpoint: LOCAL, neededBytes: 7 * GIB, freeBytes: 20 * GIB })
    ).toEqual({ kind: 'ok', freeBytes: 20 * GIB });
    expect(
      storeSpaceVerdict({ endpoint: LOCAL, neededBytes: 7 * GIB, freeBytes: 7 * GIB }).kind
    ).toBe('ok');
  });

  it('skips with a reason for a remote store', () => {
    const v = storeSpaceVerdict({
      endpoint: 'https://abc.r2.cloudflarestorage.com',
      neededBytes: GIB,
      freeBytes: undefined,
    });
    expect(v.kind).toBe('skipped');
  });

  it('skips with a reason when the local free space is unreadable', () => {
    expect(
      storeSpaceVerdict({ endpoint: LOCAL, neededBytes: GIB, freeBytes: undefined }).kind
    ).toBe('skipped');
  });
});

describe('parseDfAvailBytes', () => {
  it('reads the number under the header', () => {
    expect(parseDfAvailBytes('      Avail\n19935260672\n')).toBe(19935260672);
    expect(parseDfAvailBytes('Error: no such container')).toBeUndefined();
  });
});
