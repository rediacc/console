/**
 * The background licence refresh every machine-touching command runs (maybeRefreshRepoLicenses), through the real
 * batch: it never overwrites a licence another account server issued, and REDIACC_NO_PROVISION=1 (forced by every ops
 * health read) skips it whole. 2026-11-11: a health read under `--config eu-bench` rewrote eleven production hostinger
 * licences with bench blobs, and renet refused all of them as `sequence_regression`.
 */

import { WK_ACCOUNT_DEFAULT_ORIGIN } from '@rediacc/shared/config/well-known.generated';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  tokenState: vi.fn(),
  fetch: vi.fn(),
  scan: vi.fn(),
  write: vi.fn(),
  renew: vi.fn(),
  warn: vi.fn(),
  isRefreshDue: vi.fn(),
  markRefreshAttempted: vi.fn(),
}));

const GUID_FOREIGN = '11111111-1111-4111-8111-111111111111';
const GUID_OWN = '22222222-2222-4222-8222-222222222222';

vi.mock('../../../i18n/index.js', () => ({ t: (key: string) => key }));
vi.mock('../../account/subscription-auth.js', () => ({
  getSubscriptionTokenState: m.tokenState,
  getSubscriptionServerUrl: () => WK_ACCOUNT_DEFAULT_ORIGIN,
}));
vi.mock('../../account/account-client.js', () => ({ accountServerFetch: m.fetch }));
vi.mock('../../account/license-machine.js', () => ({
  DEFAULT_DATASTORE: 'default',
  clusterIdFor: () => undefined,
  readLocalMachineId: () => Promise.resolve('client'),
  readRemoteMachineId: () => Promise.resolve('machine'),
  scanRemoteLicenseStatuses: () => Promise.resolve([]),
  scanRemoteRepoLicenses: m.scan,
  writeRepoLicense: m.write,
}));
vi.mock('../../account/free-license.js', () => ({
  resolveLicenseAuthority: vi.fn(),
  issueFreeRepoLicense: vi.fn(),
  renewInstalledLicenses: m.renew,
}));
vi.mock('../../account/license-refresh-state.js', () => ({
  isRefreshDue: m.isRefreshDue,
  markRefreshAttempted: m.markRefreshAttempted,
}));
vi.mock('../../config/config-resources.js', () => ({
  configService: {
    listRepositories: () =>
      Promise.resolve([
        { name: 'mail', config: { repositoryGuid: GUID_FOREIGN, grandGuid: GUID_FOREIGN } },
        { name: 'web', config: { repositoryGuid: GUID_OWN, grandGuid: GUID_OWN } },
      ]),
  },
}));
vi.mock('../../config/state-write-failure.js', () => ({ reportStateWriteRefused: vi.fn() }));
vi.mock('../../core/output.js', () => ({ outputService: { info: vi.fn(), warn: m.warn } }));
vi.mock('../../machine/machine-connection.js', () => ({
  machineConnections: { acquire: vi.fn() },
  sftpConfigForMachine: () => ({}),
  withSharedOrPooledSftp: (sftp: unknown, _c: unknown, fn: (s: unknown) => unknown) => fn(sftp),
}));
vi.mock('../../telemetry/telemetry.js', () => ({
  telemetryService: { trackEvent: vi.fn(), trackError: vi.fn() },
}));

import { maybeRefreshRepoLicenses } from '../license-recovery.js';

const MACHINE = { ip: '10.0.0.1', user: 'root' } as never;
const SFTP = { exec: vi.fn() } as never;
const DATES = { currentRefreshRecommendedAt: '2000-01-01', currentHardExpiresAt: '2000-02-01' };

function scanned(): unknown[] {
  return [
    {
      repositoryGuid: GUID_FOREIGN,
      requestedSizeGb: 1,
      ...DATES,
      currentRenewalUrl: 'https://bench.example.test/account/api/v1/licenses/renew',
    },
    {
      repositoryGuid: GUID_OWN,
      requestedSizeGb: 1,
      ...DATES,
      currentRenewalUrl: `${WK_ACCOUNT_DEFAULT_ORIGIN}/account/api/v1/licenses/renew`,
    },
  ];
}

const savedHold = process.env.REDIACC_NO_PROVISION;

beforeEach(() => {
  vi.clearAllMocks();
  delete process.env.REDIACC_NO_PROVISION;
  m.tokenState.mockReturnValue({ kind: 'ready' });
  m.isRefreshDue.mockResolvedValue(true);
  m.scan.mockResolvedValue(scanned());
  m.write.mockResolvedValue(undefined);
  m.renew.mockResolvedValue({ renewed: 0, results: [] });
  m.fetch.mockImplementation(
    (_path: string, init: { body: { repos: { repositoryGuid: string }[] } }) =>
      Promise.resolve({
        results: init.body.repos.map((r) => ({
          repositoryGuid: r.repositoryGuid,
          status: 'refreshed',
          license: { blob: r.repositoryGuid },
        })),
      })
  );
});

afterEach(() => {
  if (savedHold === undefined) delete process.env.REDIACC_NO_PROVISION;
  else process.env.REDIACC_NO_PROVISION = savedHold;
});

const written = (): unknown[] => m.write.mock.calls.map((c) => c[1]);

describe('the background licence refresh', () => {
  it('renews the expiring same-origin licence and never writes the foreign-origin one', async () => {
    await maybeRefreshRepoLicenses(MACHINE, 'hostinger', 'key', '/usr/bin/renet', SFTP);
    const sent = (m.fetch.mock.calls[0][1].body.repos as { repositoryGuid: string }[]).map(
      (r) => r.repositoryGuid
    );
    expect(sent).toEqual([GUID_OWN]);
    expect(written()).toEqual([GUID_OWN]);
    expect(m.warn).toHaveBeenCalledWith('warnings.licenseForeignOriginSkipped');
  });

  it('under REDIACC_NO_PROVISION=1 runs no scan, no account call and no licence write', async () => {
    process.env.REDIACC_NO_PROVISION = '1';
    await maybeRefreshRepoLicenses(MACHINE, 'hostinger', 'key', '/usr/bin/renet', SFTP);
    expect(m.markRefreshAttempted).not.toHaveBeenCalled();
    expect(m.scan).not.toHaveBeenCalled();
    expect(m.fetch).not.toHaveBeenCalled();
    expect(m.write).not.toHaveBeenCalled();
  });

  it('under REDIACC_NO_PROVISION=1 with no login runs no renet renewal either', async () => {
    process.env.REDIACC_NO_PROVISION = '1';
    m.tokenState.mockReturnValue({ kind: 'missing' });
    await maybeRefreshRepoLicenses(MACHINE, 'hostinger', 'key', '/usr/bin/renet', SFTP);
    expect(m.renew).not.toHaveBeenCalled();
  });

  it('without the explicit hold (REDIACC_NO_PROVISION=0) the refresh runs', async () => {
    process.env.REDIACC_NO_PROVISION = '0';
    await maybeRefreshRepoLicenses(MACHINE, 'hostinger', 'key', '/usr/bin/renet', SFTP);
    expect(written()).toEqual([GUID_OWN]);
  });
});
