import {
  WK_ACCOUNT_DEFAULT_ORIGIN,
  WK_BENCH_ORIGIN,
} from '@rediacc/shared/config/well-known.generated';
import { BAKED_IN_REGIONS } from '@rediacc/shared/regions';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const fetchMock = vi.hoisted(() => vi.fn());
const scanMock = vi.hoisted(() => vi.fn());
const writeMock = vi.hoisted(() => vi.fn());
const warnMock = vi.hoisted(() => vi.fn());
const statusMock = vi.hoisted(() => vi.fn(() => Promise.resolve([] as unknown[])));
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
  scanRemoteLicenseStatuses: statusMock,
  scanRemoteRepoLicenses: scanMock,
  writeRepoLicense: writeMock,
}));
vi.mock('../../core/output.js', () => ({ outputService: { warn: warnMock } }));
vi.mock('../../../i18n/index.js', () => ({
  t: (key: string, vars?: Record<string, unknown>) => `${key} ${JSON.stringify(vars ?? {})}`,
}));
vi.mock('../../config/config-resources.js', () => ({
  configService: {
    listRepositories: () =>
      Promise.resolve(
        GUIDS.map((g, i) => ({ name: `repo${i}`, config: { repositoryGuid: g, grandGuid: g } }))
      ),
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

  it('control: compares origins when the configured server URL carries a path', () => {
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

describe('refreshRepoLicensesBatch and a foreign-origin licence', () => {
  beforeEach(() => {
    fetchMock.mockReset();
    writeMock.mockReset().mockResolvedValue(undefined);
    warnMock.mockReset();
  });

  async function refresh(
    scanned: typeof scan,
    options?: { adoptOrigin?: boolean }
  ): Promise<{
    result: Awaited<ReturnType<typeof refreshRepoLicensesBatch>>;
    sent: Map<unknown, Record<string, unknown>>;
  }> {
    scanMock.mockResolvedValue(scanned);
    // The server answers `refreshed` with a blob for every repo it is sent, so every repo sent is a licence written.
    fetchMock.mockImplementation(
      (_path: string, init: { body: { repos: { repositoryGuid: string }[] } }) =>
        Promise.resolve({
          results: init.body.repos.map((r) => ({
            repositoryGuid: r.repositoryGuid,
            status: 'refreshed',
            license: { blob: r.repositoryGuid },
          })),
        })
    );
    const result = await refreshRepoLicensesBatch(
      'hostinger',
      {} as never,
      'key',
      undefined,
      {} as never,
      undefined,
      undefined,
      options
    );
    const repos = (fetchMock.mock.calls.at(-1)?.[1].body.repos ?? []) as Record<string, unknown>[];
    return { result, sent: new Map(repos.map((r) => [r.repositoryGuid, r])) };
  }

  it('leaves a licence another account server issued out of the request, and writes nothing for it', async () => {
    const { result, sent } = await refresh(scan.slice(0, 2));
    expect(sent.has(OLD)).toBe(false);
    expect(writeMock.mock.calls.map((c) => c[1])).not.toContain(OLD);
    expect(result.failures.map((f) => f.repositoryGuid)).toContain(OLD);
  });

  it('warns once naming the repository, the machine and both account servers', async () => {
    await refresh(scan.slice(0, 2));
    expect(warnMock).toHaveBeenCalledTimes(1);
    const text = String(warnMock.mock.calls[0][0]);
    expect(text).toContain('warnings.licenseForeignOriginSkipped');
    expect(text).toContain('"repo":"repo0"');
    expect(text).toContain('"machine":"hostinger"');
    expect(text).toContain('"licenseOrigin":"https://eu.rediacc.com"');
    expect(text).toContain(`"configOrigin":"${NEW_ORIGIN}"`);
  });

  it('sends nothing at all when every licence on the machine is foreign', async () => {
    const { result } = await refresh(scan.slice(0, 1));
    expect(fetchMock).not.toHaveBeenCalled();
    expect(writeMock).not.toHaveBeenCalled();
    expect(result.valid).toBe(0);
    expect(result.recoveryFailureMode).toBe('server_rejected_all');
    expect(result.serverErrorSample).toContain('errors.license.foreignOriginSkipped');
  });

  it('still renews a same-origin licence beside the skipped one, keeping its dates', async () => {
    const { result, sent } = await refresh(scan.slice(0, 2));
    expect(sent.get(FRESH)?.currentHardExpiresAt).toBe('2099-02-01');
    expect(sent.get(FRESH)?.currentRefreshRecommendedAt).toBe('2099-01-01');
    expect(writeMock.mock.calls.map((c) => c[1])).toEqual([FRESH]);
    expect(result.refreshed).toBe(1);
  });

  it.each(['machine_mismatch', 'identity_mismatch'])(
    'does not count a skipped foreign licence as a pending reissue when renet says %s',
    async (status) => {
      statusMock.mockResolvedValueOnce([{ repositoryGuid: OLD, status }]);
      const { result } = await refresh(scan.slice(0, 2));
      expect(result.invalidSignatureDetected).toBe(0);
    }
  );

  it('keeps a same-origin copy of a guid beside its foreign sibling, warning once for the foreign one', async () => {
    const sibling = {
      ...scan[0],
      currentRenewalUrl: `${NEW_ORIGIN}/account/api/v1/licenses/renew`,
    };
    const { sent } = await refresh([scan[0], sibling]);
    expect(sent.has(OLD)).toBe(true);
    expect(warnMock).toHaveBeenCalledTimes(1);
  });

  it('with adoptOrigin reissues the foreign licence, dropping its current dates', async () => {
    const { sent } = await refresh(scan.slice(0, 2), { adoptOrigin: true });
    expect(sent.has(OLD)).toBe(true);
    expect(sent.get(OLD)?.currentHardExpiresAt).toBeUndefined();
    expect(sent.get(OLD)?.currentRefreshRecommendedAt).toBeUndefined();
    expect(sent.get(FRESH)?.currentHardExpiresAt).toBe('2099-02-01');
    expect(new Set(writeMock.mock.calls.map((c) => c[1]))).toEqual(new Set([OLD, FRESH]));
    expect(warnMock).not.toHaveBeenCalled();
  });

  describe('a FREE licence from another production region', () => {
    const EU = WK_ACCOUNT_DEFAULT_ORIGIN;
    const US = `https://${BAKED_IN_REGIONS.find((r) => r.id === 'us')?.domain}`;
    const BENCH = WK_BENCH_ORIGIN;
    const entry = (guid: string, origin: string, subscriptionId: string) => ({
      repositoryGuid: guid,
      requestedSizeGb: 1,
      ...DATES,
      currentRenewalUrl: `${origin}/account/api/v1/licenses/renew`,
      currentSubscriptionId: subscriptionId,
    });

    async function refreshUnder(
      configOrigin: string,
      repo: Omit<ReturnType<typeof entry>, 'currentSubscriptionId'> & {
        currentSubscriptionId?: string;
      }
    ) {
      server.url = configOrigin;
      try {
        return await refresh([repo]);
      } finally {
        server.url = NEW_ORIGIN;
      }
    }

    it('is reissued under a us production config without the flag, dropping its current dates', async () => {
      const { sent } = await refreshUnder(US, entry(OLD, EU, 'free:0123abcd'));
      expect(sent.has(OLD)).toBe(true);
      expect(sent.get(OLD)?.currentHardExpiresAt).toBeUndefined();
      expect(writeMock.mock.calls.map((c) => c[1])).toEqual([OLD]);
      expect(warnMock).not.toHaveBeenCalled();
    });

    it('control: a paid licence from the same eu origin is still skipped', async () => {
      const { sent } = await refreshUnder(US, entry(OLD, EU, 'sub_paid_1'));
      expect(sent.size).toBe(0);
      expect(writeMock).not.toHaveBeenCalled();
      expect(warnMock).toHaveBeenCalledTimes(1);
    });

    it('control: a bench-origin FREE licence under a production config is still skipped', async () => {
      const { sent } = await refreshUnder(US, entry(OLD, BENCH, 'free:0123abcd'));
      expect(sent.size).toBe(0);
      expect(writeMock).not.toHaveBeenCalled();
      expect(warnMock).toHaveBeenCalledTimes(1);
    });

    it('control: a FREE licence under a bench config is still skipped', async () => {
      const { sent } = await refreshUnder(BENCH, entry(OLD, EU, 'free:0123abcd'));
      expect(sent.size).toBe(0);
      expect(warnMock).toHaveBeenCalledTimes(1);
    });

    it('control: a licence whose scan entry reports no subscription id is not taken for FREE', async () => {
      const { currentSubscriptionId: _dropped, ...bare } = entry(OLD, EU, 'free:0123abcd');
      expect(_dropped).toBe('free:0123abcd');
      const { sent } = await refreshUnder(US, bare);
      expect(sent.size).toBe(0);
    });
  });
});
