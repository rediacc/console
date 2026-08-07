import { describe, expect, it } from 'vitest';

import { compareVersions, InvalidVersionError, isValidVersion } from '../version';

describe('compareVersions()', () => {
  it('orders numeric versions', () => {
    expect(compareVersions('0.4.41', '0.4.42')).toBe(-1);
    expect(compareVersions('0.4.43', '0.4.42')).toBe(1);
    expect(compareVersions('0.4.42', '0.4.42')).toBe(0);
    expect(compareVersions('1.0.0', '0.99.99')).toBe(1);
  });

  it('strips the v prefix and pre-release/build suffixes', () => {
    expect(compareVersions('v0.4.42', '0.4.42')).toBe(0);
    expect(compareVersions('1.2.3-dev', '1.2.3')).toBe(0);
    expect(compareVersions('1.2.3+build.7', '1.2.3')).toBe(0);
    expect(compareVersions('1.2.3-rc.1+build.7', '1.2.3')).toBe(0);
  });

  it('treats missing trailing segments as zero', () => {
    expect(compareVersions('0.4', '0.4.1')).toBe(-1);
    expect(compareVersions('0.4', '0.4.0')).toBe(0);
  });

  // THE CONTROL for the silent-equal defect. Every one of these returned 0
  // before the fix, and 0 means "same version" to the CLI updater, the
  // background updater, and the account server's minimum-version gate.
  it.each([
    ['1.2.16', '1.2.x'],
    ['x.y.z', '1.2.16'],
    ['garbage', 'garbage'],
    ['', '1.2.16'],
    ['1.2.16', ''],
    ['1.2.16', 'latest'],
    ['1..2', '1.0.2'],
    ['v', '1.0.0'],
  ])('refuses to compare malformed versions (%s, %s)', (a, b) => {
    expect(() => compareVersions(a, b)).toThrow(InvalidVersionError);
    // Whatever it does, it must never claim they are the same version.
    let verdict: number | null = null;
    try {
      verdict = compareVersions(a, b);
    } catch {
      verdict = null;
    }
    expect(verdict).not.toBe(0);
  });

  it('names the offending version in the error', () => {
    expect(() => compareVersions('1.2.16', '1.2.x')).toThrow(/1\.2\.x/);
    try {
      compareVersions('nope', '1.0.0');
      expect.unreachable('compareVersions should have thrown');
    } catch (err) {
      expect(err).toBeInstanceOf(InvalidVersionError);
      expect((err as InvalidVersionError).version).toBe('nope');
      expect((err as Error).name).toBe('InvalidVersionError');
    }
  });
});

describe('isValidVersion()', () => {
  it('accepts the shapes compareVersions can order', () => {
    for (const v of ['1.2.3', 'v1.2.3', '0.4', '1', '1.2.3-dev', '1.2.3+build']) {
      expect(isValidVersion(v)).toBe(true);
    }
  });

  it('rejects everything compareVersions would throw on', () => {
    for (const v of ['', 'v', 'x.y.z', '1.2.x', 'latest', '1..2', 'garbage']) {
      expect(isValidVersion(v)).toBe(false);
    }
  });
});
