import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mockReadAccountPointer = vi.hoisted(() => vi.fn((): Record<string, unknown> => ({})));
const mockConfigUpdate = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));

vi.mock('../account/subscription-auth.js', () => ({
  normalizeServerUrl: (url: string) => url.replace(/\/+$/, ''),
  getSubscriptionServerUrl: vi.fn().mockReturnValue(WK_ACCOUNT_DEFAULT_ORIGIN),
  getSubscriptionTokenState: vi.fn().mockReturnValue({ kind: 'missing' }),
}));

vi.mock('../account/account-pointer.js', () => ({
  readAccountPointer: mockReadAccountPointer,
}));

vi.mock('../../adapters/config-file-storage.js', () => ({
  configFileStorage: { update: mockConfigUpdate },
}));

vi.mock('../config/config-name.js', () => ({
  getEffectiveConfigName: vi.fn().mockReturnValue('rediacc'),
}));

vi.mock('../update/updater.js', () => ({
  resolveChannel: vi.fn().mockReturnValue('stable'),
}));

vi.mock('../../version.js', () => ({
  VERSION: '0.9.0',
}));

// The imported key stands in as its own SPKI, so a test can tell which key a call resolved to.
vi.mock('@rediacc/shared/e2e', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@rediacc/shared/e2e')>()),
  importX25519PublicKey: (publicKeySpki: string) => Promise.resolve({ publicKeySpki }),
}));

import { WK_ACCOUNT_DEFAULT_ORIGIN } from '@rediacc/shared/config/well-known.generated';
import { BAKED_IN_REGIONS, type RegionInfo } from '@rediacc/shared/regions';
import {
  fetchServerInfo,
  getServerKeyMaterial,
  ServerE2eKeyUnavailableError,
} from '../account/account-client.js';

const regionOf = (id: string): RegionInfo => {
  const r = BAKED_IN_REGIONS.find((x) => x.id === id);
  if (!r) throw new Error(`no baked-in region ${id}`);
  return r;
};

describe('fetchServerInfo', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.resetAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('constructs correct URL from server URL', async () => {
    const mockResponse = {
      e2e: { keys: [{ keyId: 'v1', publicKeySpki: 'testkey' }] },
      apiVersion: 1,
      minCliVersion: '0.8.0',
      warnCliVersion: null,
      environment: 'edge',
      updateChannel: 'edge',
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockResponse),
    });

    await fetchServerInfo(`https://${regionOf('eu').edgeDomain}`);

    expect(globalThis.fetch).toHaveBeenCalledWith(
      `https://${regionOf('eu').edgeDomain}/account/api/v1/.well-known/server-info`,
      expect.objectContaining({
        headers: expect.objectContaining({ 'User-Agent': expect.stringContaining('rdc/') }),
      })
    );
  });

  it('strips trailing slash from server URL', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          e2e: { keys: [] },
          apiVersion: 1,
          minCliVersion: '0.0.0',
          warnCliVersion: null,
          environment: 'production',
          updateChannel: 'stable',
        }),
    });

    await fetchServerInfo(`${WK_ACCOUNT_DEFAULT_ORIGIN}/`);

    expect(globalThis.fetch).toHaveBeenCalledWith(
      `${WK_ACCOUNT_DEFAULT_ORIGIN}/account/api/v1/.well-known/server-info`,
      expect.anything()
    );
  });

  it('returns parsed server info with updateChannel', async () => {
    const mockResponse = {
      e2e: { keys: [{ keyId: 'v1', publicKeySpki: 'testkey' }] },
      apiVersion: 1,
      minCliVersion: '0.9.0',
      warnCliVersion: '0.8.5',
      environment: 'edge',
      updateChannel: 'edge',
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockResponse),
    });

    const info = await fetchServerInfo(`https://${regionOf('eu').edgeDomain}`);
    expect(info.environment).toBe('edge');
    expect(info.updateChannel).toBe('edge');
    expect(info.minCliVersion).toBe('0.9.0');
    expect(info.e2e.keys).toHaveLength(1);
  });

  it('returns stable updateChannel for production', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          e2e: { keys: [] },
          apiVersion: 1,
          minCliVersion: '0.0.0',
          warnCliVersion: null,
          environment: 'production',
          updateChannel: 'stable',
        }),
    });

    const info = await fetchServerInfo(WK_ACCOUNT_DEFAULT_ORIGIN);
    expect(info.environment).toBe('production');
    expect(info.updateChannel).toBe('stable');
  });

  it('throws on non-OK response', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
    });

    await expect(fetchServerInfo(WK_ACCOUNT_DEFAULT_ORIGIN)).rejects.toThrow(
      'server-info returned 500'
    );
  });

  it('throws on network error', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('Network error'));

    await expect(fetchServerInfo(WK_ACCOUNT_DEFAULT_ORIGIN)).rejects.toThrow('Network error');
  });
});

