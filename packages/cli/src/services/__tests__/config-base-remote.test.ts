import { beforeEach, describe, expect, it, vi } from 'vitest';

// ─── Hoisted Mocks ──────────────────────────────────────────────────────

const {
  mockConfigFileStorage,
  MockRemoteConfigAdapter,
  mockRemoteTokenStorage,
  mockGetSecureStorage,
  mockAdapterInstance,
} = vi.hoisted(() => {
  const mockAdapterInstance = {
    pull: vi.fn(),
    push: vi.fn(),
    testConnection: vi.fn(),
  };

  // Must be a real class so `new Adapter(...)` works in the source
  class MockRemoteConfigAdapter {
    constructor(..._args: unknown[]) {
      return mockAdapterInstance;
    }
  }

  return {
    mockConfigFileStorage: {
      getOrCreateDefault: vi.fn(),
      load: vi.fn(),
      loadDecrypted: vi.fn(),
      exists: vi.fn(),
      init: vi.fn(),
      save: vi.fn(),
      update: vi.fn(),
      updateCache: vi.fn(),
      list: vi.fn(),
      delete: vi.fn(),
      clearCache: vi.fn(),
    },
    MockRemoteConfigAdapter,
    mockRemoteTokenStorage: { get: vi.fn(), set: vi.fn(), updateToken: vi.fn(), delete: vi.fn() },
    mockGetSecureStorage: vi.fn(() => ({
      get: vi.fn(),
      set: vi.fn(),
      delete: vi.fn(),
      type: 'mock',
    })),
    mockAdapterInstance,
  };
});

vi.mock('../../adapters/config-file-storage.js', () => ({
  configFileStorage: mockConfigFileStorage,
}));

vi.mock('../../adapters/remote-config-adapter.js', async (importOriginal) => {
  // Keep the real error classes (loadRemote branches on RemoteUnreachableError
  // via instanceof) but stub the adapter itself.
  const original = await importOriginal<typeof import('../../adapters/remote-config-adapter.js')>();
  return { ...original, RemoteConfigAdapter: MockRemoteConfigAdapter };
});

vi.mock('../../adapters/remote-token-storage.js', () => ({
  remoteTokenStorage: mockRemoteTokenStorage,
}));

vi.mock('../../utils/secure-storage.js', () => ({
  getSecureStorage: mockGetSecureStorage,
}));

// Mock resource-state module for getResourceState tests
const { mockLocalResourceStateLoad, mockRemoteResourceStateLoad } = vi.hoisted(() => ({
  mockLocalResourceStateLoad: vi.fn(),
  mockRemoteResourceStateLoad: vi.fn(),
}));

vi.mock('../config/resource-state.js', () => ({
  LocalResourceState: { load: mockLocalResourceStateLoad },
  RemoteResourceState: { load: mockRemoteResourceStateLoad },
}));

// Mock master-password resolver (required when masterPassword is set)
vi.mock('../core/master-password.js', () => ({
  requireMasterPassword: vi.fn().mockResolvedValue('test-password'),
}));

// ─── Tests ───────────────────────────────────────────────────────────────

