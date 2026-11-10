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

vi.mock('../subscription-auth.js', () => ({
  getSubscriptionServerUrl: () => 'https://eu.rediacc.cloud',
  getSubscriptionTokenState: () => ({ kind: 'ready' }),
}));

import { LISTING_COMPLETE_MARKER } from '../../backup/backup-store-universe.js';
import {
  foreignOriginLicenseGuids,
  guidsWithForeignLicenseOrigin,
  refreshRepoLicensesBatch,
} from '../license-batch.js';

const OLD = '11111111-1111-4111-8111-111111111111';
const FRESH = '22222222-2222-4222-8222-222222222222';
const BARE = '33333333-3333-4333-8333-333333333333';
const NEW_ORIGIN = 'https://eu.rediacc.cloud';

function licenseFile(renewalUrl?: string): string {
  const payload = Buffer.from(JSON.stringify(renewalUrl ? { renewalUrl } : { other: 1 })).toString(
    'base64'
  );
  return Buffer.from(JSON.stringify({ payload })).toString('base64');
}

const listing = [
  `${OLD}\t${licenseFile('https://eu.rediacc.com/account/api/v1/licenses/renew')}`,
  `${FRESH}\t${licenseFile(`${NEW_ORIGIN}/account/api/v1/licenses/renew`)}`,
  `${BARE}\t${licenseFile()}`,
  LISTING_COMPLETE_MARKER,
].join('\n');

describe('guidsWithForeignLicenseOrigin', () => {
  it('flags a licence issued by another origin and leaves same-origin and origin-less ones', () => {
    expect([...guidsWithForeignLicenseOrigin(listing, NEW_ORIGIN)]).toEqual([OLD]);
  });
});

describe('foreignOriginLicenseGuids', () => {
  it('reads the machine listing against the active config origin', async () => {
    const exec = vi.fn().mockResolvedValue(listing);
    const guids = await foreignOriginLicenseGuids({ exec }, 'hostinger');
    expect([...guids]).toEqual([OLD]);
    expect(exec.mock.calls[0][0]).toContain('sudo -n sh -c');
  });

  it('names the failure when the listing command fails', async () => {
    const exec = vi.fn().mockRejectedValue(new Error('sudo: a password is required'));
    await expect(foreignOriginLicenseGuids({ exec }, 'hostinger')).rejects.toThrow(
      /Cannot read the installed licences on hostinger.*password is required/
    );
  });

  it('names the failure when the listing is cut short', async () => {
    const exec = vi.fn().mockResolvedValue(`${OLD}\t${licenseFile('https://x.example/r')}\n`);
    await expect(foreignOriginLicenseGuids({ exec }, 'hostinger')).rejects.toThrow(/cut short/);
  });
});

describe('refreshRepoLicensesBatch force reissue', () => {
  it('drops the current dates only for the repo whose licence came from another origin', async () => {
    const dates = { currentRefreshRecommendedAt: '2099-01-01', currentHardExpiresAt: '2099-02-01' };
    scanMock.mockResolvedValue(
      [OLD, FRESH].map((repositoryGuid) => ({ repositoryGuid, requestedSizeGb: 1, ...dates }))
    );
    fetchMock.mockResolvedValue({ results: [] });
    const exec = vi.fn().mockResolvedValue(listing);
    await refreshRepoLicensesBatch('hostinger', {} as never, 'key', undefined, { exec } as never);
    const repos = fetchMock.mock.calls[0][1].body.repos as Record<string, unknown>[];
    const byGuid = new Map(repos.map((r) => [r.repositoryGuid, r]));
    expect(byGuid.get(OLD)?.currentHardExpiresAt).toBeUndefined();
    expect(byGuid.get(OLD)?.currentRefreshRecommendedAt).toBeUndefined();
    expect(byGuid.get(FRESH)?.currentHardExpiresAt).toBe('2099-02-01');
    expect(byGuid.get(FRESH)?.currentRefreshRecommendedAt).toBe('2099-01-01');
  });
});
