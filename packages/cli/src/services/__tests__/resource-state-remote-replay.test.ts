/**
 * RemoteResourceState write policy (D3/D4): push-on-mutate with fail-closed
 * unreachable handling and bucket-scoped 409 replay.
 *
 * The adapter is a plain mock injected through `RemoteResourceState.load`;
 * the error classes are the REAL ones from remote-config-adapter (persist
 * classifies by instanceof).
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockConfigFileStorage } = vi.hoisted(() => ({
  mockConfigFileStorage: {
    loadDecrypted: vi.fn(),
    updateCache: vi.fn(),
    update: vi.fn(),
    save: vi.fn(),
  },
}));

vi.mock('../../adapters/config-file-storage.js', () => ({
  configFileStorage: mockConfigFileStorage,
}));

import {
  type RemoteConfigAdapter,
  RemoteUnreachableError,
  RemoteVersionConflictError,
} from '../../adapters/remote-config-adapter.js';
import type { RdcConfig } from '../../types/index.js';
import { RemoteResourceState } from '../config/resource-state.js';

const CONFIG_NAME = 'replay-test';
const API_URL = 'https://account.example.com';

const baseConfig = {
  schemaVersion: 3,
  id: 'cfg-id',
  version: 2,
  remote: {
    apiUrl: API_URL,
    storeId: '11111111-1111-4111-8111-111111111111',
    configId: '22222222-2222-4222-8222-222222222222',
    storageKeyId: 'rdc:pk:key-1',
    cachedVersion: 4,
    cachedAt: '2026-07-22T08:00:00.000Z',
  },
  encryption: { mode: 'plaintext' },
  resources: {
    machines: { m1: { ip: '10.0.0.1', user: 'root' } },
    storages: { sOld: { provider: 's3' } },
  },
} as unknown as RdcConfig;

function createAdapter() {
  return {
    pull: vi.fn(),
    push: vi.fn(),
    testConnection: vi.fn(),
  };
}

function loadState(adapter: ReturnType<typeof createAdapter>, version = 4) {
  return RemoteResourceState.load(
    structuredClone(baseConfig),
    CONFIG_NAME,
    adapter as unknown as RemoteConfigAdapter,
    version,
    1
  );
}

describe('RemoteResourceState persist', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockConfigFileStorage.loadDecrypted.mockResolvedValue(structuredClone(baseConfig));
    mockConfigFileStorage.updateCache.mockResolvedValue(undefined);
  });

  it('pushes, tracks the new version, and refreshes the cache on success', async () => {
    const adapter = createAdapter();
    adapter.push.mockResolvedValue({ version: 5 });
    const state = loadState(adapter);

    await state.setMachines({
      m1: { ip: '10.0.0.1', user: 'root' },
      m2: { ip: '10.0.0.2', user: 'root' },
    });

    expect(adapter.push).toHaveBeenCalledTimes(1);
    const [pushDoc, currentVersion] = adapter.push.mock.calls[0] as [RdcConfig, number];
    expect(currentVersion).toBe(4);
    expect(pushDoc.state).toBeUndefined();
    expect(pushDoc.resources?.machines).toHaveProperty('m2');

    // Cache follows the push, stamped with the server's new version.
    expect(mockConfigFileStorage.updateCache).toHaveBeenCalledTimes(1);
    const updater = mockConfigFileStorage.updateCache.mock.calls[0][1] as (
      c: RdcConfig
    ) => RdcConfig;
    const written = updater(structuredClone(baseConfig));
    expect(written.remote?.cachedVersion).toBe(5);
    expect(written.resources?.machines).toHaveProperty('m2');
  });

  it('replays a 409 by re-applying ONLY the mutated bucket over the fresh pull', async () => {
    const adapter = createAdapter();
    // First push conflicts; the fresh pull is at v5 with a DIFFERENT bucket
    // changed (storages) by the other device; second push succeeds at v6.
    adapter.push
      .mockRejectedValueOnce(new RemoteVersionConflictError('Version conflict: current is 5'))
      .mockResolvedValueOnce({ version: 6 });
    adapter.pull.mockResolvedValue({
      config: {
        ...structuredClone(baseConfig),
        resources: {
          machines: { m1: { ip: '10.0.0.1', user: 'root' } },
          storages: { sNew: { provider: 'sftp' } },
        },
      },
      version: 5,
      sdkEpoch: 1,
    });
    const state = loadState(adapter);

    await state.setMachines({
      m1: { ip: '10.0.0.1', user: 'root' },
      m2: { ip: '10.0.0.2', user: 'root' },
    });

    expect(adapter.push).toHaveBeenCalledTimes(2);
    const [replayDoc, replayVersion] = adapter.push.mock.calls[1] as [RdcConfig, number];
    // Replay is based on the fresh server version...
    expect(replayVersion).toBe(5);
    // ...carries the OTHER device's storages change...
    expect(replayDoc.resources?.storages).toHaveProperty('sNew');
    expect(replayDoc.resources?.storages).not.toHaveProperty('sOld');
    // ...and re-applies our machines mutation.
    expect(replayDoc.resources?.machines).toHaveProperty('m2');

    expect(mockConfigFileStorage.updateCache).toHaveBeenCalledTimes(1);
  });

  it('gives up after 3 conflicting attempts with the retry-exhausted error', async () => {
    const adapter = createAdapter();
    adapter.push.mockRejectedValue(new RemoteVersionConflictError('Version conflict'));
    adapter.pull.mockResolvedValue({
      config: structuredClone(baseConfig),
      version: 9,
      sdkEpoch: 1,
    });
    const state = loadState(adapter);

    await expect(state.setStorages({ s2: { provider: 's3', vaultContent: {} } })).rejects.toThrow(
      /still conflicting/
    );

    // Loop shape: 3 pushes, 2 re-pulls (no pull after the final attempt).
    expect(adapter.push).toHaveBeenCalledTimes(3);
    expect(adapter.pull).toHaveBeenCalledTimes(2);
    expect(mockConfigFileStorage.updateCache).not.toHaveBeenCalled();
  });

  it('fails closed when the server is unreachable: no cache write, no local write', async () => {
    const adapter = createAdapter();
    adapter.push.mockRejectedValue(new RemoteUnreachableError(API_URL, { code: 'ECONNREFUSED' }));
    const state = loadState(adapter);

    const err = await state.setMachines({ m9: { ip: '10.0.0.9', user: 'root' } }).then(
      () => null,
      (e: unknown) => e as Error
    );

    expect(err?.message).toContain(CONFIG_NAME);
    expect(err?.message).toContain(API_URL);
    expect(adapter.pull).not.toHaveBeenCalled();
    expect(mockConfigFileStorage.updateCache).not.toHaveBeenCalled();
    expect(mockConfigFileStorage.update).not.toHaveBeenCalled();
    expect(mockConfigFileStorage.save).not.toHaveBeenCalled();
  });

  it('fails closed when the replay re-pull hits an unreachable server', async () => {
    const adapter = createAdapter();
    adapter.push.mockRejectedValue(new RemoteVersionConflictError('Version conflict'));
    adapter.pull.mockRejectedValue(new RemoteUnreachableError(API_URL, { code: 'ETIMEDOUT' }));
    const state = loadState(adapter);

    await expect(state.setMachines({ m9: { ip: '10.0.0.9', user: 'root' } })).rejects.toThrow(
      /NOT saved/
    );
    expect(mockConfigFileStorage.updateCache).not.toHaveBeenCalled();
  });
});
