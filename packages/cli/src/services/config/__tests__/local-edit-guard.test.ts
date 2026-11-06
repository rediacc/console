/**
 * A local edit of a remote config's cache file is never overwritten silently (#5013fce6).
 *
 * The disk is an in-memory document behind a mocked configFileStorage and the server a fake adapter
 * keeping every version; everything between them is the real read path:
 * ConfigServiceBase.getCurrent -> loadRemote -> reconcileLocalEdits -> writeRemoteCache.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { RdcConfig } from '../../../types/index.js';

interface Harness {
  disk: unknown;
  versions: Map<number, unknown>;
  serverVersion: number;
  pushed: { doc: unknown; current: number; base: unknown }[];
  archiveError: Error | null;
  warnings: string[];
}

const h = vi.hoisted(
  (): Harness => ({
    disk: undefined,
    versions: new Map(),
    serverVersion: 7,
    pushed: [],
    archiveError: null,
    warnings: [],
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

vi.mock('../../core/output.js', () => ({
  outputService: {
    warn: (line: string) => h.warnings.push(line),
    info: () => undefined,
    success: () => undefined,
  },
}));

vi.mock('../../../adapters/remote-config-adapter.js', async (importOriginal) => {
  const real = await importOriginal<typeof import('../../../adapters/remote-config-adapter.js')>();
  class FakeAdapter {
    pull() {
      return Promise.resolve({
        config: clone(h.versions.get(h.serverVersion)) as RdcConfig,
        version: h.serverVersion,
        sdkEpoch: 1,
      });
    }
    pullVersion(version: number) {
      if (h.archiveError) return Promise.reject(h.archiveError);
      return Promise.resolve({
        config: clone(h.versions.get(version)) as RdcConfig,
        version,
        sdkEpoch: 1,
      });
    }
    push(doc: RdcConfig, current: number, options: { base?: RdcConfig }) {
      if (current !== h.serverVersion) {
        return Promise.reject(new real.RemoteVersionConflictError('version conflict'));
      }
      h.pushed.push({ doc: clone(doc), current, base: clone(options.base) });
      h.serverVersion = current + 1;
      h.versions.set(h.serverVersion, clone(doc));
      return Promise.resolve({ version: h.serverVersion });
    }
  }
  return { ...real, RemoteConfigAdapter: FakeAdapter };
});

import { ConfigServiceBase } from '../config-base.js';
import { localEditsAgainst, RemoteLocalEditConflictError } from '../local-edit-guard.js';

const REMOTE = {
  apiUrl: 'https://account.example.com',
  storeId: '11111111-1111-4111-8111-111111111111',
  configId: '22222222-2222-4222-8222-222222222222',
  storageKeyId: 'rdc:pk:key-1',
  cachedVersion: 7,
  cachedAt: '2026-11-06T10:00:00.000Z',
};

function family(guid: string) {
  return {
    grand: 'latest',
    placement: { machine: 'm1' },
    tags: { latest: { repositoryGuid: guid } },
  };
}

/** The server copy at version 7: three repos. */
function serverV7(): Record<string, unknown> {
  return {
    schemaVersion: 3,
    id: 'cfg-id',
    version: 7,
    encryption: { mode: 'plaintext' },
    resources: {
      machines: { m1: { ip: '10.0.0.1', user: 'root' } },
      repositories: {
        shop: family('guid-shop'),
        dead1: family('guid-d1'),
        dead2: family('guid-d2'),
      },
    },
  };
}

/** The cache of version 7, device-local pointers included. */
function cacheOfV7(): Record<string, unknown> {
  return { ...serverV7(), version: 12, remote: REMOTE, renetPath: '/opt/renet' };
}

/** The cache file after a hand edit removed the two dead repos. */
function editedCache(): Record<string, unknown> {
  const doc = cacheOfV7();
  const resources = doc.resources as { repositories: Record<string, unknown> };
  delete resources.repositories.dead1;
  delete resources.repositories.dead2;
  return doc;
}

type Disk = RdcConfig;
const disk = () => h.disk as Disk;

function read(): Promise<RdcConfig | null> {
  const svc = new ConfigServiceBase();
  svc.setRuntimeConfig('cfg');
  return svc.getCurrent();
}

beforeEach(() => {
  h.versions = new Map([[7, serverV7()]]);
  h.serverVersion = 7;
  h.pushed = [];
  h.archiveError = null;
  h.warnings = [];
});

