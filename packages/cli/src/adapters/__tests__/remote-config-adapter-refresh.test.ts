/**
 * The adapter's config token renewal (PLAN-config-sync-hardening T11): a 401 whose reason a new
 * token cures is renewed once per operation with the login token, then the refused request is
 * sent again. The round trip against the real server is in
 * private/account/tests/integration/config-sync/tokens.test.ts; this pins the adapter's branches.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockConfigServerFetch, mockRefresh, mockLoginTokenFor } = vi.hoisted(() => ({
  mockConfigServerFetch: vi.fn(),
  mockRefresh: vi.fn(),
  mockLoginTokenFor: vi.fn(),
}));

vi.mock('../../services/config/config-server-client.js', () => ({
  configServerFetch: mockConfigServerFetch,
  ConfigServerError: class ConfigServerError extends Error {
    status: number;
    code?: string;
    constructor(message: string, status: number, code?: string) {
      super(message);
      this.name = 'ConfigServerError';
      this.status = status;
      this.code = code;
    }
  },
}));

vi.mock('../../services/config/device-token-refresh.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../services/config/device-token-refresh.js')>()),
  refreshDeviceToken: mockRefresh,
  loginTokenFor: mockLoginTokenFor,
}));

import { ConfigServerError } from '../../services/config/config-server-client.js';
import { RemoteTokenRefreshError } from '../../services/config/device-token-refresh.js';
import type { RemoteConfig } from '../../types/index.js';
import {
  RemoteAuthError,
  RemoteConfigAdapter,
  RemoteTeamForbiddenError,
  RemoteTokenIpMismatchError,
} from '../remote-config-adapter.js';
import type { RemoteTokenStorage, TokenLease } from '../remote-token-storage.js';

const REMOTE: RemoteConfig = {
  apiUrl: 'https://account.example.com',
  storeId: 'store-1',
  configId: 'config-1',
  teamId: 'team-1',
  storageKeyId: 'key-1',
};

/** A token file of one token and a wrapped CEK; `saved` records every token persisted. */
function tokenStorage() {
  const saved: string[] = [];
  let data = { token: 'rct_dead', wrappedCek: 'wrapped' };
  const storage = {
    saved,
    withLease: <T>(_name: string, fn: (lease: TokenLease) => Promise<T>) =>
      fn({
        get data() {
          return data;
        },
        get token() {
          return data.token;
        },
        sync: undefined,
        update: (token: string) => {
          data = { ...data, token };
          saved.push(token);
          return Promise.resolve();
        },
        recordSync: () => Promise.resolve(),
      }),
  };
  return storage;
}

function authRefusal(reason: string) {
  return new ConfigServerError(`Config auth failed: ${reason}`, 401, reason);
}

/** The config token each config server request sent, in order. */
function sentTokens(): string[] {
  return mockConfigServerFetch.mock.calls.map(
    (call) => (call[1] as { configToken: string }).configToken
  );
}

