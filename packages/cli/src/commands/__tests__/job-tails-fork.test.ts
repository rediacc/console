/**
 * PLAN-detached-jobs J4 and J16: `repo fork` and `repo checkout` run `repository_fork` as one job. Under `--background`
 * the command returns at the job start with the steps recorded on the ticket and none run (the compound class: `--up`
 * is part of that one job; the successor class: `--checkpoint --up` plans the `forkUp` step; the finalizer class: the
 * `rollbackFork` failure step). Followed, the same steps run in-process exactly once. `repo checkout` is the same job
 * with the `advanceHeadCommit` step added.
 *
 * The executor is a recording fake behind the runCommandJob seam, the ticket store is real (in a temp directory), and
 * the step claim grants every claim, so what is asserted is the command's own plan and the runner's once-only
 * behaviour, not SSH.
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

const PARENT = {
  repositoryGuid: 'g-app',
  tag: 'latest',
  credential: 'c',
  networkId: 7,
  branches: { main: 'g-commit' },
};
const COMMIT = { repositoryGuid: 'g-commit', immutable: true, networkId: 7, credential: 'c' };

const mockGetRepository = vi.hoisted(() => vi.fn());
const mockAddRepository = vi.hoisted(() => vi.fn());
const mockRemoveRepository = vi.hoisted(() => vi.fn());
vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getCurrent: vi.fn().mockResolvedValue({ resources: { repositories: { app: {} } } }),
    getRepository: mockGetRepository,
    getRepositoryKey: (ref: string) => Promise.resolve(ref),
    addRepository: mockAddRepository,
    allocateNetworkId: vi.fn().mockResolvedValue(99),
    removeRepository: mockRemoveRepository,
    getLocalMachine: vi.fn().mockResolvedValue({ ip: '127.0.0.1', user: 'root' }),
  },
}));
vi.mock('../../services/config/network-id-discovery.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../services/config/network-id-discovery.js')>()),
  targetFloor: vi.fn().mockResolvedValue([]),
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
vi.mock('../../services/machine/machine-connection.js', () => ({
  machineConnections: { acquire: vi.fn().mockResolvedValue({ release: vi.fn() }) },
}));
const mockRemoveRepoKey = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));
vi.mock('../../services/repo/repo-key-deployment.js', () => ({
  deployRepoKeyIfNeeded: vi.fn().mockResolvedValue(undefined),
  removeRepoKeyIfDeployed: mockRemoveRepoKey,
}));
const mockPostRepoUpTasks = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));
vi.mock('../repo-batch-utils.js', () => ({
  postRepoUpTasks: mockPostRepoUpTasks,
  ensureDns: vi.fn().mockResolvedValue('example.com'),
}));
const mockRefreshIdentityFor = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));
vi.mock('../../services/executor/local-executor.js', () => ({
  localExecutorService: { execute: vi.fn(), refreshIdentityFor: mockRefreshIdentityFor },
}));
const mockReconcile = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));
vi.mock('../../services/backup/repo-change-hook.js', () => ({
  reconcileBackupSchedules: mockReconcile,
}));
vi.mock('../../utils/ssh-keygen.js', () => ({
  generateSSHKeyPair: () => ({ privateKey: 'priv', publicKey: 'pub' }),
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

const { setCommandJobDeps } = await import('../../services/jobs/command-job.js');
const { TicketStore } = await import('../../services/jobs/ticket-store.js');
const executorFactory = await import('../../services/executor/executor-factory.js');
const outputModule = await import('../../services/core/output.js');
const { registerRepoForkCommand } = await import('../repo-fork.js');
const { registerRepoBranchingCommands } = await import('../repo-branching.js');

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
const BACKGROUND = { ...FINISHED, durationMs: 0, state: 'running' as const, attached: false };
const FAILED = { ...FINISHED, success: false, exitCode: 1, state: 'failed' as const };

let dir: string;
let store: InstanceType<typeof TicketStore>;
let jobCalls: Executed[];
let upCalls: Executed[];
let answer: Record<string, unknown>;
/** What addRepository wrote, as the config would read it back. */
let registered: Map<string, Record<string, unknown>>;

