import { beforeEach, describe, expect, it, vi } from 'vitest';

const report = vi.hoisted(() => ({ current: {} as Record<string, unknown> }));

vi.mock('../../services/account/subscription-auth.js', () => ({
  getSubscriptionTokenState: () => ({
    kind: 'present',
    token: { orgName: 'org', teamName: 'team' },
  }),
}));
vi.mock('../../services/account/license.js', () => ({
  fetchSubscriptionLicenseReport: async () => report.current,
}));
const config = vi.hoisted(() => ({ current: null as unknown }));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: { getCurrent: async () => config.current, getLocalMachine: async () => ({}) },
}));

const expectedOrigin = vi.hoisted(() => ({ current: undefined as string | undefined }));
const scan = vi.hoisted(() => ({ current: [] as unknown[] }));
vi.mock('../../services/backup/backup-store-universe.js', () => ({
  expectedAccountServerOrigin: () => expectedOrigin.current,
}));
vi.mock('../../services/account/license-machine.js', () => ({
  DEFAULT_DATASTORE: '/mnt/rediacc',
  scanRemoteRepoLicenses: async () => scan.current,
}));

import { checkSubscription } from '../doctor-subscription.js';

function base(status: string) {
  return {
    status,
    planCode: 'PROFESSIONAL',
    machineSlots: { active: 1, max: 3 },
    repoLicenses: {
      totalTrackedRepos: 1,
      validCount: 1,
      refreshRecommendedCount: 0,
      hardExpiredCount: 0,
    },
  };
}

async function statusRow() {
  const section = await checkSubscription();
  return section.checks.find((c) => c.value.toString().startsWith('PROFESSIONAL'));
}

describe('the doctor subscription status check', () => {
  beforeEach(() => {
    report.current = base('ACTIVE');
  });

  it('treats a lower-case active status from the account server as active', async () => {
    report.current = base('active');
    expect((await statusRow())?.status).toBe('ok');
  });

  it('keeps upper-case ACTIVE active', async () => {
    expect((await statusRow())?.status).toBe('ok');
  });

  it('CONTROL: an expired status still fails, in either case', async () => {
    report.current = base('expired');
    expect((await statusRow())?.status).toBe('fail');
    report.current = base('EXPIRED');
    expect((await statusRow())?.status).toBe('fail');
  });

  it('points a suspended subscription at the account owner or Rediacc, not billing', async () => {
    report.current = base('SUSPENDED');
    const row = await statusRow();
    expect(row?.hint).toContain('account owner or Rediacc');
    expect(row?.hint).not.toMatch(/billing/i);
  });

  it('points a full machine-slot count at an admin plan change, not self-serve upgrade', async () => {
    report.current = { ...base('ACTIVE'), machineSlots: { active: 3, max: 3 } };
    const section = await checkSubscription();
    const hint = section.checks.find((c) => c.value === '3/3')?.hint;
    expect(hint).toContain('account owner or Rediacc');
    expect(hint).not.toMatch(/upgrade/i);
  });

  it('CONTROL: an active subscription with free slots carries no hint', async () => {
    const section = await checkSubscription();
    expect(section.checks.every((c) => c.hint === undefined)).toBe(true);
  });
});

