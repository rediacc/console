/**
 * `rdc config set|clear` and the language setting on a REMOTE config push the edit to the store.
 *
 * `account` and `defaults` follow the store with no local override (operator ruling D3,
 * PLAN-config-sync-hardening F5), so an edit written only to the local cache would be overwritten by
 * the next pull. The real RemoteResourceState runs here; the file storage and the adapter are mocks.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { RdcConfig } from '../../types/index.js';

const { mockConfigFileStorage, mockAdapter, disk } = vi.hoisted(() => {
  const disk = { current: undefined as unknown };
  return {
    disk,
    mockAdapter: { pull: vi.fn(), push: vi.fn(), testConnection: vi.fn() },
    mockConfigFileStorage: {
      exists: vi.fn(() => Promise.resolve(true)),
      getOrCreateDefault: vi.fn(() => Promise.resolve(disk.current)),
      load: vi.fn(() => Promise.resolve(disk.current)),
      loadDecrypted: vi.fn(() => Promise.resolve(structuredClone(disk.current))),
      update: vi.fn(),
      updateCache: vi.fn((_name: string, updater: (c: RdcConfig) => RdcConfig) => {
        disk.current = updater(structuredClone(disk.current) as RdcConfig);
        return Promise.resolve(disk.current);
      }),
    },
  };
});

vi.mock('../../adapters/config-file-storage.js', () => ({
  configFileStorage: mockConfigFileStorage,
}));

vi.mock('../../adapters/remote-config-adapter.js', async (importOriginal) => {
  const original = await importOriginal<typeof import('../../adapters/remote-config-adapter.js')>();
  return {
    ...original,
    RemoteConfigAdapter: class {
      constructor() {
        return mockAdapter;
      }
    },
  };
});

vi.mock('../../adapters/remote-token-storage.js', () => ({ remoteTokenStorage: {} }));
vi.mock('../../utils/secure-storage.js', () => ({ getSecureStorage: () => ({}) }));

const REMOTE = {
  apiUrl: 'https://account.example.com',
  storeId: '11111111-1111-4111-8111-111111111111',
  configId: '22222222-2222-4222-8222-222222222222',
  storageKeyId: 'rdc:pk:key-1',
};

function serverCopy(defaults: Record<string, unknown>): RdcConfig {
  return {
    schemaVersion: 3,
    id: REMOTE.configId,
    version: 1,
    defaults,
    resources: { machines: { m1: { ip: '10.0.0.1', user: 'root' } } },
  } as unknown as RdcConfig;
}

describe('defaults edits on a remote config', () => {
  let ConfigServiceBase: typeof import('../config/config-base.js').ConfigServiceBase;

  beforeEach(async () => {
    vi.clearAllMocks();
    disk.current = {
      schemaVersion: 3,
      id: REMOTE.configId,
      version: 1,
      remote: REMOTE,
      encryption: { mode: 'plaintext' },
      state: { networkIds: { next: 3000 } },
    };
    ({ ConfigServiceBase } = await import('../config/config-base.js'));
  });

  it('pushes `config set` to the store instead of writing only the cache', async () => {
    mockAdapter.pull.mockResolvedValue({
      config: serverCopy({ universalUser: 'deploy' }),
      version: 4,
      sdkEpoch: 1,
    });
    mockAdapter.push.mockResolvedValue({ version: 5 });
    const service = new ConfigServiceBase();

    await service.setDefault('datastoreSize', '80%');

    expect(mockConfigFileStorage.update).not.toHaveBeenCalled();
    const [pushed, fromVersion] = mockAdapter.push.mock.calls[0] as [RdcConfig, number];
    expect(fromVersion).toBe(4);
    expect(pushed.defaults).toEqual({ universalUser: 'deploy', datastoreSize: '80%' });
    expect(pushed.state).toBeUndefined();
    // The cache follows the push, host-local sections intact.
    const cached = disk.current as RdcConfig;
    expect(cached.defaults).toEqual({ universalUser: 'deploy', datastoreSize: '80%' });
    expect(cached.remote?.cachedVersion).toBe(5);
    expect(cached.state).toEqual({ networkIds: { next: 3000 } });
  });

  it('replays the edit on the fresh server copy after a conflict, keeping the other device`s change', async () => {
    const { RemoteVersionConflictError } = await import('../../adapters/remote-config-adapter.js');
    mockAdapter.pull
      .mockResolvedValueOnce({ config: serverCopy({}), version: 4, sdkEpoch: 1 })
      .mockResolvedValueOnce({
        config: serverCopy({ universalUser: 'from-b' }),
        version: 5,
        sdkEpoch: 1,
      });
    mockAdapter.push
      .mockRejectedValueOnce(new RemoteVersionConflictError('Version conflict'))
      .mockResolvedValueOnce({ version: 6 });
    const service = new ConfigServiceBase();

    await service.setLanguage('de');

    const [replayed, fromVersion] = mockAdapter.push.mock.calls[1] as [RdcConfig, number];
    expect(fromVersion).toBe(5);
    expect(replayed.defaults).toEqual({ universalUser: 'from-b', language: 'de' });
  });

  it('edits a local config on disk as before', async () => {
    disk.current = { schemaVersion: 3, id: 'local', version: 1 };
    const service = new ConfigServiceBase();

    await service.clearDefaults();

    expect(mockConfigFileStorage.update).toHaveBeenCalledTimes(1);
    expect(mockAdapter.push).not.toHaveBeenCalled();
  });
});
