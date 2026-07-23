import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockConfigFileStorage } = vi.hoisted(() => ({
  mockConfigFileStorage: {
    updateCache: vi.fn(),
    update: vi.fn(),
    save: vi.fn(),
  },
}));

vi.mock('../../adapters/config-file-storage.js', () => ({
  configFileStorage: mockConfigFileStorage,
}));

import type { RdcConfig } from '../../types/index.js';
import {
  formatStaleCacheWarning,
  mergeRemoteIntoCache,
  writeRemoteCache,
} from '../config/remote-cache.js';

const REMOTE = {
  apiUrl: 'https://account.example.com',
  storeId: '11111111-1111-4111-8111-111111111111',
  configId: '22222222-2222-4222-8222-222222222222',
  storageKeyId: 'rdc:pk:key-1',
};

const local: RdcConfig = {
  schemaVersion: 3,
  id: 'local-id',
  version: 9,
  remote: { ...REMOTE, cachedVersion: 3, cachedAt: '2026-07-01T00:00:00.000Z' },
  encryption: { mode: 'master-password' },
  state: { repos: { shop: { latest: { networkId: 4 } } } },
  account: { userEmail: 'me@example.com', accountServer: 'https://eu.rediacc.com' },
  defaults: { language: 'tr' },
  resources: { machines: { old: { ip: '10.0.0.1', user: 'root' } } },
} as unknown as RdcConfig;

const pulled: RdcConfig = {
  schemaVersion: 3,
  id: 'remote-id',
  version: 2,
  resources: {
    machines: { prod: { ip: '10.0.0.5', user: 'deploy' } },
    storages: { s1: { provider: 's3' } },
  },
  credentials: { ssh: { privateKey: 'PRIV' } },
  defaults: { language: 'en', datastoreSize: '90%' },
} as unknown as RdcConfig;

describe('mergeRemoteIntoCache', () => {
  it('takes content from pulled, keeps remote/state/encryption from local, stamps cache metadata', () => {
    const merged = mergeRemoteIntoCache(local, pulled, 5);

    // Content sections mirror the pull.
    expect(merged.resources?.machines).toHaveProperty('prod');
    expect(merged.resources?.machines).not.toHaveProperty('old');
    expect(merged.credentials?.ssh?.privateKey).toBe('PRIV');

    // Host-local sections re-applied from local.
    expect(merged.encryption).toEqual({ mode: 'master-password' });
    expect(merged.state).toEqual(local.state);
    expect(merged.remote).toMatchObject({ ...REMOTE, cachedVersion: 5 });
    expect(Date.parse(merged.remote?.cachedAt ?? '')).not.toBeNaN();

    // Local version counter untouched (server version lives in cachedVersion).
    expect(merged.version).toBe(9);
  });

  it('local defaults and account overrides survive over the pulled values', () => {
    const merged = mergeRemoteIntoCache(local, pulled, 5);

    expect(merged.defaults?.language).toBe('tr');
    // Non-overridden pulled defaults still come through.
    expect(merged.defaults?.datastoreSize).toBe('90%');
    expect(merged.account?.userEmail).toBe('me@example.com');
  });

  it('leaves remote undefined when local has no pointer (defensive)', () => {
    const bare = { ...local, remote: undefined };
    const merged = mergeRemoteIntoCache(bare, pulled, 5);
    expect(merged.remote).toBeUndefined();
  });
});

describe('writeRemoteCache', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('writes through the no-bump updateCache path, merging with the on-disk config', async () => {
    mockConfigFileStorage.updateCache.mockImplementation(
      (_name: string, updater: (c: RdcConfig) => RdcConfig) => Promise.resolve(updater(local))
    );

    await writeRemoteCache('cfg', pulled, 5);

    // The version-bumping paths are never touched — cache writes are
    // observations, not declared intent.
    expect(mockConfigFileStorage.updateCache).toHaveBeenCalledTimes(1);
    expect(mockConfigFileStorage.update).not.toHaveBeenCalled();
    expect(mockConfigFileStorage.save).not.toHaveBeenCalled();

    const updater = mockConfigFileStorage.updateCache.mock.calls[0][1] as (
      c: RdcConfig
    ) => RdcConfig;
    const written = updater(local);
    expect(written.remote?.cachedVersion).toBe(5);
    expect(written.resources?.machines).toHaveProperty('prod');
    expect(written.version).toBe(9);
  });
});

describe('formatStaleCacheWarning', () => {
  it('names the server, config, cached version, and age', () => {
    const warning = formatStaleCacheWarning(
      { ...REMOTE, cachedVersion: 5, cachedAt: new Date(Date.now() - 5 * 60_000).toISOString() },
      'prod-cfg'
    );
    expect(warning).toContain('https://account.example.com');
    expect(warning).toContain('prod-cfg');
    expect(warning).toContain('5');
    expect(warning).toMatch(/\d+m/);
  });
});
