/**
 * PLAN-detached-jobs J20: the subscription verbs.
 *
 * `subscription status` without `-m` is the account view and starts no job: it asks the account server and prints, so no
 * machine is involved. `subscription status -m` and `subscription refresh` read and write the machine over SFTP with no
 * renet function or command kind behind them (renet's command-kind allow-list has no license entry), so they stay
 * unconverted until renet gains one; the plan table names them, and CONVERTED does not.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));

const m = vi.hoisted(() => ({
  execute: vi.fn(),
  print: vi.fn(),
  report: vi.fn(),
}));

vi.mock('../../services/executor/executor-factory.js', () => ({
  getExecutor: () => ({ execute: m.execute }),
}));
vi.mock('../../services/account/subscription-auth.js', () => ({
  getSubscriptionScopeMismatch: () => undefined,
  getSubscriptionServerUrl: () => 'https://account.test',
  getSubscriptionTokenState: () => ({ kind: 'ready', token: { teamName: 'team' } }),
}));
vi.mock('../../services/account/license.js', () => ({
  fetchSubscriptionLicenseReportOrThrow: m.report,
  readMachineActivationStatus: vi.fn(),
  readRuntimeRepoLicenseStatuses: vi.fn(),
  refreshRepoLicenseIdentity: vi.fn(),
  refreshRepoLicensesBatch: vi.fn(),
}));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getTeam: vi.fn().mockResolvedValue('team'),
    listRepositories: vi.fn().mockResolvedValue([]),
  },
}));
vi.mock('../../services/renet/renet-execution.js', () => ({
  acquireRemoteRenet: vi.fn(),
  readSSHKey: vi.fn(),
}));
vi.mock('../../services/core/output.js', () => ({
  outputService: { info: vi.fn(), success: vi.fn(), warn: vi.fn(), error: vi.fn(), print: m.print },
}));
vi.mock('../../utils/errors.js', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  getOutputFormat: () => 'json',
}));

const { executeSubscriptionStatus } = await import('../subscription-actions.js');
const { JOB_PLANS, CONVERTED } = await import('../../services/jobs/plans.js');

beforeEach(() => {
  vi.clearAllMocks();
  m.report.mockResolvedValue({
    orgName: 'org',
    teamName: 'team',
    planCode: 'pro',
    status: 'active',
    machineSlots: { active: 1, max: 3, machines: [] },
    repoLicenseIssuances: {},
    repoLicenses: { recent: [] },
  });
});

describe('subscription verbs (J20)', () => {
  it('control: status without -m is the account view and starts no job', async () => {
    await executeSubscriptionStatus();
    expect(m.execute).not.toHaveBeenCalled();
    expect(m.print).toHaveBeenCalledOnce();
  });

  it('the two machine verbs are planned for J20 and not yet converted', () => {
    for (const verb of ['subscription status', 'subscription refresh']) {
      expect(JOB_PLANS[verb].box, verb).toBe('J20');
      expect(CONVERTED.has(verb), verb).toBe(false);
    }
  });
});
