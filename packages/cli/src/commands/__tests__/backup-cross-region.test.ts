/**
 * `backup restore --at <time>` across regions (plan K13).
 *
 * The CLI's default server is the default region, but a subscription lives in one region and its
 * token carries that region's server. Resolving a time reads the manifest index, and the index is
 * on the subscription's server: a request sent to the default region would answer another
 * subscription's (empty) index and refuse a time that has snapshots. The request must follow the
 * token, whatever the config's pointer names.
 */
import { BAKED_IN_REGIONS } from '@rediacc/shared/regions';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key} ${JSON.stringify(params)}` : key,
}));

const DEFAULT_REGION = BAKED_IN_REGIONS.find((r) => r.default) ?? BAKED_IN_REGIONS[0];
const OTHER_REGION = BAKED_IN_REGIONS.find((r) => r.domain !== DEFAULT_REGION.domain);
const DEFAULT_SERVER = `https://${DEFAULT_REGION.domain}`;
const OTHER_SERVER = `https://${OTHER_REGION?.domain}`;

vi.mock('../../services/account/account-pointer.js', () => ({
  readAccountPointer: () => ({ accountServer: DEFAULT_SERVER }),
}));
vi.mock('../../services/account/subscription-auth.js', () => ({
  normalizeServerUrl: (u: string) => u.replace(/\/+$/, ''),
  getSubscriptionServerUrl: () => DEFAULT_SERVER,
  getSubscriptionTokenState: () => ({
    kind: 'ready',
    token: { token: 'api-token', serverUrl: OTHER_SERVER },
    serverUrl: OTHER_SERVER,
  }),
}));
vi.mock('../../services/core/output.js', () => ({
  outputService: { info: vi.fn(), success: vi.fn(), warn: vi.fn(), error: vi.fn(), print: vi.fn() },
}));

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('resolveSnapshotAt with a token from another region', () => {
  it('has a second region to test against', () => {
    expect(OTHER_REGION).toBeDefined();
  });

  it("sends the manifest lookup to the token's server, never the config default", async () => {
    const urls: string[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        urls.push(String(url));
        // Key discovery fails (falls back to the baked-in production key) and the tunnel answers an error: only where each request went matters.
        return Promise.resolve({
          ok: false,
          status: 503,
          json: () => Promise.resolve({ error: 'unavailable' }),
        });
      })
    );
    const { resolveSnapshotAt } = await import('../backup.js');

    await expect(
      resolveSnapshotAt('f6545d49-c46e-4c14-8006-0ad5b37f3e08', '2026-08-14T12:00:00Z', {
        anyStream: true,
      })
    ).rejects.toThrow();

    const tunnel = urls.filter((u) => u.endsWith('/account/api/v1/tunnel'));
    expect(tunnel).toEqual([`${OTHER_SERVER}/account/api/v1/tunnel`]);
    expect(urls.some((u) => u.startsWith(DEFAULT_SERVER))).toBe(false);
  });
});
