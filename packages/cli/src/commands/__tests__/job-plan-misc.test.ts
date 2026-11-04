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
  readActivation: vi.fn(),
  refreshBatch: vi.fn(),
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
  readMachineActivationStatus: m.readActivation,
  readRuntimeRepoLicenseStatuses: vi.fn().mockResolvedValue([]),
  refreshRepoLicenseIdentity: vi.fn(),
  refreshRepoLicensesBatch: m.refreshBatch,
}));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getTeam: vi.fn().mockResolvedValue('team'),
    getLocalConfig: vi.fn().mockResolvedValue({ sshPrivateKey: 'key', ssh: {} }),
    getLocalMachine: vi.fn().mockResolvedValue({ ip: '10.0.0.1', user: 'root' }),
    listRepositories: vi.fn().mockResolvedValue([]),
  },
}));
vi.mock('../../services/renet/renet-execution.js', () => ({
  acquireRemoteRenet: vi.fn().mockResolvedValue({ remotePath: '/usr/bin/renet' }),
  readSSHKey: vi.fn(),
}));
vi.mock('../../services/core/output.js', () => ({
  outputService: { info: vi.fn(), success: vi.fn(), warn: vi.fn(), error: vi.fn(), print: m.print },
}));
vi.mock('../../utils/errors.js', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  getOutputFormat: () => 'json',
}));

const { executeSubscriptionStatus, executeMachineStatus, executeMachineRefresh } = await import(
  '../subscription-actions.js'
);
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

  it('runs the two machine verbs without starting a job', async () => {
    m.refreshBatch.mockResolvedValue({
      scanned: 0,
      issued: 0,
      refreshed: 0,
      unchanged: 0,
      failed: 0,
      valid: 0,
      invalidSignatureDetected: 0,
      failures: [],
      recoveryFailureMode: 'none',
    });
    await executeMachineStatus('m1');
    await executeMachineRefresh('m1');
    // Both verbs reached their SFTP reads: the verbs ran, they did not stop early.
    expect(m.readActivation).toHaveBeenCalled();
    expect(m.refreshBatch).toHaveBeenCalled();
    expect(m.execute).not.toHaveBeenCalled();
  });

  it('the two machine verbs are planned for J20 and not yet converted', () => {
    for (const verb of ['subscription status', 'subscription refresh']) {
      expect(JOB_PLANS[verb].box, verb).toBe('J20');
      expect(CONVERTED.has(verb), verb).toBe(false);
    }
  });
});
