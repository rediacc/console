/**
 * Device-local pointers survive the whole remote cycle: pull, in-memory load, a resource write, the
 * push, the cache write after it, and a 409 rebase in between; `state` syncs and is merged per repo.
 *
 * The disk is an in-memory document behind a mocked configFileStorage; the server is a fake adapter
 * whose pull returns what `fullConfigToRdcConfig` rebuilds from a copy pushed before state synced
 * (no state, no remote pointer, no renetPath, no verifier, `encryption: plaintext`). Everything between them is the real code:
 * ConfigServiceBase.getCurrent -> loadRemote -> writeRemoteCache -> overlayDeviceLocal ->
 * RemoteResourceState -> persist -> pushOnce -> mergeRemoteIntoCache.
 *
 * F3/F4/F18 and T17 in agent/plans/PLAN-config-sync-hardening.md; renetPath from bd0278084.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { RdcConfig } from '../../../types/index.js';

interface Harness {
  disk: unknown;
  server: unknown;
  serverVersion: number;
  pushed: unknown[];
  conflictsLeft: number;
}

const h = vi.hoisted(
  (): Harness => ({
    disk: undefined,
    server: undefined,
    serverVersion: 7,
    pushed: [],
    conflictsLeft: 0,
  })
);

const clone = <T>(v: T): T => structuredClone(v);

vi.mock('../../../adapters/config-file-storage.js', () => ({
  configFileStorage: {
    exists: () => Promise.resolve(true),
    load: () => Promise.resolve(clone(h.disk)),
    loadDecrypted: () => Promise.resolve(clone(h.disk)),
    getOrCreateDefault: () => Promise.resolve(clone(h.disk)),
    setRemoteStateWriter: () => undefined,
    updateCache: (_name: string, updater: (c: RdcConfig) => RdcConfig) => {
      h.disk = clone(updater(clone(h.disk) as RdcConfig));
      return Promise.resolve(clone(h.disk));
    },
  },
}));

vi.mock('../../../adapters/remote-token-storage.js', () => ({ remoteTokenStorage: {} }));
vi.mock('../../../utils/secure-storage.js', () => ({ getSecureStorage: () => ({}) }));

vi.mock('../../../adapters/remote-config-adapter.js', async (importOriginal) => {
  const real = await importOriginal<typeof import('../../../adapters/remote-config-adapter.js')>();
  class FakeAdapter {
    pull() {
      return Promise.resolve({
        config: clone(h.server) as RdcConfig,
        version: h.serverVersion,
        sdkEpoch: 1,
      });
    }
    push(doc: RdcConfig, current: number) {
      if (h.conflictsLeft > 0) {
        h.conflictsLeft -= 1;
        h.serverVersion += 1;
        return Promise.reject(new real.RemoteVersionConflictError('version conflict'));
      }
      h.pushed.push(clone(doc));
      h.serverVersion = current + 1;
      return Promise.resolve({ version: h.serverVersion });
    }
  }
  return { ...real, RemoteConfigAdapter: FakeAdapter };
});

import { ConfigServiceBase } from '../config-base.js';
import { overlayDeviceLocal } from '../remote-cache.js';

const REMOTE = {
  apiUrl: 'https://account.example.com',
  storeId: '11111111-1111-4111-8111-111111111111',
  configId: '22222222-2222-4222-8222-222222222222',
  storageKeyId: 'rdc:pk:key-1',
  cachedVersion: 7,
  cachedAt: '2026-09-25T00:00:00.000Z',
};

const FAMILY = { grand: 'latest', tags: { latest: { repositoryGuid: 'guid-shop' } } };

/** The on-disk cache of a remote-enabled config, carrying every host-local section. */
function localDisk(): Record<string, unknown> {
  return {
    schemaVersion: 3,
    id: 'cfg-id',
    version: 12,
    remote: REMOTE,
    encryption: { mode: 'plaintext' },
    renetPath: '/opt/dev/renet',
    credentials: { ssh: { privateKey: 'OLD' }, masterPasswordVerifier: 'mpv-hash' },
    state: {
      repos: { shop: { latest: { networkId: 2816, registryPort: 5001 } } },
      networkIds: { next: 2880 },
    },
    resources: {
      machines: { m1: { ip: '10.0.0.1', user: 'root' } },
      repositories: { shop: FAMILY },
    },
    futureKey: { fromANewerCli: true },
  };
}

/** What a pull hands back: fullConfigToRdcConfig's shape, host-local sections absent. */
function serverDoc(): Record<string, unknown> {
  return {
    schemaVersion: 3,
    id: 'cfg-id',
    version: 7,
    encryption: { mode: 'plaintext' },
    credentials: { ssh: { privateKey: 'PRIV' } },
    resources: {
      machines: { m1: { ip: '10.0.0.1', user: 'root' } },
      repositories: { shop: FAMILY },
    },
  };
}

type Disk = RdcConfig & { futureKey?: unknown };
const disk = () => h.disk as Disk;

async function pullThenWriteAMachine(): Promise<void> {
  const svc = new ConfigServiceBase();
  svc.setRuntimeConfig('cfg');
  const state = await svc.getResourceState();
  expect(state.getRepositories()['shop:latest'].networkId).toBe(2816);
  await state.setMachines({ ...state.getMachines(), m2: { ip: '10.0.0.2', user: 'root' } });
}

beforeEach(() => {
  h.disk = localDisk();
  h.server = serverDoc();
  h.serverVersion = 7;
  h.pushed = [];
  h.conflictsLeft = 0;
});

