/**
 * Seed-on-enable (`finalizeEnable` / `applyHandoff`).
 *
 * The five contract cases: fresh store seeds at version 0→1 with a
 * whole local doc (the push projection leaves the device-local pointers home); a missing handoff configId is minted from the local
 * config's id; a differing existing store aborts without --force on a non-TTY
 * (credentials cleaned up); --force replaces local content with the server
 * copy; any non-404 pull error aborts with the local file untouched.
 *
 * A pull 404 seeds only when the store lists no config this token can see: on bench
 * (2026-10-28) a handoff that named no config met a store already holding an org-wide
 * one, and the old 404-means-empty rule seeded a second config beside it.
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
    listConfigs: vi.fn(),
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
      list: vi.fn(() => Promise.resolve([] as string[])),
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
  // Keep the real error classes (finalizeEnable/instanceof checks) but stub the adapter itself.
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
import { outputService } from '../../services/core/output.js';
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
    handoffNonce: 'nonce-1',
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
    mockAdapterInstance.listConfigs.mockResolvedValue([]);
  });

  it('seeds a fresh store: 404 → push v0 (state included) → pull-back proof → cache written', async () => {
    mockAdapterInstance.pull
      .mockRejectedValueOnce(new ConfigServerError('Config not found', 404))
      .mockResolvedValueOnce({ config: structuredClone(serverConfig), version: 1, sdkEpoch: 1 });
    mockAdapterInstance.push.mockResolvedValue({ version: 1 });

    await finalizeEnable(pendingRemote(CONFIG_ID), CONFIG_NAME);

    // Seed push: currentVersion=0, the local document with its state (T17: state syncs, so the store starts with this device's network IDs). The projection drops the device-local pointers.
    expect(mockAdapterInstance.push).toHaveBeenCalledTimes(1);
    const [seedDoc, currentVersion] = mockAdapterInstance.push.mock.calls[0] as [RdcConfig, number];
    expect(currentVersion).toBe(0);
    expect(seedDoc.state).toEqual(localConfig.state);
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

  it('keeps a slot secret that existed before the failed enable (F17: another local config uses it)', async () => {
    secureMem.set('rdc:pk:handoff-key', 'c2VjcmV0');
    mockAdapterInstance.pull.mockRejectedValue(new ConfigServerError('Forbidden', 403));

    await expect(applyHandoff(handoffPayload(CONFIG_ID), CONFIG_NAME, {})).rejects.toThrow(
      'Forbidden'
    );

    expect(secureMem.get('rdc:pk:handoff-key')).toBe('c2VjcmV0');
    expect(tokenMem.size).toBe(0);
  });

  it('keeps a slot secret another local config names, even when this enable wrote it', async () => {
    mockConfigFileStorage.list.mockResolvedValueOnce(['other', CONFIG_NAME]);
    mockConfigFileStorage.load.mockResolvedValueOnce({
      remote: { storageKeyId: 'rdc:pk:handoff-key' },
    });
    mockAdapterInstance.pull.mockRejectedValue(new ConfigServerError('Forbidden', 403));

    await expect(applyHandoff(handoffPayload(CONFIG_ID), CONFIG_NAME, {})).rejects.toThrow(
      'Forbidden'
    );

    expect(secureMem.has('rdc:pk:handoff-key')).toBe(true);
  });

  it('asks before replacing local content outside resources (F17b: ssh credentials and policy)', async () => {
    mockConfigFileStorage.loadDecrypted.mockResolvedValue({
      schemaVersion: 3,
      id: LOCAL_ID,
      version: 4,
      encryption: { mode: 'plaintext' },
      credentials: { ssh: { privateKey: 'LOCAL-KEY' } },
      policy: { version: 1 },
    });
    mockAdapterInstance.pull.mockResolvedValue({
      config: structuredClone(serverConfig),
      version: 3,
      sdkEpoch: 1,
    });

    await expect(finalizeEnable(pendingRemote(CONFIG_ID), CONFIG_NAME)).rejects.toThrow(/--force/);
    expect(mockConfigFileStorage.save).not.toHaveBeenCalled();
  });

  it('does not ask when the local content already equals the store copy, whatever the key order', async () => {
    mockConfigFileStorage.loadDecrypted.mockResolvedValue({
      schemaVersion: 3,
      id: LOCAL_ID,
      version: 4,
      encryption: { mode: 'plaintext' },
      resources: { machines: { srv: { user: 'deploy', ip: '10.0.0.9' } } },
    });
    mockAdapterInstance.pull.mockResolvedValue({
      config: structuredClone(serverConfig),
      version: 3,
      sdkEpoch: 1,
    });

    await finalizeEnable(pendingRemote(CONFIG_ID), CONFIG_NAME);
    expect(mockConfigFileStorage.save).toHaveBeenCalledTimes(1);
  });
});

describe('finalizeEnable --config-id (attach to an existing store entry)', () => {
  const ATTACH_ID = '33333333-3333-4333-8333-333333333333';
  const TEAM_ID = '44444444-4444-4444-8444-444444444444';

  beforeEach(() => {
    vi.clearAllMocks();
    adapterCtorArgs.length = 0;
    secureMem.clear();
    tokenMem.clear();
    mockConfigFileStorage.loadDecrypted.mockResolvedValue(structuredClone(localConfig));
    mockConfigFileStorage.save.mockResolvedValue(undefined);
    mockConfigFileStorage.getConfigPath.mockReturnValue(`/tmp/${CONFIG_NAME}.json`);
  });

  it('sets the local id and remote.configId to the named entry and pulls its copy', async () => {
    mockAdapterInstance.listConfigs.mockResolvedValue([
      { configId: CONFIG_ID, version: 2, lastModified: 'x' },
      { configId: ATTACH_ID, version: 114, lastModified: 'y', teamId: TEAM_ID },
    ]);
    mockAdapterInstance.pull.mockResolvedValue({
      config: { ...structuredClone(serverConfig), id: ATTACH_ID },
      version: 114,
      sdkEpoch: 1,
    });

    await finalizeEnable(pendingRemote(undefined), CONFIG_NAME, {
      force: true,
      configId: ATTACH_ID,
    });

    expect(mockAdapterInstance.push).not.toHaveBeenCalled();
    // The pull ran against a pointer that names the attached entry and its team.
    const lastCtor = adapterCtorArgs.at(-1)?.[0];
    expect(lastCtor).toMatchObject({ configId: ATTACH_ID, teamId: TEAM_ID });
    const saved = mockConfigFileStorage.save.mock.calls[0][0] as RdcConfig;
    expect(saved.id).toBe(ATTACH_ID);
    expect(saved.remote).toMatchObject({ configId: ATTACH_ID, cachedVersion: 114 });
  });

  it('refuses an id the store does not list, naming the available ones, and writes nothing', async () => {
    mockAdapterInstance.listConfigs.mockResolvedValue([
      { configId: CONFIG_ID, version: 2, lastModified: 'x' },
    ]);

    await expect(
      finalizeEnable(pendingRemote(undefined), CONFIG_NAME, { configId: ATTACH_ID })
    ).rejects.toThrow(new RegExp(`${ATTACH_ID}[\\s\\S]*Available: ${CONFIG_ID}`));

    expect(mockAdapterInstance.pull).not.toHaveBeenCalled();
    expect(mockAdapterInstance.push).not.toHaveBeenCalled();
    expect(mockConfigFileStorage.save).not.toHaveBeenCalled();
  });

  it('drops the handoff pointer team when the attached entry has none', async () => {
    mockAdapterInstance.listConfigs.mockResolvedValue([
      { configId: ATTACH_ID, version: 3, lastModified: 'y' },
    ]);
    mockAdapterInstance.pull.mockResolvedValue({
      config: { ...structuredClone(serverConfig), id: ATTACH_ID },
      version: 3,
      sdkEpoch: 1,
    });

    await finalizeEnable({ ...pendingRemote(undefined), teamId: TEAM_ID }, CONFIG_NAME, {
      force: true,
      configId: ATTACH_ID,
    });

    const lastCtor = adapterCtorArgs.at(-1)?.[0] as Record<string, unknown>;
    expect(lastCtor.configId).toBe(ATTACH_ID);
    expect(lastCtor).not.toHaveProperty('teamId');
    const saved = mockConfigFileStorage.save.mock.calls[0][0] as RdcConfig;
    expect(saved.remote).not.toHaveProperty('teamId');
  });

  it('refuses an interactive enable whose list failed, instead of minting a new entry', async () => {
    const tty = Object.getOwnPropertyDescriptor(process.stdin, 'isTTY');
    const yes = process.env.REDIACC_YES;
    Object.defineProperty(process.stdin, 'isTTY', { value: true, configurable: true });
    delete process.env.REDIACC_YES;
    mockAdapterInstance.listConfigs.mockRejectedValue(new Error('list boom'));
    try {
      await expect(finalizeEnable(pendingRemote(undefined), CONFIG_NAME)).rejects.toThrow(
        /list boom/
      );
    } finally {
      if (tty) Object.defineProperty(process.stdin, 'isTTY', tty);
      else delete (process.stdin as { isTTY?: boolean }).isTTY;
      if (yes !== undefined) process.env.REDIACC_YES = yes;
    }
    expect(mockAdapterInstance.pull).not.toHaveBeenCalled();
    expect(mockAdapterInstance.push).not.toHaveBeenCalled();
    expect(mockConfigFileStorage.save).not.toHaveBeenCalled();
  });

  it('with --config-id given, a failed list is the error itself, not advice to pass --config-id', async () => {
    mockAdapterInstance.listConfigs.mockRejectedValue(new Error('list boom'));
    const err = await finalizeEnable(pendingRemote(undefined), CONFIG_NAME, {
      configId: ATTACH_ID,
    }).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(Error);
    expect((err as Error).message).toBe('list boom');
    expect(mockAdapterInstance.pull).not.toHaveBeenCalled();
    expect(mockConfigFileStorage.save).not.toHaveBeenCalled();
  });

  it('never seeds a new entry when the attached entry pulls 404', async () => {
    mockAdapterInstance.listConfigs.mockResolvedValue([
      { configId: ATTACH_ID, version: 1, lastModified: 'y' },
    ]);
    mockAdapterInstance.pull.mockRejectedValue(new ConfigServerError('Config not found', 404));

    await expect(
      finalizeEnable(pendingRemote(undefined), CONFIG_NAME, { configId: ATTACH_ID })
    ).rejects.toThrow('Config not found');
    expect(mockAdapterInstance.push).not.toHaveBeenCalled();
  });

  it('without --config-id on a non-TTY, an empty store list keeps the minted-id seed (once)', async () => {
    mockAdapterInstance.listConfigs.mockResolvedValue([]);
    mockAdapterInstance.pull
      .mockRejectedValueOnce(new ConfigServerError('Config not found', 404))
      .mockResolvedValueOnce({ config: structuredClone(serverConfig), version: 1, sdkEpoch: 1 });
    mockAdapterInstance.push.mockResolvedValue({ version: 1 });

    await finalizeEnable(pendingRemote(undefined), CONFIG_NAME);

    // The 404 alone does not prove an empty store: the list is read, and only an empty one seeds.
    expect(mockAdapterInstance.listConfigs).toHaveBeenCalledTimes(1);
    expect(mockAdapterInstance.push).toHaveBeenCalledTimes(1);
    expect(mockAdapterInstance.push.mock.calls[0]?.[1]).toBe(0);
    expect(adapterCtorArgs[0]?.[0]).toMatchObject({ configId: LOCAL_ID });
  });

  it('says on stderr that it seeded an empty store, and says nothing of the kind when it attaches', async () => {
    const success = vi.spyOn(outputService, 'success').mockImplementation(() => undefined);
    const stdout = vi.spyOn(process.stdout, 'write').mockImplementation(() => true);
    try {
      mockAdapterInstance.pull
        .mockRejectedValueOnce(new ConfigServerError('Config not found', 404))
        .mockResolvedValueOnce({ config: structuredClone(serverConfig), version: 1, sdkEpoch: 1 });
      mockAdapterInstance.push.mockResolvedValue({ version: 1 });
      await finalizeEnable(pendingRemote(undefined), CONFIG_NAME);
      expect(success).toHaveBeenCalledWith(
        'Store was empty; pushed the local config as version 1.'
      );
      expect(stdout).not.toHaveBeenCalled();

      // A store that already holds one config is attached to, never seeded: no seeded line.
      success.mockClear();
      mockAdapterInstance.push.mockClear();
      mockAdapterInstance.listConfigs.mockResolvedValue([
        { configId: CONFIG_ID, version: 1, lastModified: 'z', teamId: null },
      ]);
      mockAdapterInstance.pull
        .mockRejectedValueOnce(new ConfigServerError('Config not found', 404))
        .mockResolvedValueOnce({ config: structuredClone(serverConfig), version: 1, sdkEpoch: 1 });
      await finalizeEnable(pendingRemote(undefined), CONFIG_NAME, { force: true });
      expect(mockAdapterInstance.push).not.toHaveBeenCalled();
      expect(success).not.toHaveBeenCalled();
    } finally {
      success.mockRestore();
      stdout.mockRestore();
    }
  });
});

describe('finalizeEnable never seeds a second config beside an existing one', () => {
  const EXISTING_ID = '3df57118-0000-4000-8000-000000000001';
  const OTHER_ID = '3df57118-0000-4000-8000-000000000002';
  const TEAM_ID = '44444444-4444-4444-8444-444444444444';

  beforeEach(() => {
    vi.clearAllMocks();
    adapterCtorArgs.length = 0;
    secureMem.clear();
    tokenMem.clear();
    delete process.env.REDIACC_YES;
    mockConfigFileStorage.loadDecrypted.mockResolvedValue(structuredClone(localConfig));
    mockConfigFileStorage.save.mockResolvedValue(undefined);
    mockConfigFileStorage.getConfigPath.mockReturnValue(`/tmp/${CONFIG_NAME}.json`);
    mockAdapterInstance.push.mockResolvedValue({ version: 1 });
  });

  it('attaches to the one org-wide config the handoff did not name (bench 2026-10-28), zero pushes', async () => {
    // The handoff named no config (the enroll could not see the org-wide one), so the minted id 404s; the list shows it.
    mockAdapterInstance.listConfigs.mockResolvedValue([
      { configId: EXISTING_ID, version: 7, lastModified: 'z', teamId: null },
    ]);
    mockAdapterInstance.pull
      .mockRejectedValueOnce(new ConfigServerError('Config not found', 404))
      .mockResolvedValueOnce({
        config: { ...structuredClone(serverConfig), id: EXISTING_ID },
        version: 7,
        sdkEpoch: 1,
      });

    await finalizeEnable({ ...pendingRemote(undefined), teamId: TEAM_ID }, CONFIG_NAME, {
      force: true,
    });

    expect(mockAdapterInstance.push).not.toHaveBeenCalled();
    // The second pull addressed the existing org-wide entry, without the handoff's team.
    const lastCtor = adapterCtorArgs.at(-1)?.[0] as Record<string, unknown>;
    expect(lastCtor.configId).toBe(EXISTING_ID);
    expect(lastCtor).not.toHaveProperty('teamId');
    const saved = mockConfigFileStorage.save.mock.calls[0][0] as RdcConfig;
    expect(saved.id).toBe(EXISTING_ID);
    expect(saved.remote).toMatchObject({ configId: EXISTING_ID, cachedVersion: 7 });
  });

  it('still guards differing local content after attaching: non-TTY without --force aborts, zero pushes', async () => {
    mockAdapterInstance.listConfigs.mockResolvedValue([
      { configId: EXISTING_ID, version: 7, lastModified: 'z', teamId: null },
    ]);
    mockAdapterInstance.pull
      .mockRejectedValueOnce(new ConfigServerError('Config not found', 404))
      .mockResolvedValueOnce({
        config: { ...structuredClone(serverConfig), id: EXISTING_ID },
        version: 7,
        sdkEpoch: 1,
      });

    await expect(applyHandoff(handoffPayload(undefined), CONFIG_NAME, {})).rejects.toThrow(
      /--force/
    );
    expect(mockAdapterInstance.push).not.toHaveBeenCalled();
    expect(mockConfigFileStorage.save).not.toHaveBeenCalled();
    expect(tokenMem.size).toBe(0);
  });

  it('refuses when several configs are visible and none was named, listing them, zero pushes', async () => {
    mockAdapterInstance.listConfigs.mockResolvedValue([
      { configId: EXISTING_ID, version: 7, lastModified: 'z', teamId: null },
      { configId: OTHER_ID, version: 2, lastModified: 'y', teamId: TEAM_ID },
    ]);
    mockAdapterInstance.pull.mockRejectedValue(new ConfigServerError('Config not found', 404));

    await expect(applyHandoff(handoffPayload(undefined), CONFIG_NAME, {})).rejects.toThrow(
      new RegExp(`Available: ${EXISTING_ID}, ${OTHER_ID}`)
    );
    expect(mockAdapterInstance.push).not.toHaveBeenCalled();
    expect(mockConfigFileStorage.save).not.toHaveBeenCalled();
    expect(tokenMem.size).toBe(0);
  });

  it('refuses when the handoff named a config that 404s while the store holds another, zero pushes', async () => {
    mockAdapterInstance.listConfigs.mockResolvedValue([
      { configId: EXISTING_ID, version: 7, lastModified: 'z', teamId: null },
    ]);
    mockAdapterInstance.pull.mockRejectedValue(new ConfigServerError('Config not found', 404));

    await expect(finalizeEnable(pendingRemote(CONFIG_ID), CONFIG_NAME)).rejects.toThrow(
      new RegExp(`${CONFIG_ID}[\\s\\S]*Available: ${EXISTING_ID}`)
    );
    expect(mockAdapterInstance.push).not.toHaveBeenCalled();
    expect(mockConfigFileStorage.save).not.toHaveBeenCalled();
  });

  it('refuses to seed when the store list cannot be read after the 404, zero pushes', async () => {
    mockAdapterInstance.listConfigs.mockRejectedValue(new Error('list boom'));
    mockAdapterInstance.pull.mockRejectedValue(new ConfigServerError('Config not found', 404));

    await expect(finalizeEnable(pendingRemote(undefined), CONFIG_NAME)).rejects.toThrow(
      /list boom[\s\S]*duplicate/
    );
    expect(mockAdapterInstance.push).not.toHaveBeenCalled();
    expect(mockConfigFileStorage.save).not.toHaveBeenCalled();
  });
});
