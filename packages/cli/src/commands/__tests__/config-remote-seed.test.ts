/**
 * Seed-on-enable (`finalizeEnable` / `applyHandoff`).
 *
 * The five contract cases: fresh store seeds at version 0→1 with a
 * state/remote-free doc; a missing handoff configId is minted from the local
 * config's id; a differing existing store aborts without --force on a non-TTY
 * (credentials cleaned up); --force replaces local content with the server
 * copy; any non-404 pull error aborts with the local file untouched.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

// ─── Hoisted Mocks ──────────────────────────────────────────────────────

const {
  mockConfigFileStorage,
  mockAdapterInstance,
  MockRemoteConfigAdapter,
  adapterCtorArgs,
  secureMem,
  tokenMem,
  mockAskConfirm,
} = vi.hoisted(() => {
  const mockAdapterInstance = {
    pull: vi.fn(),
    push: vi.fn(),
    testConnection: vi.fn(),
  };
  const adapterCtorArgs: unknown[][] = [];
  class MockRemoteConfigAdapter {
    constructor(...args: unknown[]) {
      adapterCtorArgs.push(args);
      return mockAdapterInstance;
    }
  }
  return {
    mockConfigFileStorage: {
      load: vi.fn(),
      loadDecrypted: vi.fn(),
      save: vi.fn(),
      updateCache: vi.fn(),
      getConfigPath: vi.fn(),
    },
    mockAdapterInstance,
    MockRemoteConfigAdapter,
    adapterCtorArgs,
    secureMem: new Map<string, string>(),
    tokenMem: new Map<string, { token: string; wrappedCek: string }>(),
    mockAskConfirm: vi.fn(),
  };
});

vi.mock('../../adapters/config-file-storage.js', () => ({
  configFileStorage: mockConfigFileStorage,
}));

vi.mock('../../adapters/remote-config-adapter.js', async (importOriginal) => {
  // Keep the real error classes (finalizeEnable/instanceof checks) but stub
  // the adapter itself.
  const original = await importOriginal<typeof import('../../adapters/remote-config-adapter.js')>();
  return { ...original, RemoteConfigAdapter: MockRemoteConfigAdapter };
});

vi.mock('../../adapters/remote-token-storage.js', () => ({
  remoteTokenStorage: {
    get: (name: string) => Promise.resolve(tokenMem.get(name) ?? null),
    set: (name: string, data: { token: string; wrappedCek: string }) => {
      tokenMem.set(name, data);
      return Promise.resolve();
    },
    updateToken: vi.fn(),
    delete: (name: string) => {
      tokenMem.delete(name);
      return Promise.resolve();
    },
  },
}));

vi.mock('../../utils/secure-storage.js', () => ({
  getSecureStorage: () => ({
    type: 'mem',
    get: (k: string) => Promise.resolve(secureMem.get(k) ?? null),
    set: (k: string, v: string) => {
      secureMem.set(k, v);
      return Promise.resolve();
    },
    delete: (k: string) => {
      secureMem.delete(k);
      return Promise.resolve();
    },
  }),
}));

vi.mock('../../utils/prompt.js', () => ({
  askConfirm: mockAskConfirm,
  askPassword: vi.fn(),
}));

import { ConfigServerError } from '../../services/config/config-server-client.js';
import type { RdcConfig } from '../../types/index.js';
import { applyHandoff, finalizeEnable, type PendingRemoteConfig } from '../config-remote-enable.js';
import type { HandoffPayload } from '../config-remote-handoff.js';

// ─── Fixtures ────────────────────────────────────────────────────────────

const CONFIG_NAME = 'seed-test';
const LOCAL_ID = '9a8b7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d';
const STORE_ID = '11111111-1111-4111-8111-111111111111';
const CONFIG_ID = '22222222-2222-4222-8222-222222222222';

const localConfig = {
  schemaVersion: 3,
  id: LOCAL_ID,
  version: 4,
  encryption: { mode: 'plaintext' },
  defaults: { language: 'en' },
  state: { repos: { shop: { latest: { networkId: 2 } } } },
  resources: { machines: { m1: { ip: '10.0.0.1', user: 'root' } } },
} as unknown as RdcConfig;

const serverConfig = {
  schemaVersion: 3,
  id: CONFIG_ID,
  version: 1,
  resources: { machines: { srv: { ip: '10.0.0.9', user: 'deploy' } } },
} as unknown as RdcConfig;

function pendingRemote(configId?: string): PendingRemoteConfig {
  return {
    apiUrl: 'https://account.example.com',
    storeId: STORE_ID,
    configId,
    storageKeyId: 'rdc:pk:handoff-key',
  };
}

function handoffPayload(configId?: string): HandoffPayload {
  return {
    passkey_secret: 'c2VjcmV0',
    token: 'rct_1',
    storageKeyId: 'rdc:pk:handoff-key',
    wrappedCek: 'wrapped',
    storeId: STORE_ID,
    apiUrl: 'https://account.example.com',
    ...(configId ? { configId } : {}),
  };
}

describe('finalizeEnable (seed-on-enable)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    adapterCtorArgs.length = 0;
    secureMem.clear();
    tokenMem.clear();
    delete process.env.REDIACC_YES;
    mockConfigFileStorage.loadDecrypted.mockResolvedValue(structuredClone(localConfig));
    mockConfigFileStorage.save.mockResolvedValue(undefined);
    mockConfigFileStorage.getConfigPath.mockReturnValue(`/tmp/${CONFIG_NAME}.json`);
  });

  it('seeds a fresh store: 404 → push v0 (no state/remote) → pull-back proof → cache written', async () => {
    mockAdapterInstance.pull
      .mockRejectedValueOnce(new ConfigServerError('Config not found', 404))
      .mockResolvedValueOnce({ config: structuredClone(serverConfig), version: 1, sdkEpoch: 1 });
    mockAdapterInstance.push.mockResolvedValue({ version: 1 });

    await finalizeEnable(pendingRemote(CONFIG_ID), CONFIG_NAME);

    // Seed push: currentVersion=0, doc carries neither state nor remote.
    expect(mockAdapterInstance.push).toHaveBeenCalledTimes(1);
    const [seedDoc, currentVersion] = mockAdapterInstance.push.mock.calls[0] as [RdcConfig, number];
    expect(currentVersion).toBe(0);
    expect(seedDoc.state).toBeUndefined();
    expect(seedDoc.remote).toBeUndefined();
    expect(seedDoc.resources?.machines).toHaveProperty('m1');

    // Round-trip proof: a second pull ran.
    expect(mockAdapterInstance.pull).toHaveBeenCalledTimes(2);

    // Cache written: full content + pointer + cachedVersion 1.
    expect(mockConfigFileStorage.save).toHaveBeenCalledTimes(1);
    const saved = mockConfigFileStorage.save.mock.calls[0][0] as RdcConfig;
    expect(saved.remote).toMatchObject({ configId: CONFIG_ID, cachedVersion: 1 });
    expect(saved.resources?.machines).toHaveProperty('srv');
    expect(saved.state).toEqual(localConfig.state);
    expect(saved.encryption).toEqual({ mode: 'plaintext' });
  });

  it('mints the configId from the local config id when the handoff omits it', async () => {
    mockAdapterInstance.pull
      .mockRejectedValueOnce(new ConfigServerError('Config not found', 404))
      .mockResolvedValueOnce({ config: structuredClone(serverConfig), version: 1, sdkEpoch: 1 });
    mockAdapterInstance.push.mockResolvedValue({ version: 1 });

    await finalizeEnable(pendingRemote(undefined), CONFIG_NAME);

    // The adapter was constructed with the minted pointer.
    expect(adapterCtorArgs[0]?.[0]).toMatchObject({ configId: LOCAL_ID });
    const saved = mockConfigFileStorage.save.mock.calls[0][0] as RdcConfig;
    expect(saved.remote?.configId).toBe(LOCAL_ID);
  });

  it('aborts on a differing existing store without --force on a non-TTY, cleaning up credentials', async () => {
    // Existing store: first pull succeeds with content differing from local.
    mockAdapterInstance.pull.mockResolvedValue({
      config: structuredClone(serverConfig),
      version: 3,
      sdkEpoch: 1,
    });

    await expect(applyHandoff(handoffPayload(CONFIG_ID), CONFIG_NAME, {})).rejects.toThrow(
      /--force/
    );

    expect(mockConfigFileStorage.save).not.toHaveBeenCalled();
    expect(mockAskConfirm).not.toHaveBeenCalled();
    // applyHandoff stored the credentials, then cleaned them up on abort.
    expect(secureMem.size).toBe(0);
    expect(tokenMem.size).toBe(0);
  });

  it('replaces local content from the server copy with --force', async () => {
    mockAdapterInstance.pull.mockResolvedValue({
      config: structuredClone(serverConfig),
      version: 3,
      sdkEpoch: 1,
    });

    await finalizeEnable(pendingRemote(CONFIG_ID), CONFIG_NAME, { force: true });

    expect(mockAskConfirm).not.toHaveBeenCalled();
    const saved = mockConfigFileStorage.save.mock.calls[0][0] as RdcConfig;
    expect(saved.resources?.machines).toHaveProperty('srv');
    expect(saved.resources?.machines).not.toHaveProperty('m1');
    expect(saved.remote).toMatchObject({ configId: CONFIG_ID, cachedVersion: 3 });
  });

  it('aborts untouched on any non-404 pull error, cleaning up credentials', async () => {
    mockAdapterInstance.pull.mockRejectedValue(new ConfigServerError('Forbidden', 403));

    await expect(applyHandoff(handoffPayload(CONFIG_ID), CONFIG_NAME, {})).rejects.toThrow(
      'Forbidden'
    );

    expect(mockAdapterInstance.push).not.toHaveBeenCalled();
    expect(mockConfigFileStorage.save).not.toHaveBeenCalled();
    expect(secureMem.size).toBe(0);
    expect(tokenMem.size).toBe(0);
  });
});
