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
  return section.checks.find((c) => c.value?.toString().startsWith('PROFESSIONAL'));
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
});