describe('getServerKeyMaterial tiers', () => {
  // A real, valid X25519 SPKI (the hardcoded production key), reused so importX25519PublicKey does not reject.
  const VALID_SPKI = 'MCowBQYDK2VuAyEALY64atDar/bIwKoYEJPoYphKKZ6KUIkPzIHdfH6nKg8=';
  const originalFetch = globalThis.fetch;
  let urlCounter = 0;
  /** A distinct non-production server per test: discovered keys are remembered per URL for the process. */
  const devServer = () => `http://gateway-${++urlCounter}.test:4800`;

  let keyCounter = 0;
  const freshSpki = () => `SPKI-${++keyCounter}`;
  const spkiOf = (key: unknown) => (key as { publicKeySpki: string }).publicKeySpki;

  function serverInfoResponse(publicKeySpki: string, keyId = 'v1'): Response {
    return new Response(JSON.stringify({ e2e: { keys: [{ keyId, publicKeySpki }] } }), {
      status: 200,
    });
  }

  beforeEach(() => {
    mockConfigUpdate.mockReset();
    mockConfigUpdate.mockResolvedValue(undefined);
  });

  afterEach(() => {
    delete process.env.X25519_PUBLIC_KEY;
    globalThis.fetch = originalFetch;
    mockReadAccountPointer.mockReset();
    mockReadAccountPointer.mockReturnValue({});
  });

  it('uses the config account.e2ePublicKey (keyId "config") for the config\'s own server; the deleted X25519_PUBLIC_KEY env gate no longer applies', async () => {
    // The old dev gate would have honored this env var; it must now be ignored.
    process.env.X25519_PUBLIC_KEY = 'unused-env-key';
    const server = devServer();
    mockReadAccountPointer.mockReturnValue({
      accountServer: `${server}/`,
      e2ePublicKey: VALID_SPKI,
    });
    globalThis.fetch = vi.fn() as typeof fetch;

    const material = await getServerKeyMaterial(server);
    expect(material.keyId).toBe('config');
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('ignores a saved key that belongs to another server and discovers the key of the server the request goes to', async () => {
    const server = devServer();
    const devKey = freshSpki();
    mockReadAccountPointer.mockReturnValue({
      accountServer: WK_ACCOUNT_DEFAULT_ORIGIN,
      e2ePublicKey: VALID_SPKI,
    });
    const fetchMock = vi.fn().mockResolvedValue(serverInfoResponse(devKey, 'dev'));
    globalThis.fetch = fetchMock as typeof fetch;

    const material = await getServerKeyMaterial(server);
    expect(material.keyId).toBe('dev');
    expect(spkiOf(material.key)).toBe(devKey);
    expect(fetchMock).toHaveBeenCalledWith(
      `${server}/account/api/v1/.well-known/server-info`,
      expect.anything()
    );
    // The config names another server, so the discovered key is not saved into it.
    expect(mockConfigUpdate).not.toHaveBeenCalled();
  });

  it('refuses with ServerE2eKeyUnavailableError, never the production key, when a non-production server has no saved key and cannot be asked', async () => {
    const server = devServer();
    mockReadAccountPointer.mockReturnValue({ accountServer: server });
    globalThis.fetch = vi.fn().mockRejectedValue(new TypeError('fetch failed')) as typeof fetch;

    const refusal = await getServerKeyMaterial(server).catch((error: unknown) => error);
    expect(refusal).toBeInstanceOf(ServerE2eKeyUnavailableError);
    expect((refusal as ServerE2eKeyUnavailableError).serverUrl).toBe(server);
    expect((refusal as Error).message).toContain(`No E2E key for account server ${server}`);
    expect((refusal as Error).message).toContain('fetch failed');
    // The network failure stays reachable through `cause`, so remote-config reads still classify it as unreachable.
    expect((refusal as Error).cause).toBeInstanceOf(TypeError);
  });

  it('falls back to the baked-in key for a production region whose server-info cannot be read', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new TypeError('fetch failed')) as typeof fetch;
    const material = await getServerKeyMaterial(`https://${regionOf('us').domain}`);
    expect(material.keyId).toBe('v1');
    expect(spkiOf(material.key)).toBe(VALID_SPKI);
  });

  it('reads the saved key on every call, so a key saved mid-process (subscription login) replaces the one an earlier call used', async () => {
    const server = devServer();
    const staleKey = freshSpki();
    const savedKey = freshSpki();
    mockReadAccountPointer.mockReturnValue({ accountServer: server, e2ePublicKey: staleKey });
    const first = await getServerKeyMaterial(server);
    mockReadAccountPointer.mockReturnValue({ accountServer: server, e2ePublicKey: savedKey });
    const second = await getServerKeyMaterial(server);

    expect(spkiOf(first.key)).toBe(staleKey);
    expect(spkiOf(second.key)).toBe(savedKey);
  });

  it('saves a discovered key only when the locked config still names that server and holds no key (the config init race)', async () => {
    const server = devServer();
    const discovered = freshSpki();
    // Outside the lock the config names the server and has no key yet ...
    mockReadAccountPointer.mockReturnValue({ accountServer: server });
    globalThis.fetch = vi.fn().mockResolvedValue(serverInfoResponse(discovered)) as typeof fetch;

    await getServerKeyMaterial(server);
    expect(mockConfigUpdate).toHaveBeenCalledTimes(1);
    const edit = mockConfigUpdate.mock.calls[0][1] as (cfg: Record<string, unknown>) => {
      account?: Record<string, unknown>;
    };

    // ... but by the time the write holds the lock, `config init` has saved the server's own key: it stays.
    const initSaved = { account: { accountServer: server, e2ePublicKey: 'INIT-SAVED-KEY' } };
    expect(edit(initSaved).account?.e2ePublicKey).toBe('INIT-SAVED-KEY');
    // A config that now names another server does not take the key either.
    const otherServer = { account: { accountServer: 'http://elsewhere.test' } };
    expect(edit(otherServer).account?.e2ePublicKey).toBeUndefined();
    // Still the same server and still no key: the discovered key is saved.
    expect(edit({ account: { accountServer: server } }).account?.e2ePublicKey).toBe(discovered);
  });
});
