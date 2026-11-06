/**
 * PLAN-detached-jobs J4, the compound class: `repo migrate` runs `repository_migrate` as its one source job, and the
 * rest (the placement rewrite on the cutover marker, the report, the target up with DNS, the source delete and the
 * backup-unit re-render) is the plan on the ticket. Under `--background` the command returns at the job start with the
 * three steps recorded and no second machine call; followed, the target is brought up once and the source deleted once.
 *
 * The source job is a recording fake behind the runCommandJob seam; the plain executor, which a step's own calls go
 * through, is a second recorder, so a client second leg shows up as a call in it.
 */
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));

const mockGetRepository = vi.hoisted(() => vi.fn());
const mockSetRepositoryPlacement = vi.hoisted(() => vi.fn());
vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getRepository: mockGetRepository,
    getCurrent: vi.fn().mockResolvedValue({
      resources: { repositories: { app: { grand: 'latest', tags: { latest: {} } } } },
    }),
    getLocalConfig: vi.fn().mockResolvedValue({
      machines: { 'src-machine': { ip: '10.0.0.1' }, 'dst-machine': { ip: '10.0.0.2' } },
    }),
    setRepositoryPlacement: mockSetRepositoryPlacement,
  },
}));
vi.mock('../../services/config/network-id-discovery.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../services/config/network-id-discovery.js')>()),
  ensureRepositoryNetworkId: vi.fn().mockResolvedValue(undefined),
}));

const mockPlainExecute = vi.hoisted(() => vi.fn());
vi.mock('../../services/executor/executor-factory.js', () => ({
  getExecutor: () => ({ execute: mockPlainExecute }),
}));
vi.mock('../../services/repo/repo-key-deployment.js', () => ({
  deployRepoKeyIfNeeded: vi.fn().mockResolvedValue(undefined),
}));
vi.mock('../../services/repo-migrate-license.js', () => ({
  ensureTargetRepoLicense: vi.fn().mockResolvedValue(undefined),
}));
const mockReconcile = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));
vi.mock('../../services/backup/repo-change-hook.js', () => ({
  reconcileBackupSchedules: mockReconcile,
}));
const mockPostRepoUpTasks = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));
vi.mock('../repo-batch-utils.js', () => ({ postRepoUpTasks: mockPostRepoUpTasks }));
vi.mock('../repo-list-parser.js', () => ({ parseRepositoryListOutput: () => [] }));
vi.mock('../repo-push-stats.js', () => ({ extractPushResult: () => undefined }));
vi.mock('../repo-backup.js', () => ({
  autoProvisionTarget: vi.fn().mockResolvedValue(undefined),
  buildPushParams: (repo: string, guid: string, type: string, to: string) => ({
    params: { repository: repo, dest: guid, destinationType: type, to },
    dest: guid,
  }),
}));
vi.mock('../../utils/command-policy.js', () => ({
  assertCommandPolicy: vi.fn().mockResolvedValue(undefined),
  CMD: { REPO_PUSH: 'repo push' },
}));
vi.mock('../../utils/remote-resolve.js', () => ({
  resolveRemoteName: (name: string) => Promise.resolve({ type: 'machine', name }),
}));
vi.mock('../../utils/repo-target.js', () => ({
  resolveRepoRef: () =>
    Promise.resolve({ name: 'app', repoKey: 'app', machineName: 'src-machine', tag: 'latest' }),
}));
vi.mock('../../utils/spinner.js', () => ({
  withSpinner: <T>(_label: string, fn: () => Promise<T>) => fn(),
}));
vi.mock('../../services/core/output.js', () => ({
  outputService: { info: vi.fn(), success: vi.fn(), warn: vi.fn() },
}));

const { setCommandJobDeps } = await import('../../services/jobs/command-job.js');
const { TicketStore } = await import('../../services/jobs/ticket-store.js');
const { migrateRepo } = await import('../repo-migrate.js');

type Executed = Record<string, unknown> & { functionName: string; jobSteps?: { name: string }[] };