describe('RemoteConfigAdapter token renewal (T11)', () => {
  let storage: ReturnType<typeof tokenStorage>;
  let adapter: RemoteConfigAdapter;

  beforeEach(() => {
    vi.clearAllMocks();
    storage = tokenStorage();
    adapter = new RemoteConfigAdapter(REMOTE, 'cfg', storage as unknown as RemoteTokenStorage, {
      type: 'mock',
      get: vi.fn(),
      set: vi.fn(),
      delete: vi.fn(),
    });
    mockLoginTokenFor.mockReturnValue('rdt_login');
    mockRefresh.mockResolvedValue('rct_fresh');
  });

  it.each(['ip_mismatch', 'token_expired', 'token_exhausted', 'invalid_token'])(
    'renews on %s and sends the refused request again with the new token',
    async (reason) => {
      mockConfigServerFetch
        .mockRejectedValueOnce(authRefusal(reason))
        .mockResolvedValueOnce({ data: { versions: [] }, newServerToken: 'rct_rotated' });

      await expect(adapter.listVersions()).resolves.toEqual([]);
      expect(mockLoginTokenFor).toHaveBeenCalledWith('https://account.example.com');
      expect(mockRefresh).toHaveBeenCalledTimes(1);
      expect(mockRefresh).toHaveBeenCalledWith(REMOTE, 'rdt_login', {
        fetchImpl: undefined,
        serverKey: undefined,
      });
      expect(sentTokens()).toEqual(['rct_dead', 'rct_fresh']);
      expect(storage.saved).toEqual(['rct_fresh', 'rct_rotated']);
    }
  );

  it('never renews on decryption_failed', async () => {
    mockConfigServerFetch.mockRejectedValueOnce(authRefusal('decryption_failed'));
    const error = await adapter.listVersions().catch((e: unknown) => e);
    expect((error as RemoteAuthError).reason).toBe('decryption_failed');
    expect(mockRefresh).not.toHaveBeenCalled();
  });

  it('renews once per operation: a second refusal after the renewal is raised', async () => {
    mockConfigServerFetch
      .mockRejectedValueOnce(authRefusal('ip_mismatch'))
      .mockRejectedValueOnce(authRefusal('ip_mismatch'));
    const error = await adapter.listVersions().catch((e: unknown) => e);
    expect(error).toBeInstanceOf(RemoteTokenIpMismatchError);
    expect(mockRefresh).toHaveBeenCalledTimes(1);
    expect(mockConfigServerFetch).toHaveBeenCalledTimes(2);
  });

  it('without a login token for the server, names both remedies and renews nothing', async () => {
    mockLoginTokenFor.mockReturnValue(undefined);
    mockConfigServerFetch.mockRejectedValueOnce(authRefusal('ip_mismatch'));
    const error = await adapter.listVersions().catch((e: unknown) => e);
    expect(error).toBeInstanceOf(RemoteTokenIpMismatchError);
    expect((error as Error).message).toContain('rdc subscription login');
    expect((error as Error).message).toContain('rdc config remote enable');
    expect(mockRefresh).not.toHaveBeenCalled();
  });

  it('a transport seam login token wins over the stored one', async () => {
    adapter = new RemoteConfigAdapter(
      REMOTE,
      'cfg',
      storage as unknown as RemoteTokenStorage,
      { type: 'mock', get: vi.fn(), set: vi.fn(), delete: vi.fn() },
      { loginToken: () => 'rdt_seam' }
    );
    mockConfigServerFetch
      .mockRejectedValueOnce(authRefusal('token_expired'))
      .mockResolvedValueOnce({ data: { versions: [] } });
    await adapter.listVersions();
    expect(mockLoginTokenFor).not.toHaveBeenCalled();
    expect(mockRefresh.mock.calls[0]?.[1]).toBe('rdt_seam');
  });

  it('raises a refused renewal as it came, and keeps the dead token', async () => {
    const refused = new RemoteTokenRefreshError('login_scope', 'log in again');
    mockRefresh.mockRejectedValueOnce(refused);
    mockConfigServerFetch.mockRejectedValueOnce(authRefusal('ip_mismatch'));
    await expect(adapter.listVersions()).rejects.toBe(refused);
    expect(storage.saved).toEqual([]);
  });

  it('maps a team refusal of the renewal to the team error', async () => {
    mockRefresh.mockRejectedValueOnce(
      Object.assign(new Error('forbidden'), { status: 403, code: 'team_forbidden' })
    );
    mockConfigServerFetch.mockRejectedValueOnce(authRefusal('token_expired'));
    await expect(adapter.listVersions()).rejects.toBeInstanceOf(RemoteTeamForbiddenError);
  });

  it('a renewal that cannot reach the server raises the original refusal, never unreachable', async () => {
    const offline = new TypeError('fetch failed');
    mockRefresh.mockRejectedValueOnce(offline);
    mockConfigServerFetch.mockRejectedValueOnce(authRefusal('token_expired'));
    const error = await adapter.listVersions().catch((e: unknown) => e);
    expect(error).toBeInstanceOf(RemoteAuthError);
    expect((error as RemoteAuthError).reason).toBe('token_expired');
    expect((error as Error).cause).toBe(offline);
  });
});

describe('RemoteConfigAdapter.listVersions (T16)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("lists the config's archived versions in its team, with the archive time", async () => {
    const adapter = new RemoteConfigAdapter(
      REMOTE,
      'cfg',
      tokenStorage() as unknown as RemoteTokenStorage,
      { type: 'mock', get: vi.fn(), set: vi.fn(), delete: vi.fn() }
    );
    mockConfigServerFetch.mockResolvedValueOnce({
      data: {
        versions: [
          { version: 2, sdkEpoch: 7, createdAt: '2026-09-26T10:00:00.000Z', createdByUserId: 'u' },
        ],
      },
    });
    await expect(adapter.listVersions()).resolves.toEqual([
      { version: 2, sdkEpoch: 7, archivedAt: '2026-09-26T10:00:00.000Z' },
    ]);
    expect(mockConfigServerFetch.mock.calls[0]?.[0]).toBe(
      '/account/api/v1/configs/config-1/versions?teamId=team-1'
    );
  });
});
