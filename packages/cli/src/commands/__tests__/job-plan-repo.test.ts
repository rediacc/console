/**
 * PLAN-detached-jobs J16: a converted repo verb is one machine job whose client-side follow-up rides the ticket as
 * steps. `repo create` is the first row: under `--background` the job's start returns the ticket at once with the plan
 * recorded, and the finished job's `identityRefresh` step later refreshes the licence identity with the size the repo
 * was created with (review cac18e21.2). The executor is a recording fake behind the runCommandJob seam, the ticket
 * store is real in a temp directory, and the step claim grants every claim, so the test sees the command's own plan.
 */
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));

const mockAddRepository = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));
const mockRemoveRepository = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getCurrent: vi.fn().mockResolvedValue({ resources: { machines: {}, datastores: {} } }),
    getRepository: vi.fn().mockResolvedValue(undefined),
    getRepositoryKey: (ref: string) => Promise.resolve(`${ref}:latest`),
    allocateNetworkId: vi.fn(),
    addRepository: mockAddRepository,
    removeRepository: mockRemoveRepository,
  },
}));
const mockRefreshIdentity = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));
vi.mock('../../services/executor/local-executor.js', () => ({
  localExecutorService: { refreshIdentityFor: mockRefreshIdentity },
}));
const mockReconcile = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));
vi.mock('../../services/backup/repo-change-hook.js', () => ({
  reconcileBackupSchedules: mockReconcile,
}));
vi.mock('../../services/executor/executor-factory.js', () => ({
  getExecutor: () => ({ execute: () => Promise.reject(new Error('the executor is replaced')) }),
  requestNetworkIdAuto: vi.fn(),
}));
vi.mock('../../services/core/output.js', () => ({
  outputService: {
    info: vi.fn(),
    success: vi.fn(),
    warn: vi.fn(),
    setTimelineRendered: vi.fn(),
  },
}));
vi.mock('../../utils/agent-guard.js', () => ({ assertAgentRepoCreate: vi.fn() }));
vi.mock('../_validate.js', () => ({ assertMachineExists: vi.fn().mockResolvedValue(undefined) }));
vi.mock('../../utils/ssh-keygen.js', () => ({
  generateSSHKeyPair: () => ({ privateKey: 'priv', publicKey: 'pub' }),
}));
vi.mock('../../utils/local-execution-failures.js', () => ({
  renderLocalExecutionFailure: vi.fn(),
}));
vi.mock('../../utils/errors.js', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  handleError: (e: unknown) => {
    throw e;
  },
}));

const { configService } = await import('../../services/config/config-resources.js');
const { setCommandJobDeps } = await import('../../services/jobs/command-job.js');
const { TicketStore } = await import('../../services/jobs/ticket-store.js');
const { resolveStepHandler } = await import('../../services/jobs/steps.js');
const { handleRepoCreate } = await import('../repo-create-delete.js');

type Executed = {
  functionName: string;
  deferIdentityRefresh?: boolean;
  jobSteps?: { name: string; on: string; params: Record<string, unknown> }[];
};

const BACKGROUND = {
  success: true,
  exitCode: 0,
  durationMs: 0,
  state: 'running' as const,
  jobId: 'job-1',
  attached: false,
};
const FINISHED = { ...BACKGROUND, durationMs: 5, state: 'succeeded' as const, attached: true };
const FAILED = { ...FINISHED, success: false, exitCode: 1, state: 'failed' as const };

let dir: string;
let store: InstanceType<typeof TicketStore>;
let executed: Executed[];
let answer: Record<string, unknown>;

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(configService.getRepository).mockResolvedValue(undefined);
  dir = mkdtempSync(join(tmpdir(), 'job-plan-repo-'));
  store = new TicketStore('test', dir);
  executed = [];
  answer = FINISHED;
  setCommandJobDeps({
    executor: () => ({
      execute: (options) => {
        executed.push(options as unknown as Executed);
        return Promise.resolve(answer as never);
      },
    }),
    store: () => store,
    stepDeps: () =>
      Promise.resolve({
        observer: { configName: 'test' },
        warn: () => undefined,
        claim: ({ steps }) =>
          Promise.resolve(steps.map((name) => ({ name, result: 'claimed' as const }))),
      }),
  });
});

afterEach(() => {
  setCommandJobDeps();
  rmSync(dir, { recursive: true, force: true });
  process.exitCode = 0;
});

describe('repo create (one job; rollback, identity refresh and schedules as steps)', () => {
  it('makes one job start for the machine and defers the identity refresh to a step', async () => {
    await handleRepoCreate('shop', { machine: 'm1', size: '5G' });

    expect(executed.map((o) => o.functionName)).toEqual(['repository_create']);
    expect(executed[0].deferIdentityRefresh).toBe(true);
    expect(executed[0].jobSteps?.map((s) => [s.name, s.on])).toEqual([
      ['rollbackCreate', 'failure'],
      ['identityRefresh', 'success'],
      ['reconcileBackupSchedules', 'success'],
    ]);
  });

  it('control: followed, the success steps run once and the rollback does not', async () => {
    await handleRepoCreate('shop', { machine: 'm1', size: '5G' });

    expect(mockRefreshIdentity).toHaveBeenCalledExactlyOnceWith('repository_create', 'm1', {
      repository: 'shop',
      size: '5G',
    });
    expect(mockReconcile).toHaveBeenCalledExactlyOnceWith('m1');
    expect(mockRemoveRepository).not.toHaveBeenCalled();
    expect(store.tickets()[0].acknowledged).toBe(true);
  });

  it('a failed job rolls the registration back and refreshes nothing', async () => {
    answer = FAILED;
    // Absent until the create registers it, then the registered record: the rollback step removes it by GUID.
    vi.mocked(configService.getRepository).mockImplementation(() => {
      const added = mockAddRepository.mock.calls[0]?.[1] as { repositoryGuid: string } | undefined;
      return Promise.resolve(
        added ? ({ repositoryGuid: added.repositoryGuid } as never) : undefined
      );
    });
    await handleRepoCreate('shop', { machine: 'm1', size: '5G' });

    expect(mockRemoveRepository).toHaveBeenCalledExactlyOnceWith('shop');
    expect(mockRefreshIdentity).not.toHaveBeenCalled();
    expect(mockReconcile).not.toHaveBeenCalled();
  });

  it('under --background the ticket carries the plan, and the finished job refreshes the identity with its size', async () => {
    answer = BACKGROUND;
    await handleRepoCreate('shop', { machine: 'm1', size: '5G' });

    expect(mockRefreshIdentity).not.toHaveBeenCalled();
    expect(mockReconcile).not.toHaveBeenCalled();
    const ticket = store.tickets()[0];
    expect(ticket.steps.map((s) => s.name)).toEqual([
      'rollbackCreate',
      'identityRefresh',
      'reconcileBackupSchedules',
    ]);
    expect(ticket.stepsDone).toEqual([]);

    // The observer that sees the job finish runs the step from the ticket's recorded params.
    const refresh = ticket.steps.find((s) => s.name === 'identityRefresh');
    const handler = await resolveStepHandler('identityRefresh');
    await handler({
      jobId: ticket.jobId ?? 'job-1',
      machine: ticket.machine ?? 'm1',
      params: refresh?.params ?? {},
      state: 'succeeded',
    });
    expect(mockRefreshIdentity).toHaveBeenCalledExactlyOnceWith('repository_create', 'm1', {
      repository: 'shop',
      size: '5G',
    });
  });
});
