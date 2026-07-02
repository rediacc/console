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
      exists: vi.fn(),
      init: vi.fn(),
      save: vi.fn(),
      update: vi.fn(),
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

vi.mock('../../adapters/remote-config-adapter.js', () => ({
  RemoteConfigAdapter: MockRemoteConfigAdapter,
}));

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

vi.mock('../resource-state.js', () => ({
  LocalResourceState: { load: mockLocalResourceStateLoad },
  RemoteResourceState: { load: mockRemoteResourceStateLoad },
}));

// Mock master-password resolver (required when masterPassword is set)
vi.mock('../master-password.js', () => ({
  requireMasterPassword: vi.fn().mockResolvedValue('test-password'),
}));

// ─── Tests ───────────────────────────────────────────────────────────────

describe('ConfigServiceBase remote integration', () => {
  let ConfigServiceBase: typeof import('../config-base.js').ConfigServiceBase;
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
    const mod = await import('../config-base.js');
    ConfigServiceBase = mod.ConfigServiceBase;
    service = new ConfigServiceBase();

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

      const mockLocalState = { getMachines: vi.fn() };
      mockLocalResourceStateLoad.mockResolvedValue(mockLocalState);

      const state = await service.getResourceState();

      expect(mockLocalResourceStateLoad).toHaveBeenCalledWith(
        localConfig,
        'rediacc',
        null // no master password
      );
      expect(state).toBe(mockLocalState);
    });

    it('should cache resource state on second call', async () => {
      mockConfigFileStorage.getOrCreateDefault.mockResolvedValue(localConfig);
      const mockLocalState = { getMachines: vi.fn() };
      mockLocalResourceStateLoad.mockResolvedValue(mockLocalState);

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