const MARKER = [{ name: 'cutover_complete', duration_ms: 1 }];
const FINISHED = {
  success: true,
  exitCode: 0,
  durationMs: 5,
  state: 'succeeded' as const,
  jobId: 'job-1',
  attached: true,
  stdout: '',
  steps: MARKER,
};
const BACKGROUND = {
  success: true,
  exitCode: 0,
  durationMs: 0,
  state: 'running' as const,
  jobId: 'job-1',
  attached: false,
};
const FAILED = { ...FINISHED, success: false, exitCode: 14, state: 'failed' as const, steps: [] };

let dir: string;
let store: InstanceType<typeof TicketStore>;
let jobCalls: Executed[];
let answer: Record<string, unknown>;

beforeEach(() => {
  vi.clearAllMocks();
  dir = mkdtempSync(join(tmpdir(), 'job-tails-migrate-'));
  store = new TicketStore('test', dir);
  jobCalls = [];
  answer = FINISHED;
  mockGetRepository.mockResolvedValue({
    repositoryGuid: 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    tag: 'latest',
    networkId: 100,
  });
  mockSetRepositoryPlacement.mockResolvedValue(undefined);
  mockPlainExecute.mockResolvedValue({ success: true, stdout: '' });
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
});

afterEach(() => {
  setCommandJobDeps();
  rmSync(dir, { recursive: true, force: true });
  process.exitCode = 0;
});

/** The step's own machine calls; only the read-only `repository_list` mounted-on-target probe before the job is not a second leg, so a real leg that happened to set `probe` still shows. */
const plainCalls = () =>
  mockPlainExecute.mock.calls
    .map((c) => c[0] as { functionName: string; machineName: string; probe?: boolean })
    .filter((c) => !(c.probe === true && c.functionName === 'repository_list'));

describe('repo migrate (the compound class: one repository_migrate job and a plan)', () => {
  it('under --background returns at the one job start, with the plan on the ticket and no second leg', async () => {
    answer = BACKGROUND;
    await migrateRepo('app', { to: 'dst-machine', skipDns: true });

    expect(jobCalls.map((o) => o.functionName)).toEqual(['repository_migrate']);
    expect(jobCalls[0].machineName).toBe('src-machine');
    expect(jobCalls[0].jobSteps?.map((s) => s.name)).toEqual([
      'migratePlacement',
      'reportMigrateResult',
      'migrateComplete',
    ]);
    expect(plainCalls()).toEqual([]);
    expect(mockSetRepositoryPlacement).not.toHaveBeenCalled();
    expect(mockReconcile).not.toHaveBeenCalled();
    const [ticket] = store.tickets();
    expect(ticket.steps.map((s) => s.name)).toEqual(jobCalls[0].jobSteps?.map((s) => s.name));
    expect(ticket.stepsDone).toEqual([]);
  });

  it('control: followed, the target comes up once, the source is deleted once and placement moves once', async () => {
    await migrateRepo('app', { to: 'dst-machine', skipDns: true });

    expect(jobCalls.map((o) => o.functionName)).toEqual(['repository_migrate']);
    expect(plainCalls().map((c) => [c.functionName, c.machineName])).toEqual([
      ['repository_up', 'dst-machine'],
      ['repository_delete', 'src-machine'],
    ]);
    expect(mockSetRepositoryPlacement).toHaveBeenCalledExactlyOnceWith('app', {
      machine: 'dst-machine',
    });
    expect(mockReconcile.mock.calls.map((c) => c[0])).toEqual(['src-machine', 'dst-machine']);
    expect(store.tickets()[0].stepsDone).toEqual([
      'migratePlacement',
      'reportMigrateResult',
      'migrateComplete',
    ]);
  });

  it('control: --keep-source followed leaves the source image in place', async () => {
    await migrateRepo('app', { to: 'dst-machine', skipDns: true, keepSource: true });

    expect(plainCalls().map((c) => c.functionName)).toEqual(['repository_up']);
  });

  it('a failed job before the cutover runs no step and leaves placement on the source', async () => {
    answer = FAILED;
    await expect(migrateRepo('app', { to: 'dst-machine', skipDns: true })).rejects.toThrow(
      /repository_migrate failed/
    );

    expect(plainCalls()).toEqual([]);
    expect(mockSetRepositoryPlacement).not.toHaveBeenCalled();
    expect(mockReconcile).not.toHaveBeenCalled();
  });
});