describe('the doctor repo-licence check', () => {
  const LIVE = '11111111-aaaa-4aaa-8aaa-000000000001';
  const DELETED = '22222222-bbbb-4bbb-8bbb-000000000002';

  function withLicences(recent: { repositoryGuid: string; freshness: string }[]) {
    const count = (f: string) => recent.filter((r) => r.freshness === f).length;
    report.current = {
      ...base('ACTIVE'),
      repoLicenses: {
        totalTrackedRepos: recent.length,
        validCount: count('valid'),
        refreshRecommendedCount: count('refresh_recommended'),
        hardExpiredCount: count('hard_expired'),
        recent,
      },
    };
  }

  async function licenceRow() {
    const section = await checkSubscription();
    return section.checks.find((c) => String(c.value).includes('expired'));
  }

  beforeEach(() => {
    config.current = {
      resources: {
        repositories: {
          web: {
            grand: 'main',
            placement: { machine: 'box' },
            tags: { main: { repositoryGuid: LIVE } },
          },
        },
      },
    };
  });

  it('warns, not fails, when every expired licence belongs to a repository not in this config, and names the retire command', async () => {
    withLicences([
      { repositoryGuid: LIVE, freshness: 'valid' },
      { repositoryGuid: DELETED, freshness: 'hard_expired' },
    ]);
    const row = await licenceRow();
    expect(row?.status).toBe('warn');
    expect(row?.value).toContain('1 expired (none in this config)');
    expect(row?.hint).toContain('rdc subscription retire --expired');
    expect(row?.hint).not.toContain('subscription refresh');
  });

  it('CONTROL: an expired licence of a repository this config holds still fails, naming both commands', async () => {
    withLicences([
      { repositoryGuid: LIVE, freshness: 'hard_expired' },
      { repositoryGuid: DELETED, freshness: 'hard_expired' },
    ]);
    const row = await licenceRow();
    expect(row?.status).toBe('fail');
    expect(row?.value).toContain('2 expired (1 in this config)');
    expect(row?.hint).toContain('rdc subscription refresh -m <machine>');
    expect(row?.hint).toContain('rdc subscription retire --expired');
  });

  it('fails with both commands when the report carries no licence list to split', async () => {
    report.current = {
      ...base('ACTIVE'),
      repoLicenses: {
        totalTrackedRepos: 3,
        validCount: 1,
        refreshRecommendedCount: 0,
        hardExpiredCount: 2,
      },
    };
    const row = await licenceRow();
    expect(row?.status).toBe('fail');
    expect(row?.hint).toContain('rdc subscription refresh -m <machine>');
    expect(row?.hint).toContain('rdc subscription retire --expired');
  });
});

describe('the doctor repo-licence check across account servers', () => {
  const LIVE = '11111111-aaaa-4aaa-8aaa-000000000001';

  beforeEach(() => {
    expectedOrigin.current = 'https://eu.rediacc.cloud';
    config.current = {
      resources: {
        repositories: {
          web: {
            grand: 'main',
            placement: { machine: 'box' },
            tags: { main: { repositoryGuid: LIVE } },
          },
        },
      },
    };
    report.current = {
      ...base('ACTIVE'),
      repoLicenses: {
        totalTrackedRepos: 1,
        validCount: 0,
        refreshRecommendedCount: 0,
        hardExpiredCount: 1,
        recent: [{ repositoryGuid: LIVE, freshness: 'hard_expired' }],
      },
    };
  });

  it('leaves the check ok with an info row when another account server issued the expired licence', async () => {
    scan.current = [
      {
        repositoryGuid: LIVE,
        currentRenewalUrl: 'https://bench-eu.rediacc.cloud/api/license/renew',
      },
    ];
    const section = await checkSubscription();
    const rows = section.checks.filter((c) => c.name === 'Repo licenses');
    expect(rows.length).toBeGreaterThan(0);
    expect(rows.every((c) => c.status === 'ok')).toBe(true);
    const info = rows.find((c) => String(c.value).startsWith('info:'));
    expect(info?.value).toContain('https://bench-eu.rediacc.cloud');
    expect(info?.hint).toContain('--adopt-origin');
  });

  it('CONTROL: an expired licence this config server issued still fails', async () => {
    scan.current = [
      { repositoryGuid: LIVE, currentRenewalUrl: 'https://eu.rediacc.cloud/api/license/renew' },
    ];
    const section = await checkSubscription();
    const row = section.checks.find((c) => String(c.value).includes('expired'));
    expect(row?.status).toBe('fail');
    expect(section.checks.some((c) => String(c.value).startsWith('info:'))).toBe(false);
  });
});