describe('a local edit of the cache file is not overwritten by the next read', () => {
  it('pushes the edit as the next version when the server has not moved', async () => {
    h.disk = editedCache();
    const config = await read();

    expect(h.pushed).toHaveLength(1);
    expect(h.pushed[0].current).toBe(7);
    // The base is the server copy at 7, so the removal carries its tombstones.
    expect(h.pushed[0].base).toHaveProperty(['resources', 'repositories', 'dead1']);
    expect(Object.keys(config?.resources?.repositories ?? {})).toEqual(['shop']);
    expect(Object.keys(disk().resources?.repositories ?? {})).toEqual(['shop']);
    expect(disk().remote?.cachedVersion).toBe(8);
    // Device-local pointers stay with the file, never with the push.
    expect(disk().renetPath).toBe('/opt/renet');
    expect(h.warnings).toEqual([
      'Config "cfg": the local file held edits made since server version 7; pushed them as version 8: /resources/repositories/dead1, /resources/repositories/dead2',
    ]);
  });

  it('refuses, naming both versions, when the server moved on as well', async () => {
    h.versions.set(8, { ...serverV7(), defaults: { language: 'de' } });
    h.serverVersion = 8;
    h.disk = editedCache();

    const failure = await read().catch((error: unknown) => error);

    expect(failure).toBeInstanceOf(RemoteLocalEditConflictError);
    expect(failure).toMatchObject({ cachedVersion: 7, serverVersion: 8 });
    expect((failure as RemoteLocalEditConflictError).changes).toContain(
      '/resources/repositories/dead1'
    );
    expect(h.pushed).toHaveLength(0);
    // Nothing was overwritten.
    expect(disk()).toEqual(editedCache());
  });

  it('refuses when the cached version cannot be read back to tell an edit from a server change', async () => {
    h.versions.set(8, { ...serverV7(), defaults: { language: 'de' } });
    h.serverVersion = 8;
    h.archiveError = new Error('version 7 was pruned');
    h.disk = editedCache();

    await expect(read()).rejects.toBeInstanceOf(RemoteLocalEditConflictError);
    expect(h.pushed).toHaveLength(0);
    expect(disk()).toEqual(editedCache());
  });

  it('takes the server copy when the file is only behind, not edited', async () => {
    h.versions.set(8, { ...serverV7(), defaults: { language: 'de' } });
    h.serverVersion = 8;
    h.disk = cacheOfV7();

    const config = await read();

    expect(h.pushed).toHaveLength(0);
    expect(config?.defaults?.language).toBe('de');
    expect(disk().remote?.cachedVersion).toBe(8);
    expect(h.warnings).toEqual([]);
  });

  it('pushes nothing and warns nothing when the file matches the server', async () => {
    h.disk = cacheOfV7();
    await read();
    expect(h.pushed).toHaveLength(0);
    expect(h.warnings).toEqual([]);
  });
});

describe('runtime state the cache merge resolves is not a local edit', () => {
  const serverState = {
    repos: { mail: { latest: { networkId: 3008 } } },
    networkIds: { next: 3072 },
  };

  beforeEach(() => {
    h.versions = new Map([[7, { ...serverV7(), state: serverState }]]);
  });

  it('pushes nothing for a state-only difference, and the pulled runtime wins', async () => {
    h.disk = {
      ...cacheOfV7(),
      state: {
        repos: { mail: { latest: { networkId: 9999 } }, legacy: { latest: { networkId: 4032 } } },
      },
    };

    const config = await read();

    expect(h.pushed).toHaveLength(0);
    expect(h.warnings).toEqual([]);
    expect(config?.state?.repos?.mail?.latest?.networkId).toBe(3008);
    expect(config?.state?.repos?.legacy?.latest?.networkId).toBe(4032);
  });

  it('still pushes a repos removal made beside a state difference, without the local state', async () => {
    h.disk = { ...editedCache(), state: { repos: { mail: { latest: { networkId: 9999 } } } } };

    await read();

    expect(h.pushed).toHaveLength(1);
    const pushed = h.pushed[0].doc as RdcConfig;
    expect(Object.keys(pushed.resources?.repositories ?? {})).toEqual(['shop']);
    expect(pushed.state?.repos?.mail?.latest?.networkId).toBe(3008);
    expect(h.warnings).toHaveLength(1);
    expect(h.warnings[0]).not.toContain('/state');
  });

  it('names no state pointer to config remote refresh', () => {
    const local = { ...cacheOfV7(), state: { repos: { mail: { latest: { networkId: 9999 } } } } };
    const pulled = { config: h.versions.get(7) as RdcConfig, version: 7, sdkEpoch: 1 };
    expect(localEditsAgainst(local as unknown as RdcConfig, pulled)).toBeNull();
  });
});

describe('config remote refresh names what it replaces', () => {
  const pulled = () => ({ config: serverV7() as unknown as RdcConfig, version: 7, sdkEpoch: 1 });

  it('names the pointers of a local edit', () => {
    expect(localEditsAgainst(editedCache() as unknown as RdcConfig, pulled())).toContain(
      '/resources/repositories/dead1'
    );
  });

  it('names nothing when the file matches, or was never cached', () => {
    expect(localEditsAgainst(cacheOfV7() as unknown as RdcConfig, pulled())).toBeNull();
    const bare = { ...editedCache(), remote: { ...REMOTE, cachedVersion: undefined } };
    expect(localEditsAgainst(bare as unknown as RdcConfig, pulled())).toBeNull();
  });
});