describe('ConfigServiceBase remote integration', () => {
  let ConfigServiceBase: typeof import('../config/config-base.js').ConfigServiceBase;
  let service: InstanceType<typeof ConfigServiceBase>;

  const localConfig = {
    schemaVersion: 2 as const,
    id: 'local-id',
    version: 1,
    resources: { machines: { m1: { ip: '10.0.0.1', user: 'root' } } },
  };

  const remotePointer = {
    apiUrl: 'https://account.example.com',
    storeId: 'store-001',
    configId: 'config-001',
    teamId: 'team-001',
    storageKeyId: 'key-001',
  };

  const localConfigWithRemote = {
    ...localConfig,
    remote: remotePointer,
    defaults: { language: 'en' },
  };

  const pulledConfig = {
    schemaVersion: 2 as const,
    id: 'remote-id',
    version: 3,
    resources: {
      machines: { prod: { ip: '10.0.0.5', user: 'deploy' } },
      repositories: {},
      storages: {},
    },
  };

  beforeEach(async () => {
    vi.clearAllMocks();

    // Fresh import each test to reset module-level state
    const mod = await import('../config/config-base.js');
    ConfigServiceBase = mod.ConfigServiceBase;
    service = new ConfigServiceBase();
    // The config-name override is a module-level singleton (config-name.ts), so
    // reset it between tests — a prior test's setRuntimeConfig would otherwise leak.
    service.setRuntimeConfig(null);

    // Ensure we don't pick up env vars
    delete process.env.REDIACC_CONFIG;
  });

  // ─── getCurrent() ─────────────────────────────────────────────────

  describe('getCurrent', () => {
    it('should return local config when no remote field', async () => {
      mockConfigFileStorage.getOrCreateDefault.mockResolvedValue(localConfig);

      const result = await service.getCurrent();

      expect(result).toEqual(localConfig);
      expect(mockAdapterInstance.pull).not.toHaveBeenCalled();
    });

    it('should delegate to RemoteConfigAdapter.pull when remote field is present', async () => {
      mockConfigFileStorage.getOrCreateDefault.mockResolvedValue(localConfigWithRemote);
      mockAdapterInstance.pull.mockResolvedValue({
        config: { ...pulledConfig },
        version: 3,
        sdkEpoch: 42,
      });

      const result = await service.getCurrent();

      expect(mockAdapterInstance.pull).toHaveBeenCalled();
      // Pulled config should have remote pointer and language preserved from local
      expect(result?.remote).toEqual(remotePointer);
      expect(result?.defaults?.language).toBe('en');
      expect(result?.resources?.machines).toHaveProperty('prod');
    });

    it('should cache remote config on second call', async () => {
      mockConfigFileStorage.getOrCreateDefault.mockResolvedValue(localConfigWithRemote);
      mockAdapterInstance.pull.mockResolvedValue({
        config: { ...pulledConfig },
        version: 3,
        sdkEpoch: 42,
      });

      const first = await service.getCurrent();
      const second = await service.getCurrent();

      // pull should only be called once; second call uses cache
      expect(mockAdapterInstance.pull).toHaveBeenCalledTimes(1);
      expect(first).toBe(second);
    });

    it('should return null for non-default config that does not exist', async () => {
      service.setRuntimeConfig('staging');
      mockConfigFileStorage.exists.mockResolvedValue(false);

      const result = await service.getCurrent();
      expect(result).toBeNull();
    });
  });

  // ─── offline read fallback ─────────────────────────────────────────

  describe('offline read fallback', () => {
    const cachedOnDisk = {
      ...localConfig,
      remote: {
        ...remotePointer,
        cachedVersion: 3,
        cachedAt: '2026-07-22T08:00:00.000Z',
      },
      defaults: { language: 'en' },
    };

    async function unreachable() {
      const { RemoteUnreachableError } = await import('../../adapters/remote-config-adapter.js');
      return new RemoteUnreachableError('https://account.example.com', { code: 'ECONNREFUSED' });
    }

    it('serves the cached config with a single stderr warning when the server is unreachable', async () => {
      mockConfigFileStorage.getOrCreateDefault.mockResolvedValue(cachedOnDisk);
      mockConfigFileStorage.loadDecrypted.mockResolvedValue(cachedOnDisk);
      mockAdapterInstance.pull.mockRejectedValue(await unreachable());

      const { outputService } = await import('../core/output.js');
      const warnSpy = vi.spyOn(outputService, 'warn').mockImplementation(() => {});

      const result = await service.getCurrent();

      expect(result?.resources?.machines).toHaveProperty('m1');
      expect(warnSpy).toHaveBeenCalledTimes(1);
      const warning = warnSpy.mock.calls[0][0];
      expect(warning).toContain('https://account.example.com');
      expect(warning).toContain('3');
      warnSpy.mockRestore();
    });

    it('rethrows with a refresh hint when the pointer has no cache yet', async () => {
      // Pre-migration bare pointer: no cachedVersion on disk.
      const bare = { ...localConfigWithRemote };
      mockConfigFileStorage.getOrCreateDefault.mockResolvedValue(bare);
      mockConfigFileStorage.loadDecrypted.mockResolvedValue(bare);
      mockAdapterInstance.pull.mockRejectedValue(await unreachable());

      await expect(service.getCurrent()).rejects.toThrow(/config remote refresh/);
    });

    it('rethrows auth errors without falling back to the cache', async () => {
      mockConfigFileStorage.getOrCreateDefault.mockResolvedValue(cachedOnDisk);
      mockConfigFileStorage.loadDecrypted.mockResolvedValue(cachedOnDisk);
      const { RemoteTokenExpiredError } = await import('../../adapters/remote-config-adapter.js');
      mockAdapterInstance.pull.mockRejectedValue(new RemoteTokenExpiredError());

      await expect(service.getCurrent()).rejects.toBeInstanceOf(RemoteTokenExpiredError);
      expect(mockConfigFileStorage.updateCache).not.toHaveBeenCalled();
    });

    it('refreshes the on-disk cache after a successful pull', async () => {
      mockConfigFileStorage.getOrCreateDefault.mockResolvedValue(cachedOnDisk);
      mockAdapterInstance.pull.mockResolvedValue({
        config: { ...pulledConfig },
        version: 4,
        sdkEpoch: 42,
      });
      mockConfigFileStorage.updateCache.mockResolvedValue(cachedOnDisk);

      await service.getCurrent();

      expect(mockConfigFileStorage.updateCache).toHaveBeenCalledTimes(1);
      expect(mockConfigFileStorage.updateCache).toHaveBeenCalledWith(
        'rediacc',
        expect.any(Function)
      );
    });
  });

  // ─── getResourceState() ───────────────────────────────────────────

  describe('getResourceState', () => {
    it('should return RemoteResourceState when remote field is present', async () => {
      mockConfigFileStorage.getOrCreateDefault.mockResolvedValue(localConfigWithRemote);
      mockAdapterInstance.pull.mockResolvedValue({
        config: { ...pulledConfig },
        version: 7,
        sdkEpoch: 99,
      });

      const mockRemoteState = { getMachines: vi.fn() };
      mockRemoteResourceStateLoad.mockResolvedValue(mockRemoteState);

      const state = await service.getResourceState();

      expect(mockRemoteResourceStateLoad).toHaveBeenCalledWith(
        expect.objectContaining({ id: 'remote-id' }),
        'rediacc',
        expect.anything(), // adapter instance
        7,
        99
      );
      expect(state).toBe(mockRemoteState);
    });

    it('should return LocalResourceState when no remote field', async () => {
      mockConfigFileStorage.getOrCreateDefault.mockResolvedValue(localConfig);
      mockConfigFileStorage.loadDecrypted.mockResolvedValue(localConfig);

      const mockLocalState = { getMachines: vi.fn() };
      mockLocalResourceStateLoad.mockReturnValue(mockLocalState);

      const state = await service.getResourceState();

      // v3: encryption is a storage-layer transform, so config-base feeds
      // LocalResourceState a decrypted config (no master-password arg).
      expect(mockLocalResourceStateLoad).toHaveBeenCalledWith(localConfig, 'rediacc');
      expect(state).toBe(mockLocalState);
    });

    it('should cache resource state on second call', async () => {
      mockConfigFileStorage.getOrCreateDefault.mockResolvedValue(localConfig);
      mockConfigFileStorage.loadDecrypted.mockResolvedValue(localConfig);
      const mockLocalState = { getMachines: vi.fn() };
      mockLocalResourceStateLoad.mockReturnValue(mockLocalState);

      const first = await service.getResourceState();
      const second = await service.getResourceState();

      expect(mockLocalResourceStateLoad).toHaveBeenCalledTimes(1);
      expect(first).toBe(second);
    });

    it('should throw when no active config', async () => {
      service.setRuntimeConfig('nonexistent');
      mockConfigFileStorage.exists.mockResolvedValue(false);

      await expect(service.getResourceState()).rejects.toThrow('No active config');
    });
  });
});
