/**
 * PLAN-detached-jobs J20: the subscription verbs.
 *
 * `subscription status` without `-m` is the account view and starts no job: it asks the account server and prints, so no
 * machine is involved. `subscription status -m` is one `license-status` job and `subscription refresh -m` one
 * `license-scan` job, each with the rest of the verb (the activation section and the license table, or the account call
 * and the license writes) as its ticket step. `vscode serve status` and `vscode serve stop` stay JOB_EXCEPTIONS: their
 * script runs as the repo user and a job is a root unit (J0b finding 9). The executor is a recording fake behind the
 * runCommandJob seam.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { installJobDeps } from './job-deps.js';

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
  refreshIdentity: vi.fn(),
  resolveRepoRef: vi.fn(),
  info: vi.fn(),
  setExitCode: vi.fn(),
  jobs: [] as Record<string, unknown>[],
  jobAnswer: {} as Record<string, unknown>,
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
  refreshRepoLicenseIdentity: m.refreshIdentity,
  refreshRepoLicensesBatch: m.refreshBatch,
}));
vi.mock('../../utils/repo-target.js', () => ({ resolveRepoRef: m.resolveRepoRef }));
vi.mock('../../utils/repo-executor.js', () => ({
  recordedDatastoreMount: () => Promise.resolve(undefined),
}));
vi.mock('../../utils/spinner.js', () => ({
  withSpinner: (_label: string, fn: () => Promise<unknown>) => fn(),
}));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getRepository: vi.fn().mockResolvedValue({ repositoryGuid: 'guid-1' }),
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
  outputService: { info: m.info, success: vi.fn(), warn: vi.fn(), error: vi.fn(), print: m.print },
}));
vi.mock('../../services/core/request-context.js', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  setExitCode: m.setExitCode,
}));
vi.mock('../../utils/errors.js', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  getOutputFormat: () => 'json',
}));

const {
  executeSubscriptionStatus,
  executeMachineStatus,
  executeMachineRefresh,
  executeRepoLicenseRefresh,
} = await import('../subscription-actions.js');
const { JOB_PLANS, CONVERTED, JOB_EXCEPTIONS } = await import('../../services/jobs/plans.js');

let restoreJobDeps: () => void;
const OK = { success: true, exitCode: 0, durationMs: 1, state: 'succeeded' as const };

beforeEach(() => {
  vi.clearAllMocks();
  m.jobs.length = 0;
  m.jobAnswer = { ...OK, stdout: '[]' };
  restoreJobDeps = installJobDeps((options) => {
    m.jobs.push(options as unknown as Record<string, unknown>);
    return Promise.resolve(m.jobAnswer as never);
  });
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

afterEach(() => {
  restoreJobDeps();
});

describe('subscription verbs (J20)', () => {
  it('control: status without -m is the account view and starts no job', async () => {
    await executeSubscriptionStatus();
    expect(m.execute).not.toHaveBeenCalled();
    expect(m.print).toHaveBeenCalledOnce();
  });

  it('status -m makes one license-status job and renders the table in its step', async () => {
    m.readActivation.mockResolvedValue(null);
    m.jobAnswer = {
      ...OK,
      stdout: JSON.stringify([{ repositoryGuid: 'guid-1', status: 'valid' }]),
    };

    await executeMachineStatus('m1');

    expect(m.jobs).toHaveLength(1);
    expect(m.jobs[0]).toMatchObject({
      functionName: 'license-status',
      machineName: 'm1',
      commandKind: { name: 'license-status' },
      jobSteps: [{ name: 'renderSubscriptionStatus', on: 'success' }],
    });
    expect(m.info).toHaveBeenCalledWith(
      expect.stringContaining('commands.subscription.repo.status.entry')
    );
  });

  it('status -m control: a job still running renders nothing and sets its exit code', async () => {
    m.jobAnswer = { ...OK, state: 'running' };

    await executeMachineStatus('m1');

    expect(m.jobs).toHaveLength(1);
    expect(m.info).not.toHaveBeenCalled();
    expect(m.readActivation).not.toHaveBeenCalled();
  });

  it('status -m throws the job failure and renders nothing', async () => {
    m.jobAnswer = { ...OK, success: false, exitCode: 2, state: 'failed', stderr: 'no datastore' };

    await expect(executeMachineStatus('m1')).rejects.toThrow(
      'renet license-status failed on m1 (exit 2): no datastore'
    );
    expect(m.info).not.toHaveBeenCalled();
  });

  it('refresh -m makes one license-scan job and hands its output to the batch in the step', async () => {
    const scan = [{ repositoryGuid: 'guid-1' }];
    m.jobAnswer = { ...OK, stdout: JSON.stringify(scan) };
    m.refreshBatch.mockResolvedValue({
      scanned: 1,
      issued: 0,
      refreshed: 1,
      unchanged: 0,
      failed: 0,
      valid: 1,
      invalidSignatureDetected: 0,
      failures: [],
      recoveryFailureMode: 'none',
    });

    await executeMachineRefresh('m1');

    expect(m.jobs).toHaveLength(1);
    expect(m.jobs[0]).toMatchObject({
      functionName: 'license-scan',
      machineName: 'm1',
      commandKind: { name: 'license-scan' },
      jobSteps: [{ name: 'renderSubscriptionRefresh', on: 'success' }],
    });
    expect(m.refreshBatch).toHaveBeenCalledTimes(1);
    expect(m.refreshBatch.mock.calls[0][5]).toBeUndefined();
    expect(m.refreshBatch.mock.calls[0][6]).toEqual(scan);
  });

  it('refresh -m control: a job still running issues nothing', async () => {
    m.jobAnswer = { ...OK, state: 'running' };

    await executeMachineRefresh('m1');

    expect(m.jobs).toHaveLength(1);
    expect(m.refreshBatch).not.toHaveBeenCalled();
  });

  it('refresh --repo reads and writes the machine only through executor jobs, never a client SSH command', async () => {
    const machineLicense = await vi.importActual<
      typeof import('../../services/account/license-machine.js')
    >('../../services/account/license-machine.js');
    m.resolveRepoRef.mockResolvedValue({ repoKey: 'shop:test', machineName: 'm1' });
    m.execute.mockResolvedValue({ ...OK, stdout: '[{"repositoryGuid":"guid-1"}]' });
    m.refreshIdentity.mockImplementation(async (machineName: string) => {
      await machineLicense.scanRemoteRepoLicenses(machineName, 'rediacc');
      await machineLicense.writeRepoLicense(machineName, 'guid-1', { publicKeyId: 'a'.repeat(16) });
      return true;
    });

    await executeRepoLicenseRefresh('shop:test');

    expect(m.resolveRepoRef).toHaveBeenCalledWith('shop:test', { readOnly: true });
    expect(
      m.execute.mock.calls.map(([options]) => [options.functionName, options.machineName])
    ).toEqual([
      ['license-scan', 'm1'],
      ['license-write', 'm1'],
    ]);
    // Each is a probe whose answer the verb needs now, so no ticket is handed back in its place.
    expect(m.execute.mock.calls.every(([options]) => options.probe === true)).toBe(true);
    expect(m.jobs).toHaveLength(0);
  });

  it('the two machine verbs are converted, and the two vscode serve verbs stay exceptions with their reason', () => {
    for (const verb of ['subscription status', 'subscription refresh']) {
      expect(JOB_PLANS[verb].box, verb).toBe('J20');
      expect(CONVERTED.has(verb), verb).toBe(true);
    }
    for (const verb of ['vscode serve status', 'vscode serve stop']) {
      expect(JOB_EXCEPTIONS[verb], verb).toContain('repo user');
      expect(CONVERTED.has(verb), verb).toBe(false);
    }
  });
});
