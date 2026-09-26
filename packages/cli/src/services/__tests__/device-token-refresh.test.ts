import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockAccountServerFetch, mockTokenState } = vi.hoisted(() => ({
  mockAccountServerFetch: vi.fn(),
  mockTokenState: vi.fn(),
}));

vi.mock('../account/account-client.js', () => ({ accountServerFetch: mockAccountServerFetch }));
vi.mock('../account/subscription-auth.js', () => ({
  getSubscriptionTokenState: mockTokenState,
  normalizeServerUrl: (url: string) => url.replace(/\/+$/, ''),
}));

import type { RemoteConfig } from '../../types/index.js';
import {
  DEVICE_TOKEN_REFRESH_PATH,
  loginTokenFor,
  REFRESHABLE_AUTH_REASONS,
  RemoteTokenRefreshError,
  refreshDeviceToken,
} from '../config/device-token-refresh.js';

const REMOTE: RemoteConfig = {
  apiUrl: 'https://account.example.com',
  storeId: 'store-1',
  configId: 'config-1',
  teamId: 'team-1',
  storageKeyId: 'key-1',
};

function refusal(status: number, code?: string, message = 'refused') {
  return Object.assign(new Error(message), { status, ...(code ? { code } : {}) });
}

function refusedWith(error: unknown): Promise<unknown> {
  mockAccountServerFetch.mockRejectedValueOnce(error);
  return refreshDeviceToken(REMOTE, 'rdt_login').catch((e: unknown) => e);
}

describe('device token refresh (T11)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('posts the store and team with the login token to the refresh route, and returns the new token', async () => {
    mockAccountServerFetch.mockResolvedValueOnce({ deviceToken: 'rct_new' });
    const fetchImpl = vi.fn() as unknown as typeof fetch;

    await expect(refreshDeviceToken(REMOTE, 'rdt_login', { fetchImpl })).resolves.toBe('rct_new');
    expect(mockAccountServerFetch).toHaveBeenCalledWith(DEVICE_TOKEN_REFRESH_PATH, {
      method: 'POST',
      body: { storeId: 'store-1', teamId: 'team-1' },
      token: 'rdt_login',
      serverUrl: 'https://account.example.com',
      fetchImpl,
    });
  });

  it('sends teamId null for an org-level config', async () => {
    mockAccountServerFetch.mockResolvedValueOnce({ deviceToken: 'rct_new' });
    await refreshDeviceToken({ ...REMOTE, teamId: undefined }, 'rdt_login');
    expect(mockAccountServerFetch.mock.calls[0]?.[1]).toMatchObject({
      body: { storeId: 'store-1', teamId: null },
    });
  });

  it('refuses an answer without a token', async () => {
    mockAccountServerFetch.mockResolvedValueOnce({});
    const error = await refreshDeviceToken(REMOTE, 'rdt_login').catch((e: unknown) => e);
    expect(error).toBeInstanceOf(RemoteTokenRefreshError);
    expect((error as RemoteTokenRefreshError).code).toBe('malformed_response');
  });

  it.each([
    [401, undefined, 'login_invalid', 'rdc subscription login'],
    [403, undefined, 'login_scope', 'rdc subscription login'],
    [403, 'TOKEN_IP_MISMATCH', 'login_ip_mismatch', 'rdc config remote enable'],
    [403, 'not_store_member', 'not_store_member', 'store-1'],
    [403, 'store_mismatch', 'store_mismatch', 'store-1'],
    [403, 'stale_cek_generation', 'stale_cek_generation', 'rdc config remote enable'],
    [429, undefined, 'rate_limited', 'Too many'],
    [500, undefined, 'refresh_failed', 'rdc config remote enable'],
  ])('maps %i %s to %s, naming the remedy', async (status, code, expected, remedy) => {
    const error = await refusedWith(refusal(status, code, 'Too many requests'));
    expect(error).toBeInstanceOf(RemoteTokenRefreshError);
    expect((error as RemoteTokenRefreshError).code).toBe(expected);
    expect((error as Error).message).toContain(remedy);
  });

  it('keeps the rebind message of a login token bound elsewhere and adds the enable remedy', async () => {
    const rebindMessage =
      'Your IP address changed ... run `rdc subscription login` to sign in again.';
    const error = await refusedWith(refusal(403, 'TOKEN_IP_MISMATCH', rebindMessage));
    expect((error as Error).message).toContain(rebindMessage);
    expect((error as Error).message).toContain('rdc config remote enable');
  });

  it.each([
    [403, 'team_forbidden'],
    [404, 'team_not_found'],
  ])('passes the team refusal %i %s through for the adapter to map', async (status, code) => {
    const raw = refusal(status, code);
    expect(await refusedWith(raw)).toBe(raw);
  });

  it('passes a network failure through', async () => {
    const raw = new TypeError('fetch failed');
    expect(await refusedWith(raw)).toBe(raw);
  });

  it('refreshes the four dead-chain reasons and never decryption_failed', () => {
    expect([...REFRESHABLE_AUTH_REASONS].sort()).toEqual([
      'invalid_token',
      'ip_mismatch',
      'token_exhausted',
      'token_expired',
    ]);
    expect(REFRESHABLE_AUTH_REASONS.has('decryption_failed')).toBe(false);
  });

  it('uses the stored login only for the config server it belongs to', () => {
    mockTokenState.mockReturnValue({
      kind: 'ready',
      token: { token: 'rdt_login', serverUrl: 'https://account.example.com/' },
      serverUrl: 'https://account.example.com/',
    });
    expect(loginTokenFor('https://account.example.com')).toBe('rdt_login');
    expect(loginTokenFor('https://other.example.com')).toBeUndefined();
    mockTokenState.mockReturnValue({ kind: 'missing' });
    expect(loginTokenFor('https://account.example.com')).toBeUndefined();
  });
});
