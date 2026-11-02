/**
 * `subscription status` splits the server's repo license counts by membership in the
 * current config, and `repo delete` tells the server the license is retired.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));

const mockPrint = vi.hoisted(() => vi.fn());
const infos = vi.hoisted(() => [] as string[]);
const warns = vi.hoisted(() => [] as string[]);
vi.mock('../../services/core/output.js', () => ({
  outputService: {
    info: (m: string) => infos.push(m),
    warn: (m: string) => warns.push(m),
    success: vi.fn(),
    print: mockPrint,
  },
}));

const mockReport = vi.hoisted(() => vi.fn());
vi.mock('../../services/account/license.js', () => ({
  fetchSubscriptionLicenseReportOrThrow: mockReport,
}));
const tokenKind = vi.hoisted(() => ({ value: 'ready' }));
vi.mock('../../services/account/subscription-auth.js', () => ({
  getSubscriptionTokenState: () => ({ kind: tokenKind.value, token: {} }),
  getSubscriptionScopeMismatch: () => null,
  getSubscriptionServerUrl: () => 'http://localhost',
}));
const mockListRepos = vi.hoisted(() => vi.fn());
vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getTeam: vi.fn().mockResolvedValue(undefined),
    listRepositories: mockListRepos,
  },
}));
const mockFetch = vi.hoisted(() => vi.fn());
vi.mock('../../services/account/account-client.js', () => ({ accountServerFetch: mockFetch }));

import { setOutputFormat } from '../../utils/errors.js';
import { settleRepoLicense } from '../repo-delete-settle.js';
import { executeSubscriptionStatus, splitRepoLicensesByConfig } from '../subscription-actions.js';

const recent = [
  { repositoryGuid: 'a', freshness: 'valid' },
  { repositoryGuid: 'b', freshness: 'hard_expired' },
  { repositoryGuid: 'c', freshness: 'valid' },
  { repositoryGuid: 'd', freshness: 'refresh_recommended' },
];

describe('subscription status reconcile view', () => {
  beforeEach(() => {
    infos.length = 0;
    warns.length = 0;
  });

  it('splits the tracked repositories by config membership', () => {
    expect(splitRepoLicensesByConfig(recent, new Set(['a', 'd']))).toEqual({
      totalTrackedRepos: 2,
      validCount: 1,
      refreshRecommendedCount: 1,
      hardExpiredCount: 0,
      notInConfigCount: 2,
    });
  });

  it('keeps the account-wide total: the in-config and not-in-config counts add up to the server total', () => {
    const split = splitRepoLicensesByConfig(recent, new Set(['a', 'd']));
    expect(split.totalTrackedRepos + split.notInConfigCount).toBe(recent.length);
  });

  it('prints the in-config and not-in-config lines from the report', async () => {
    mockReport.mockResolvedValue({
      planCode: 'ENTERPRISE',
      status: 'active',
      machineSlots: { active: 0, max: 1, machines: [] },
      repoLicenseIssuances: { used: 0, limit: 10 },
      repoLicenses: {
        totalTrackedRepos: 4,
        validCount: 2,
        refreshRecommendedCount: 1,
        hardExpiredCount: 1,
        recent,
      },
    });
    mockListRepos.mockResolvedValue([
      { name: 'x', config: { repositoryGuid: 'a' } },
      { name: 'y', config: { repositoryGuid: 'b' } },
    ]);
    await executeSubscriptionStatus();
    const out = infos.join('\n');
    expect(out).toContain('remoteRepoLicensesInConfig:');
    expect(out).toContain('"totalTrackedRepos":2');
    expect(out).toContain('remoteRepoLicensesNotInConfig:{"count":2}');
    expect(out).not.toContain('commands.subscription.status.remoteRepoLicenses:');
  });

  it('emits structured data through outputService.print under -o json, with no info lines', async () => {
    mockReport.mockResolvedValue({
      orgName: 'Acme',
      planCode: 'ENTERPRISE',
      status: 'active',
      machineSlots: { active: 1, max: 2, machines: [{ machineId: 'm1', overLimit: true }] },
      repoLicenseIssuances: { used: 0, limit: 10 },
      repoLicenses: {
        totalTrackedRepos: 4,
        validCount: 2,
        refreshRecommendedCount: 1,
        hardExpiredCount: 1,
        recent,
      },
    });
    mockListRepos.mockResolvedValue([{ name: 'x', config: { repositoryGuid: 'a' } }]);
    mockPrint.mockClear();
    setOutputFormat('json');
    try {
      await executeSubscriptionStatus();
    } finally {
      setOutputFormat('table');
    }
    expect(infos).toEqual([]);
    expect(mockPrint).toHaveBeenCalledTimes(1);
    const [data, format] = mockPrint.mock.calls[0] as [Record<string, unknown>, string];
    expect(format).toBe('json');
    expect(data).toMatchObject({
      organization: 'Acme',
      plan: 'ENTERPRISE',
      status: 'active',
      overLimitCount: 1,
      repoLicenses: { totalTrackedRepos: 1, notInConfigCount: 3, scope: 'config' },
    });
  });

  it('falls back to the server totals when the server sends no per-repo list', async () => {
    mockReport.mockResolvedValue({
      planCode: 'ENTERPRISE',
      status: 'active',
      machineSlots: { active: 0, max: 1, machines: [] },
      repoLicenseIssuances: { used: 0, limit: 10 },
      repoLicenses: {
        totalTrackedRepos: 4,
        validCount: 4,
        refreshRecommendedCount: 0,
        hardExpiredCount: 0,
      },
    });
    mockListRepos.mockResolvedValue([]);
    await executeSubscriptionStatus();
    expect(infos.join('\n')).toContain('commands.subscription.status.remoteRepoLicenses:');
  });
});

describe('repo delete retires the license', () => {
  beforeEach(() => {
    warns.length = 0;
    mockFetch.mockReset();
  });

  it('POSTs the retire route for the repository GUID, forks included', async () => {
    mockFetch.mockResolvedValue({ retired: true });
    await settleRepoLicense('lva:m1', { repositoryGuid: 'f1', grandGuid: 'g1' });
    const [url, init] = mockFetch.mock.calls[0] as [string, { method: string }];
    expect(url).toBe('/account/api/v1/licenses/repos/f1/retire');
    expect(init.method).toBe('POST');
  });

  it('sends nothing without an account token: no license was issued from this config', async () => {
    tokenKind.value = 'missing';
    try {
      await settleRepoLicense('lva', { repositoryGuid: 'g1', grandGuid: 'g1' });
    } finally {
      tokenKind.value = 'ready';
    }
    expect(mockFetch).not.toHaveBeenCalled();
    expect(warns).toEqual([]);
  });

  it('a failed retire warns and never fails the delete', async () => {
    mockFetch.mockRejectedValue(new Error('server down'));
    await expect(
      settleRepoLicense('lva', { repositoryGuid: 'g1', grandGuid: 'g1' })
    ).resolves.toBeUndefined();
    expect(warns.join('\n')).toContain('licenseRetireFailed');
  });
});