describe('device-local pointers and state across pull + write', () => {
  it('keeps every repo networkId and the networkIds counter, and publishes them (F3, T17)', async () => {
    await pullThenWriteAMachine();
    expect(h.pushed).toHaveLength(1);
    // The server copy had no state (pushed before state synced): the local state is kept and pushed.
    expect(h.pushed[0]).toHaveProperty('state.networkIds.next', 2880);
    expect(h.pushed[0]).toHaveProperty(['state', 'repos', 'shop', 'latest', 'networkId'], 2816);
    expect(disk().resources?.machines).toHaveProperty('m2');
    expect(disk().state?.repos?.shop.latest).toEqual({ networkId: 2816, registryPort: 5001 });
    expect(disk().state?.networkIds).toEqual({ next: 2880 });
  });

  it('keeps networkIds through a 409 rebase on a bucket other than repositories (F3)', async () => {
    h.conflictsLeft = 1;
    await pullThenWriteAMachine();
    expect(h.pushed).toHaveLength(1);
    expect(disk().state?.repos?.shop.latest.networkId).toBe(2816);
  });

  it('keeps credentials.masterPasswordVerifier while ssh comes from the server (F4)', async () => {
    await pullThenWriteAMachine();
    expect(disk().credentials?.masterPasswordVerifier).toBe('mpv-hash');
    expect(disk().credentials?.ssh?.privateKey).toBe('PRIV');
  });

  it('keeps an unknown top-level key from a newer CLI (F18)', async () => {
    await pullThenWriteAMachine();
    expect(disk().futureKey).toEqual({ fromANewerCli: true });
  });

  it('keeps renetPath (bd0278084)', async () => {
    await pullThenWriteAMachine();
    expect(disk().renetPath).toBe('/opt/dev/renet');
  });

  it('serves in memory exactly what the cache holds, state included', async () => {
    const svc = new ConfigServiceBase();
    svc.setRuntimeConfig('cfg');
    const current = await svc.getCurrent();
    expect(current).toEqual(disk());
    expect(current?.state?.networkIds?.next).toBe(2880);
  });
});

describe('overlayDeviceLocal', () => {
  const local = localDisk() as RdcConfig;

  it('lets a pulled document that carries the same unknown key win', () => {
    const pulled = { ...serverDoc(), futureKey: 'server' } as unknown as RdcConfig;
    expect((overlayDeviceLocal(pulled, local) as Disk).futureKey).toBe('server');
  });

  it('takes device-local absence from local too (the pull never decides a device-local pointer)', () => {
    const bare = { ...localDisk(), renetPath: undefined } as unknown as RdcConfig;
    const pulled = { ...serverDoc(), renetPath: '/server/renet' };
    expect(overlayDeviceLocal(pulled as unknown as RdcConfig, bare)).not.toHaveProperty(
      'renetPath'
    );
  });

  it('takes the pulled state (T17: state syncs)', () => {
    const bare = { ...localDisk(), state: undefined } as unknown as RdcConfig;
    const pulled = { ...serverDoc(), state: { reconciledAt: 'x' } } as unknown as RdcConfig;
    expect(overlayDeviceLocal(pulled, bare).state).toEqual({ reconciledAt: 'x' });
  });

  it('keeps the local state whole when the pulled copy has none (one-time migration)', () => {
    const pulled = serverDoc() as unknown as RdcConfig;
    expect(overlayDeviceLocal(pulled, local).state).toEqual(local.state);
  });

  it('merges repos per repo and tag: pulled wins where both have one, each side keeps its own', () => {
    const pulled = {
      ...serverDoc(),
      state: {
        networkIds: { next: 4000 },
        repos: { shop: { latest: { networkId: 3008 } }, blog: { latest: { networkId: 3072 } } },
      },
    } as unknown as RdcConfig;
    const mine = {
      ...localDisk(),
      state: {
        networkIds: { next: 2880 },
        repos: {
          shop: { latest: { networkId: 2816 }, dev: { networkId: 2944 } },
          legacy: { latest: { networkId: 2752 } },
        },
      },
    } as unknown as RdcConfig;
    expect(overlayDeviceLocal(pulled, mine).state).toEqual({
      networkIds: { next: 4000 },
      repos: {
        shop: { latest: { networkId: 3008 }, dev: { networkId: 2944 } },
        blog: { latest: { networkId: 3072 } },
        legacy: { latest: { networkId: 2752 } },
      },
    });
  });

  it('drops a verifier the pull carries when local has none, without creating credentials', () => {
    const noCreds = { ...localDisk(), credentials: undefined } as unknown as RdcConfig;
    const withVerifier = { ...serverDoc(), credentials: { masterPasswordVerifier: 'x' } };
    expect(overlayDeviceLocal(withVerifier as unknown as RdcConfig, noCreds).credentials).toEqual(
      {}
    );
    const noCredsPulled = { ...serverDoc(), credentials: undefined } as unknown as RdcConfig;
    expect(overlayDeviceLocal(noCredsPulled, noCreds)).not.toHaveProperty(
      'credentials.masterPasswordVerifier'
    );
  });

  it('mutates neither input', () => {
    const pulled = serverDoc() as unknown as RdcConfig;
    const before = clone(pulled);
    const localBefore = clone(local);
    overlayDeviceLocal(pulled, local);
    expect(pulled).toEqual(before);
    expect(local).toEqual(localBefore);
  });
});