beforeEach(() => {
  vi.clearAllMocks();
  dir = mkdtempSync(join(tmpdir(), 'job-tails-fork-'));
  store = new TicketStore('test', dir);
  jobCalls = [];
  upCalls = [];
  answer = FINISHED;
  registered = new Map();
  mockAddRepository.mockImplementation((key: string, value: Record<string, unknown>) => {
    registered.set(key, value);
    return Promise.resolve();
  });
  mockGetRepository.mockImplementation((ref: string) => {
    if (ref === 'app') return Promise.resolve(PARENT);
    if (ref === 'g-commit') return Promise.resolve(COMMIT);
    return Promise.resolve(registered.get(ref));
  });
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
  // The successor's up leg is a plain executor call made by the step, outside the job seam.
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

async function runFork(argv: string[]): Promise<void> {
  const program = new Command();
  program.exitOverride();
  registerRepoForkCommand(program.command('repo'));
  await program.parseAsync(['node', 'rdc', 'repo', 'fork', 'app', ...argv]);
}

async function runCheckout(argv: string[]): Promise<void> {
  const program = new Command();
  program.exitOverride();
  registerRepoBranchingCommands(program.command('repo'));
  await program.parseAsync(['node', 'rdc', 'repo', 'checkout', 'main', '--from', 'app', ...argv]);
}

function onlyTicket() {
  const tickets = store.tickets();
  expect(tickets).toHaveLength(1);
  return tickets[0];
}

const stepNames = (call: Executed) => call.jobSteps?.map((s) => s.name);

describe('repo fork --up (the compound class: one repository_fork job carries the up)', () => {
  it('under --background returns at the one job start, with the tails on the ticket and not run', async () => {
    answer = BACKGROUND;
    await runFork(['--tag', 'w', '--up']);

    expect(jobCalls.map((o) => o.functionName)).toEqual(['repository_fork']);
    expect(jobCalls[0].params).toMatchObject({ up: true, grand: 'g-app', repo_name: 'app:w' });
    expect(upCalls).toEqual([]);
    expect(stepNames(jobCalls[0])).toEqual([
      'rollbackFork',
      'identityRefresh',
      'postRepoUpTasks',
      'reconcileBackupSchedules',
    ]);
    expect(onlyTicket().steps.map((s) => s.name)).toEqual(stepNames(jobCalls[0]));
    expect(onlyTicket().stepsDone).toEqual([]);
    expect(mockRefreshIdentityFor).not.toHaveBeenCalled();
    expect(mockPostRepoUpTasks).not.toHaveBeenCalled();
    expect(mockReconcile).not.toHaveBeenCalled();
    expect(mockRemoveRepository).not.toHaveBeenCalled();
  });

  it('control: followed, each success tail runs exactly once and no second leg starts', async () => {
    await runFork(['--tag', 'w', '--up']);

    expect(jobCalls.map((o) => o.functionName)).toEqual(['repository_fork']);
    expect(upCalls).toEqual([]);
    expect(mockRefreshIdentityFor).toHaveBeenCalledTimes(1);
    expect(mockPostRepoUpTasks).toHaveBeenCalledTimes(1);
    expect(mockReconcile).toHaveBeenCalledExactlyOnceWith('m1');
    expect(onlyTicket().stepsDone).toEqual([
      'identityRefresh',
      'postRepoUpTasks',
      'reconcileBackupSchedules',
    ]);
  });

  it('a failed fork runs no success tail', async () => {
    answer = FAILED;
    await runFork(['--tag', 'w', '--up']).catch(() => undefined);

    expect(jobCalls).toHaveLength(1);
    expect(mockRefreshIdentityFor).not.toHaveBeenCalled();
    expect(mockPostRepoUpTasks).not.toHaveBeenCalled();
    expect(mockReconcile).not.toHaveBeenCalled();
  });
});

describe('repo fork --checkpoint --up (the successor class: forkUp is a step, not a client second leg)', () => {
  it('under --background plans forkUp on the ticket and starts no repository_up', async () => {
    answer = BACKGROUND;
    await runFork(['--tag', 'w', '--checkpoint', '--up']);

    expect(jobCalls.map((o) => o.functionName)).toEqual(['repository_fork']);
    expect(jobCalls[0].params).toMatchObject({ checkpoint: true });
    expect(jobCalls[0].params).not.toHaveProperty('up');
    expect(stepNames(jobCalls[0])).toEqual([
      'rollbackFork',
      'identityRefresh',
      'forkUp',
      'postRepoUpTasks',
      'reconcileBackupSchedules',
    ]);
    expect(upCalls).toEqual([]);
    expect(onlyTicket().stepsDone).toEqual([]);
  });

  it('control: followed, the successor starts exactly one repository_up for the fork', async () => {
    await runFork(['--tag', 'w', '--checkpoint', '--up']);

    expect(upCalls.map((o) => o.functionName)).toEqual(['repository_up']);
    expect(upCalls[0].params).toMatchObject({ repository: 'app:w', mount: true, grand: 'g-app' });
    expect(onlyTicket().stepsDone).toContain('forkUp');
  });
});

describe('repo fork (the finalizer class: rollbackFork)', () => {
  it('a plain fork under --background registers the fork and plans the rollback and refresh as steps', async () => {
    answer = BACKGROUND;
    await runFork(['--tag', 'w']);

    expect(jobCalls.map((o) => o.functionName)).toEqual(['repository_fork']);
    expect(stepNames(jobCalls[0])).toEqual([
      'rollbackFork',
      'identityRefresh',
      'reconcileBackupSchedules',
    ]);
    expect(mockRemoveRepository).not.toHaveBeenCalled();
  });

  it('a failed fork, with no image marker in the stream, rolls the registration and the key back once', async () => {
    answer = { ...FAILED, steps: [] };
    await runFork(['--tag', 'w']);

    expect(mockAddRepository).toHaveBeenCalledTimes(1);
    expect(mockRemoveRepository).toHaveBeenCalledExactlyOnceWith('app:w');
    expect(mockRemoveRepoKey).toHaveBeenCalledTimes(1);
    expect(onlyTicket().state).toBe('failed');
  });

  it('a failure after the image was made keeps the registration', async () => {
    answer = { ...FAILED, steps: [{ name: 'cow_reflink', duration_ms: 3 }] };
    await runFork(['--tag', 'w']);

    expect(mockRemoveRepository).not.toHaveBeenCalled();
  });
});

describe('repo checkout (one repository_fork job, with advanceHeadCommit as a step)', () => {
  it('under --background returns at the job start; the tip is not recorded until the fork exists', async () => {
    answer = BACKGROUND;
    await runCheckout(['--tag', 'w']);

    expect(jobCalls.map((o) => o.functionName)).toEqual(['repository_fork']);
    expect(jobCalls[0].params).toMatchObject({ repository: 'g-commit' });
    expect(stepNames(jobCalls[0])).toEqual([
      'rollbackFork',
      'identityRefresh',
      'reconcileBackupSchedules',
      'advanceHeadCommit',
    ]);
    const ticket = onlyTicket();
    expect(ticket.steps.map((s) => s.name)).toContain('advanceHeadCommit');
    expect(ticket.stepsDone).toEqual([]);
    // Only the registration of the new fork was written; the tip is not.
    expect(mockAddRepository).toHaveBeenCalledTimes(1);
    expect(mockAddRepository.mock.calls[0][1]).not.toHaveProperty('headCommit');
  });

  it('control: followed, the working tip is recorded once, as the checked-out commit', async () => {
    await runCheckout(['--tag', 'w']);

    const tips = mockAddRepository.mock.calls.filter(
      (c) => (c[1] as { headCommit?: string }).headCommit === 'g-commit'
    );
    expect(tips).toHaveLength(1);
    expect(tips[0][0]).toBe('app:w');
    expect(onlyTicket().stepsDone).toContain('advanceHeadCommit');
  });
});

describe('repo fork --up network-ID retry (a client second leg that does not run while the client is away)', () => {
  const hints = () =>
    vi
      .mocked(outputModule.outputService.info)
      .mock.calls.filter((c) => String(c[0]).includes('not retried'));

  it('under --background names the exact retry command and starts no second up leg', async () => {
    answer = BACKGROUND;
    await runFork(['--tag', 'w', '--up']);

    expect(hints()).toHaveLength(1);
    expect(String(hints()[0][0])).toContain('rdc repo up app:w -m');
    expect(upCalls).toEqual([]);
    expect(mockRemoveRepository).not.toHaveBeenCalled();
  });

  it('control: a fork without --up has no up phase to refuse, so no hint', async () => {
    answer = BACKGROUND;
    await runFork(['--tag', 'w']);

    expect(hints()).toEqual([]);
  });

  it('control: followed, the job finishes and no hint is printed', async () => {
    await runFork(['--tag', 'w', '--up']);

    expect(hints()).toEqual([]);
  });
});
