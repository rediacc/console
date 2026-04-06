import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../subscription-auth.js', () => ({
  normalizeServerUrl: (url: string) => url.replace(/\/+$/, ''),
  loadServerConfig: vi.fn().mockReturnValue(null),
  saveServerConfig: vi.fn(),
  getSubscriptionServerUrl: vi.fn().mockReturnValue('https://eu.rediacc.com'),
  getSubscriptionTokenState: vi.fn().mockReturnValue({ kind: 'missing' }),
}));

vi.mock('../updater.js', () => ({
  resolveChannel: vi.fn().mockReturnValue('stable'),
}));

vi.mock('../../version.js', () => ({
  VERSION: '0.9.0',
}));

import { fetchServerInfo } from '../account-client.js';

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

    await fetchServerInfo('https://edge-eu.rediacc.com');

    expect(globalThis.fetch).toHaveBeenCalledWith(
      'https://edge-eu.rediacc.com/account/api/v1/.well-known/server-info',
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

    await fetchServerInfo('https://eu.rediacc.com/');

    expect(globalThis.fetch).toHaveBeenCalledWith(
      'https://eu.rediacc.com/account/api/v1/.well-known/server-info',
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

    const info = await fetchServerInfo('https://edge-eu.rediacc.com');
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

    const info = await fetchServerInfo('https://eu.rediacc.com');
    expect(info.environment).toBe('production');
    expect(info.updateChannel).toBe('stable');
  });

  it('throws on non-OK response', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
    });

    await expect(fetchServerInfo('https://eu.rediacc.com')).rejects.toThrow(
      'server-info returned 500'
    );
  });

  it('throws on network error', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('Network error'));

    await expect(fetchServerInfo('https://eu.rediacc.com')).rejects.toThrow('Network error');
  });
});
