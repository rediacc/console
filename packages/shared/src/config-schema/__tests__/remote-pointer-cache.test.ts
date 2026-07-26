/**
 * Remote pointer cache metadata (offline read cache).
 *
 * The `remote` pointer carries two host-local cache fields — `cachedVersion`
 * (server envelope version of the last successful pull/push) and `cachedAt`
 * (ISO timestamp). They must parse through the strict schema, round-trip, and
 * leave `hasRemoteConfig` untouched (the pointer is valid with or without them).
 */

import { describe, expect, it } from 'vitest';
import { createEmptyRdcConfig, hasRemoteConfig, RdcConfigSchema } from '../schemas.js';

const POINTER = {
  apiUrl: 'https://eu.rediacc.com',
  storeId: '3f2a1b0c-9d8e-4f7a-8b6c-5d4e3f2a1b0c',
  configId: '4a3b2c1d-0e9f-4a8b-9c7d-6e5f4a3b2c1d',
  storageKeyId: 'rdc:pk:key-1',
};

describe('RemoteConfigSchema cache metadata', () => {
  it('parses a pointer carrying cachedVersion/cachedAt and round-trips both', () => {
    const config = {
      ...createEmptyRdcConfig(),
      remote: { ...POINTER, cachedVersion: 7, cachedAt: '2026-07-22T10:00:00.000Z' },
    };

    const parsed = RdcConfigSchema.parse(config);
    expect(parsed.remote?.cachedVersion).toBe(7);
    expect(parsed.remote?.cachedAt).toBe('2026-07-22T10:00:00.000Z');
  });

  it('keeps both cache fields optional (pre-cache bare pointers still parse)', () => {
    const config = { ...createEmptyRdcConfig(), remote: { ...POINTER } };

    const parsed = RdcConfigSchema.parse(config);
    expect(parsed.remote?.cachedVersion).toBeUndefined();
    expect(parsed.remote?.cachedAt).toBeUndefined();
  });

  it('hasRemoteConfig is unchanged by the cache fields', () => {
    const bare = { ...createEmptyRdcConfig(), remote: { ...POINTER } };
    const cached = {
      ...createEmptyRdcConfig(),
      remote: { ...POINTER, cachedVersion: 1, cachedAt: '2026-07-22T10:00:00.000Z' },
    };

    expect(hasRemoteConfig(RdcConfigSchema.parse(bare))).toBe(true);
    expect(hasRemoteConfig(RdcConfigSchema.parse(cached))).toBe(true);
    expect(hasRemoteConfig(createEmptyRdcConfig())).toBe(false);
  });

  it('rejects a non-integer cachedVersion', () => {
    const config = { ...createEmptyRdcConfig(), remote: { ...POINTER, cachedVersion: 1.5 } };
    expect(() => RdcConfigSchema.parse(config)).toThrow();
  });
});
