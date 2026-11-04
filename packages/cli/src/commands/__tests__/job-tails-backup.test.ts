/**
 * PLAN-detached-jobs J4, the successor class: `repo pull --up` runs `backup_pull` as its one job and carries the deploy
 * as the `pullDeploy` step. Under `--background` the command returns at the job start with the step on the ticket and
 * no `repository_up` started; followed, the step starts that job once; a failed pull starts none.
 */
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { Command } from 'commander';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));

const mockGetRepository = vi.hoisted(() => vi.fn());
vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getCurrent: vi.fn().mockResolvedValue({ resources: { repositories: { app: {} } } }),
    getRepository: mockGetRepository,
    getRepositoryKey: (ref: string) => Promise.resolve(ref),
    getRepositoryMachine: vi.fn().mockResolvedValue('m1'),
  },
}));
vi.mock('../../services/account/subscription-auth.js', () => ({
  getSubscriptionTokenState: () => ({ kind: 'ready' }),
}));
vi.mock('../../utils/repo-target.js', () => ({
  resolveRepoRef: () =>
    Promise.resolve({ name: 'app', repoKey: 'app', machineName: 'm1', tag: 'latest' }),
  resolveRepoRefLocal: () =>
    Promise.resolve({ name: 'app', repoKey: 'app', machineName: 'm1', tag: 'latest' }),
}));
vi.mock('../../utils/repo-executor.js', () => ({
  recordedDatastoreMount: vi.fn().mockResolvedValue(undefined),
}));
vi.mock('../../utils/command-policy.js', () => ({
  assertCommandPolicy: vi.fn().mockResolvedValue(undefined),
  CMD: new Proxy({}, { get: (_t, p) => String(p) }),
}));
vi.mock('../../services/repo/repo-key-deployment.js', () => ({
  deployRepoKeyIfNeeded: vi.fn().mockResolvedValue(undefined),
  removeRepoKeyIfDeployed: vi.fn().mockResolvedValue(undefined),
}));
vi.mock('../../utils/local-execution-failures.js', () => ({
  renderLocalExecutionFailure: vi.fn(),
}));
vi.mock('../../services/core/output.js', () => ({
  outputService: {
    info: vi.fn(),
    success: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
    print: vi.fn(),
    setTimelineRendered: vi.fn(),
    getCommandName: () => undefined,
  },
}));

const { setCommandJobDeps } = await import('../../services/jobs/command-job.js');
const { TicketStore } = await import('../../services/jobs/ticket-store.js');
const executorFactory = await import('../../services/executor/executor-factory.js');
const { registerRepoBackupCommands } = await import('../repo-backup.js');

type Executed = Record<string, unknown> & { functionName: string; jobSteps?: { name: string }[] };

const FINISHED = {
  success: true,
  exitCode: 0,
  durationMs: 5,
  state: 'succeeded' as const,
  jobId: 'job-1',
  attached: true,
  stdout: '',
};
const BACKGROUND = {
  ...FINISHED,
  durationMs: 0,
  state: 'running' as const,
  attached: false,
};
const FAILED = { ...FINISHED, success: false, exitCode: 1, state: 'failed' as const };

let dir: string;
let store: InstanceType<typeof TicketStore>;
let jobCalls: Executed[];
let upCalls: Executed[];
let answer: Record<string, unknown>;

beforeEach(() => {
  vi.clearAllMocks();
  dir = mkdtempSync(join(tmpdir(), 'job-tails-backup-'));
  store = new TicketStore('test', dir);
  jobCalls = [];
  upCalls = [];
  answer = FINISHED;
  mockGetRepository.mockResolvedValue({ repositoryGuid: 'g-app', networkId: 7, credential: 'c' });
  setCommandJobDeps({
    executor: () => ({
      execute: (options) => {
        jobCalls.push(options as unknown as Executed);
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
  // The deploy leg is a plain executor call made by the step, outside the job seam.
  vi.spyOn(executorFactory, 'getExecutor').mockReturnValue({
    execute: (options) => {
      upCalls.push(options as unknown as Executed);
      return Promise.resolve(FINISHED as never);
    },
  });
});

afterEach(() => {
  setCommandJobDeps();
  vi.restoreAllMocks();
  rmSync(dir, { recursive: true, force: true });
  process.exitCode = 0;
});

async function runPull(extra: string[]): Promise<void> {
  const program = new Command();
  program.exitOverride();
  registerRepoBackupCommands(program.command('repo'));
  await program.parseAsync([
    'node',
    'rdc',
    'repo',
    'pull',
    'app',
    '--from-machine',
    'm2',
    ...extra,
  ]);
}

describe('repo pull --up (a successor step: pullDeploy)', () => {
  it('under --background returns at the pull start, with the deploy on the ticket and not started', async () => {
    answer = BACKGROUND;
    await runPull(['--up']);

    expect(jobCalls.map((o) => o.functionName)).toEqual(['backup_pull']);
    expect(jobCalls[0].jobSteps?.map((s) => s.name)).toEqual(['pullDeploy']);
    expect(upCalls).toEqual([]);
    const [ticket] = store.tickets();
    expect(ticket.steps.map((s) => s.name)).toEqual(['pullDeploy']);
    expect(ticket.stepsDone).toEqual([]);
  });

  it('control: followed, the deploy starts exactly one repository_up with the mount', async () => {
    await runPull(['--up']);

    expect(jobCalls.map((o) => o.functionName)).toEqual(['backup_pull']);
    expect(upCalls.map((o) => o.functionName)).toEqual(['repository_up']);
    expect(upCalls[0].params).toMatchObject({ repository: 'app', mount: true });
    expect(store.tickets()[0].stepsDone).toEqual(['pullDeploy']);
  });

  it('a failed pull starts no deploy', async () => {
    answer = FAILED;
    await runPull(['--up']);

    // The pull was dispatched with the deploy planned, so the empty upCalls is the failure's doing and not an early exit.
    expect(jobCalls.map((o) => o.functionName)).toEqual(['backup_pull']);
    expect(jobCalls[0].jobSteps?.map((s) => s.name)).toEqual(['pullDeploy']);
    expect(upCalls).toEqual([]);
  });

  it('control: without --up the pull plans no step', async () => {
    await runPull([]);

    expect(jobCalls[0].jobSteps ?? []).toEqual([]);
    expect(upCalls).toEqual([]);
  });
});
