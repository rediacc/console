/**
 * PLAN-detached-jobs J4: each converted verb runs its main call as one job and carries its follow-up code as ticket
 * steps. Under `--background` the command returns at the job start with the steps recorded on the ticket and nothing
 * run; followed, the same steps run in-process exactly once.
 *
 * The executor is a recording fake behind the runCommandJob seam, the ticket store is real (in a temp directory), and
 * the step claim is a stub that grants every claim, so what is asserted is the command's own plan and the runner's
 * once-only behaviour, not SSH.
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
const mockAddRepository = vi.hoisted(() => vi.fn());
vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getCurrent: vi.fn().mockResolvedValue({ resources: { repositories: { app: {} } } }),
    getRepository: mockGetRepository,
    getRepositoryKey: (ref: string) => Promise.resolve(ref),
    addRepository: mockAddRepository,
    removeRepository: vi.fn().mockResolvedValue(undefined),
  },
}));
vi.mock('../../services/config/network-id-discovery.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../services/config/network-id-discovery.js')>()),
  ensureRepositoryNetworkId: vi.fn().mockResolvedValue(undefined),
}));
vi.mock('../../utils/repo-target.js', () => ({
  resolveRepoRef: () =>
    Promise.resolve({ name: 'app', repoKey: 'app', machineName: 'm1', tag: 'latest' }),
  resolveRepoRefLocal: () =>
    Promise.resolve({ name: 'app', repoKey: 'app', machineName: 'm1', tag: 'latest' }),
}));
vi.mock('../../utils/command-policy.js', () => ({
  assertCommandPolicy: vi.fn().mockResolvedValue(undefined),
  CMD: new Proxy({}, { get: (_t, p) => String(p) }),
}));
vi.mock('../../services/repo/repo-key-deployment.js', () => ({
  deployRepoKeyIfNeeded: vi.fn().mockResolvedValue(undefined),
  removeRepoKeyIfDeployed: vi.fn().mockResolvedValue(undefined),
}));
const mockPostRepoUpTasks = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));
vi.mock('../repo-batch-utils.js', () => ({
  postRepoUpTasks: mockPostRepoUpTasks,
  handleDownAll: vi.fn(),
  handleRepoList: vi.fn(),
  handleUpAll: vi.fn(),
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
vi.mock('../../utils/errors.js', async () => {
  const actual =
    await vi.importActual<typeof import('../../utils/errors.js')>('../../utils/errors.js');
  return {
    ...actual,
    getOutputFormat: () => 'table',
    handleError: (e: unknown) => {
      throw e;
    },
  };
});

const { setCommandJobDeps, runCommandJob } = await import('../../services/jobs/command-job.js');
const { TicketStore } = await import('../../services/jobs/ticket-store.js');
const { planStep, bindStepHandler } = await import('../../services/jobs/steps.js');
const { registerRepoBranchingCommands } = await import('../repo-branching.js');
const { registerRepoCommands } = await import('../repo.js');

type Executed = Record<string, unknown> & { functionName: string; jobSteps?: { name: string }[] };

const BACKGROUND = {
  success: true,
  exitCode: 0,
  durationMs: 0,
  state: 'running' as const,
  jobId: 'job-1',
  attached: false,
};
const FINISHED = {
  success: true,
  exitCode: 0,
  durationMs: 5,
  state: 'succeeded' as const,
  jobId: 'job-1',
  attached: true,
  stdout: '',
};
const FAILED = { ...FINISHED, success: false, exitCode: 1, state: 'failed' as const };

let dir: string;
let store: InstanceType<typeof TicketStore>;
let executed: Executed[];
let answer: Record<string, unknown>;
let claims: string[][];

beforeEach(() => {
  vi.clearAllMocks();
  dir = mkdtempSync(join(tmpdir(), 'job-tails-'));
  store = new TicketStore('test', dir);
  executed = [];
  claims = [];
  answer = FINISHED;
  mockGetRepository.mockResolvedValue({ repositoryGuid: 'g-app', networkId: 7, credential: 'c' });
  setCommandJobDeps({
    executor: () => ({
      execute: (options) => {
        executed.push(options as Executed);
        return Promise.resolve(answer as never);
      },
    }),
    store: () => store,
    stepDeps: () =>
      Promise.resolve({
        observer: { configName: 'test' },
        warn: () => undefined,
        claim: ({ steps, done }) => {
          if (!done) claims.push(steps);
          return Promise.resolve(steps.map((name) => ({ name, result: 'claimed' as const })));
        },
      }),
  });
});

afterEach(() => {
  setCommandJobDeps();
  rmSync(dir, { recursive: true, force: true });
  process.exitCode = 0;
});

async function run(register: (repo: Command) => void, argv: string[]): Promise<void> {
  const program = new Command();
  program.exitOverride();
  register(program.command('repo'));
  await program.parseAsync(['node', 'rdc', 'repo', ...argv]);
}

function onlyTicket() {
  const tickets = store.tickets();
  expect(tickets).toHaveLength(1);
  return tickets[0];
}

async function runRepo(argv: string[]): Promise<void> {
  const program = new Command();
  program.exitOverride();
  registerRepoCommands(program);
  await program.parseAsync(['node', 'rdc', 'repo', ...argv]);
}

describe('repo up (a success step: postRepoUpTasks)', () => {
  it('under --background returns at the job start, with the step on the ticket and not run', async () => {
    answer = BACKGROUND;
    await runRepo(['up', 'app']);

    expect(executed.map((o) => o.functionName)).toEqual(['repository_up']);
    expect(executed[0].jobSteps?.map((s) => s.name)).toEqual(['postRepoUpTasks']);
    expect(mockPostRepoUpTasks).not.toHaveBeenCalled();
    const ticket = onlyTicket();
    expect(ticket.jobId).toBe('job-1');
    expect(ticket.state).not.toBe('succeeded');
    expect(ticket.steps.map((s) => s.name)).toEqual(['postRepoUpTasks']);
    expect(ticket.stepsDone).toEqual([]);
  });

  it('control: followed, the step runs in-process exactly once and the ticket is settled', async () => {
    await runRepo(['up', 'app']);

    expect(mockPostRepoUpTasks).toHaveBeenCalledExactlyOnceWith('app', 'm1');
    expect(claims).toEqual([['postRepoUpTasks']]);
    const ticket = onlyTicket();
    expect(ticket.stepsDone).toEqual(['postRepoUpTasks']);
    expect(ticket.acknowledged).toBe(true);
  });

  it('a failed up runs no success step (repo up used to run postRepoUpTasks after a failed up)', async () => {
    answer = FAILED;
    await runRepo(['up', 'app']);

    expect(mockPostRepoUpTasks).not.toHaveBeenCalled();
    expect(onlyTicket().state).toBe('failed');
  });
});

describe('repo commit (a finalizer: recordRepoCommit)', () => {
  it('under --background records nothing in the config until the commit exists', async () => {
    answer = BACKGROUND;
    await run(registerRepoBranchingCommands, ['commit', 'app', '--message', 'snap']);

    expect(executed.map((o) => o.functionName)).toEqual(['repository_commit']);
    expect(mockAddRepository).not.toHaveBeenCalled();
    expect(onlyTicket().steps.map((s) => s.name)).toEqual(['recordRepoCommit']);
  });

  it('control: followed, the commit object and the working tip are recorded once', async () => {
    await run(registerRepoBranchingCommands, ['commit', 'app', '--message', 'snap']);

    const commitGuid = (executed[0].params as { tag: string }).tag;
    expect(mockAddRepository).toHaveBeenCalledTimes(2);
    expect(mockAddRepository).toHaveBeenNthCalledWith(
      1,
      commitGuid,
      expect.objectContaining({ immutable: true, commitMessage: 'snap', parentGuid: 'g-app' })
    );
    expect(mockAddRepository).toHaveBeenNthCalledWith(
      2,
      'app',
      expect.objectContaining({ headCommit: commitGuid })
    );
  });
});

describe('runCommandJob (a successor step and the refusal path)', () => {
  it('a successor runs only once its job succeeded, and never on a failure', async () => {
    const successor = vi.fn().mockResolvedValue(undefined);
    bindStepHandler('pullDeploy', successor);
    const steps = [planStep('pullDeploy', { repo: 'app' })];

    answer = FAILED;
    await runCommandJob('repo pull', { functionName: 'backup_pull', machineName: 'm1' }, steps);
    expect(successor).not.toHaveBeenCalled();

    answer = FINISHED;
    await runCommandJob('repo pull', { functionName: 'backup_pull', machineName: 'm1' }, steps);
    expect(successor).toHaveBeenCalledTimes(1);
    expect(successor.mock.calls[0][0]).toMatchObject({ machine: 'm1', params: { repo: 'app' } });
  });

  it('passes the failure state, exit code and markers to a failure step', async () => {
    const failed = vi.fn().mockResolvedValue(undefined);
    bindStepHandler('rollbackFork', failed);
    answer = { ...FAILED, exitCode: 16, steps: [{ name: 'cow_reflink', duration_ms: 3 }] };

    await runCommandJob('repo fork', { functionName: 'repository_fork', machineName: 'm1' }, [
      planStep('rollbackFork', { repo: 'app:t', guid: 'g' }),
    ]);

    expect(failed.mock.calls[0][0]).toMatchObject({
      state: 'failed',
      exitCode: 16,
      markers: ['cow_reflink'],
    });
  });

  it('a call that ran outside a job still runs its steps once, with no claim', async () => {
    const step = vi.fn().mockResolvedValue(undefined);
    bindStepHandler('pullDeploy', step);
    answer = { success: true, exitCode: 0, durationMs: 1 };

    await runCommandJob('repo pull', { functionName: 'backup_pull', machineName: 'm1' }, [
      planStep('pullDeploy', { repo: 'app' }),
    ]);

    expect(step).toHaveBeenCalledTimes(1);
    expect(claims).toEqual([]);
    expect(onlyTicket().stepsDone).toEqual(['pullDeploy']);
  });

  it('a refused start leaves an acknowledged ticket and rethrows', async () => {
    setCommandJobDeps({
      executor: () => ({ execute: () => Promise.reject(new Error('overlap refused')) }),
      store: () => store,
      stepDeps: () =>
        Promise.resolve({
          observer: { configName: 'test' },
          warn: () => undefined,
          claim: () => Promise.resolve([]),
        }),
    });

    await expect(
      runCommandJob('repo up', { functionName: 'repository_up', machineName: 'm1' }, [])
    ).rejects.toThrow('overlap refused');
    expect(onlyTicket().acknowledged).toBe(true);
  });
});
