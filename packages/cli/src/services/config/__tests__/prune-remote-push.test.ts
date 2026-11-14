/**
 * `config prune` on a remote-synced config pushes (PR-TASK 09b8bdfa). The prune edit mutates the
 * document it is given and returns it; configFileStorage hands out its in-process cache, so
 * `pushOnce` read the same object as `base` and `merged`, saw "nothing changed" and pushed
 * nothing. The next read then took the server copy back (eu-remote, 2026-11-06).
 *
 * The storage is an in-memory document that, like the real one, returns the SAME object on every
 * load; the adapter keeps every pushed version. Prune, updateSyncedConfig and RemoteResourceState
 * are real.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { RdcConfig } from '../../../types/index.js';

interface Harness {
  cache: RdcConfig;
  serverVersion: number;
  pushed: RdcConfig[];
}

const h = vi.hoisted((): Harness => ({ cache: undefined as never, serverVersion: 7, pushed: [] }));

vi.mock('../../../adapters/config-file-storage.js', () => ({
  configFileStorage: {
    exists: () => Promise.resolve(true),
    load: () => Promise.resolve(h.cache),
    loadDecrypted: () => Promise.resolve(h.cache),
    updateCache: (_name: string, updater: (c: RdcConfig) => RdcConfig) => {
      h.cache = updater(structuredClone(h.cache));
      return Promise.resolve(h.cache);
    },
  },
}));
vi.mock('../../../adapters/remote-token-storage.js', () => ({ remoteTokenStorage: {} }));
vi.mock('../../../utils/secure-storage.js', () => ({ getSecureStorage: () => ({}) }));
vi.mock('../push-visibility.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../push-visibility.js')>()),
  announcePush: () => undefined,
}));

const adapter = {
  pull: () =>
    Promise.resolve({
      config: structuredClone(h.pushed.at(-1) ?? h.cache),
      version: h.serverVersion,
      sdkEpoch: 1,
    }),
  push: (doc: RdcConfig, current: number) => {
    if (current !== h.serverVersion) return Promise.reject(new Error('unexpected version'));
    h.pushed.push(structuredClone(doc));
    h.serverVersion = current + 1;
    return Promise.resolve({ version: h.serverVersion });
  },
};

vi.mock('../config-resources.js', async () => {
  const { RemoteResourceState } = await import('../resource-state.js');
  const service = {
    getEffectiveConfigName: () => 'eu',
    getCurrent: () => Promise.resolve(h.cache),
    getResourceState: () =>
      Promise.resolve(
        RemoteResourceState.load(h.cache, 'eu', adapter as never, h.serverVersion, 1)
      ),
    resetResourceView: () => undefined,
  };
  return { configService: service };
});

import { applyConfigPrune } from '../config-prune.js';

function config(): RdcConfig {
  return {
    schemaVersion: 3,
    id: '00000000-0000-0000-0000-000000000000',
    version: 12,
    remote: {
      apiUrl: 'https://account.example.com',
      storeId: '11111111-1111-4111-8111-111111111111',
      configId: '22222222-2222-4222-8222-222222222222',
      storageKeyId: 'rdc:pk:key-1',
      cachedVersion: 7,
      cachedAt: '2026-11-06T10:00:00.000Z',
    },
    resources: {
      machines: { hostinger: { ip: '1.2.3.4', user: 'root' } },
      repositories: {
        obsram: {
          grand: 'latest',
          placement: { machine: 'obs-lab' },
          tags: { latest: { repositoryGuid: '11111111-1111-4111-8111-111111111111' } },
        },
        shop: {
          grand: 'latest',
          placement: { machine: 'hostinger' },
          tags: { latest: { repositoryGuid: '33333333-3333-4333-8333-333333333333' } },
        },
      },
    },
  } as unknown as RdcConfig;
}

beforeEach(() => {
  h.cache = config();
  h.serverVersion = 7;
  h.pushed = [];
});

describe('config prune on a remote-synced config', () => {
  it('pushes the pruned document as the next server version', async () => {
    await applyConfigPrune({ goneMachineRepos: true, refsOnly: true });

    expect(h.pushed).toHaveLength(1);
    expect(h.serverVersion).toBe(8);
    const pushed = h.pushed[0];
    expect(Object.keys(pushed.resources?.repositories ?? {})).toEqual(['shop']);
    expect(pushed.resources?.deletedRepositories?.map((a) => a.name)).toEqual(['obsram']);
  });

  it('leaves the cache holding the pruned document, so a read does not bring the entries back', async () => {
    await applyConfigPrune({ goneMachineRepos: true, refsOnly: true });

    expect(Object.keys(h.cache.resources?.repositories ?? {})).toEqual(['shop']);
    expect(h.cache.resources?.deletedRepositories).toHaveLength(1);
  });

  it('pushes nothing when there is nothing to prune', async () => {
    await applyConfigPrune({ refsOnly: true });
    expect(h.pushed).toHaveLength(0);
    expect(h.serverVersion).toBe(7);
  });
});
