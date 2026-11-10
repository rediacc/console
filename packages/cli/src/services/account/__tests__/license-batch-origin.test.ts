import { WK_ACCOUNT_DEFAULT_ORIGIN } from '@rediacc/shared/config/well-known.generated';
import { describe, expect, it, vi } from 'vitest';

const fetchMock = vi.hoisted(() => vi.fn());
const scanMock = vi.hoisted(() => vi.fn());
const GUIDS = vi.hoisted(() => [
  '11111111-1111-4111-8111-111111111111',
  '22222222-2222-4222-8222-222222222222',
]);

vi.mock('../account-client.js', () => ({ accountServerFetch: fetchMock }));
vi.mock('../license-machine.js', () => ({
  DEFAULT_DATASTORE: 'default',
  clusterIdFor: () => undefined,
  readLocalMachineId: () => Promise.resolve('client'),
  readRemoteMachineId: () => Promise.resolve('machine'),
  scanRemoteLicenseStatuses: () => Promise.resolve([]),
  scanRemoteRepoLicenses: scanMock,
  writeRepoLicense: () => Promise.resolve(),
}));
vi.mock('../../config/config-resources.js', () => ({
  configService: {
    listRepositories: () =>
      Promise.resolve(GUIDS.map((g) => ({ config: { repositoryGuid: g, grandGuid: g } }))),
  },
}));
vi.mock('../../machine/machine-connection.js', () => ({
  sftpConfigForMachine: () => ({}),
  withSharedOrPooledSftp: (sftp: unknown, _c: unknown, fn: (s: unknown) => unknown) => fn(sftp),
}));
vi.mock('../../telemetry/telemetry.js', () => ({ telemetryService: { trackError: vi.fn() } }));

const server = vi.hoisted(() => ({ url: '' }));

vi.mock('../subscription-auth.js', () => ({
  getSubscriptionServerUrl: () => server.url,
  getSubscriptionTokenState: () => ({ kind: 'ready' }),
}));

import { refreshRepoLicensesBatch, reposWithForeignLicenseOrigin } from '../license-batch.js';

const OLD = '11111111-1111-4111-8111-111111111111';
const FRESH = '22222222-2222-4222-8222-222222222222';
const BARE = '33333333-3333-4333-8333-333333333333';
const NEW_ORIGIN = WK_ACCOUNT_DEFAULT_ORIGIN;
server.url = NEW_ORIGIN;
const DATES = { currentRefreshRecommendedAt: '2099-01-01', currentHardExpiresAt: '2099-02-01' };

const scan = [
  {
    repositoryGuid: OLD,
    requestedSizeGb: 1,
    ...DATES,
    currentRenewalUrl: 'https://eu.rediacc.com/account/api/v1/licenses/renew',
  },
  {
    repositoryGuid: FRESH,
    requestedSizeGb: 1,
    ...DATES,
    currentRenewalUrl: `${NEW_ORIGIN}/account/api/v1/licenses/renew`,
  },
  { repositoryGuid: BARE, requestedSizeGb: 1, ...DATES },
];

describe('reposWithForeignLicenseOrigin', () => {
  it('flags a licence issued by another origin and leaves same-origin and origin-less ones', () => {
    expect([...reposWithForeignLicenseOrigin(scan, 'hostinger')]).toEqual([OLD]);
  });

  it('counts a renewalUrl that does not parse as foreign', () => {
    const odd = [{ repositoryGuid: OLD, requestedSizeGb: 1, currentRenewalUrl: 'not a url' }];
    expect([...reposWithForeignLicenseOrigin(odd, 'hostinger')]).toEqual([OLD]);
  });

  it('compares origins when the configured server URL carries a path', () => {
    server.url = `${NEW_ORIGIN}/account/api/v1`;
    try {
      expect([...reposWithForeignLicenseOrigin(scan, 'hostinger')]).toEqual([OLD]);
    } finally {
      server.url = NEW_ORIGIN;
    }
  });

  it('refuses a configured server that is not a URL instead of reissuing every licence', () => {
    server.url = 'not a url';
    try {
      expect(() => reposWithForeignLicenseOrigin(scan, 'hostinger')).toThrow(
        /"not a url" is not a URL/
      );
    } finally {
      server.url = NEW_ORIGIN;
    }
  });
});

describe('refreshRepoLicensesBatch force reissue', () => {
  async function requestedRepos(): Promise<Map<unknown, Record<string, unknown>>> {
    scanMock.mockResolvedValue(scan.slice(0, 2));
    fetchMock.mockResolvedValue({ results: [] });
    await refreshRepoLicensesBatch('hostinger', {} as never, 'key', undefined, {} as never);
    const repos = fetchMock.mock.calls.at(-1)?.[1].body.repos as Record<string, unknown>[];
    return new Map(repos.map((r) => [r.repositoryGuid, r]));
  }

  it('drops the current dates only for the repo whose scan names another origin', async () => {
    const byGuid = await requestedRepos();
    expect(byGuid.get(OLD)?.currentHardExpiresAt).toBeUndefined();
    expect(byGuid.get(OLD)?.currentRefreshRecommendedAt).toBeUndefined();
  });

  it('keeps the dates of a same-origin licence', async () => {
    const byGuid = await requestedRepos();
    expect(byGuid.get(FRESH)?.currentHardExpiresAt).toBe('2099-02-01');
    expect(byGuid.get(FRESH)?.currentRefreshRecommendedAt).toBe('2099-01-01');
  });
});
