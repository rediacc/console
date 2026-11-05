/**
 * PLAN-detached-jobs J4: `backup restore` runs `backup_restore` (a snapshot, `--at`) or `backup_pull` (an artifact) as
 * its one job, with the run record, the stats report, the registration rollback, the backup-unit re-render and, under
 * `--up`, the `restoreDeploy` successor as ticket steps. `backup restore --path` runs `backup_restore_path` with the
 * record print as its step. Under `--background` the command returns at the job start with the steps on the ticket and
 * none run; followed, the steps run in-process exactly once; a failed restore rolls the registration back and starts
 * no deploy.
 *
 * The job is a recording fake behind the runCommandJob seam; the plain executor, which the deploy step goes through,
 * is a second recorder.
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

const SOURCE = { repositoryGuid: 'src-guid', tag: 'latest', credential: 'secret' };
const SNAPSHOT = '20260815T041418Z-c1e8778364245163';

const mockAddRepository = vi.hoisted(() => vi.fn());
const mockRemoveRepository = vi.hoisted(() => vi.fn());
vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getCurrent: vi.fn().mockResolvedValue({ state: {}, resources: { repositories: {} } }),
    addRepository: mockAddRepository,
    removeRepository: mockRemoveRepository,
    allocateNetworkId: vi.fn().mockResolvedValue(4242),
    getRepository: (ref: string) => Promise.resolve(ref === 'src' ? SOURCE : undefined),
    getRepositoryKey: (ref: string) => Promise.resolve(ref),
    listRepositories: vi.fn().mockResolvedValue([]),
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
vi.mock('../../services/account/account-client.js', () => ({ accountServerFetch: vi.fn() }));
// The pull route's licence step is not under test: the target already holds a licence.
vi.mock('../../services/machine/machine-connection.js', () => ({
  machineConnections: {
    acquire: vi.fn().mockResolvedValue({ sftp: {}, machine: {}, release: vi.fn() }),
  },
}));
vi.mock('../../services/executor/repo-license-context.js', () => ({
  resolveRestoreLicenseContext: vi.fn().mockResolvedValue({}),
  restoreLicenseAlreadyInstalled: vi.fn().mockResolvedValue(true),
}));
const mockRecordBackupRun = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));
vi.mock('../../services/backup/backup-runs-state.js', () => ({
  recordBackupRun: mockRecordBackupRun,
}));
const mockReconcile = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));
vi.mock('../../services/backup/repo-change-hook.js', () => ({
  reconcileBackupSchedules: mockReconcile,
}));
vi.mock('../../services/backup/dr-nudge.js', () => ({
  warnIfConfigStorageUnenrolled: vi.fn().mockResolvedValue(undefined),
}));
vi.mock('../../services/addressing/ref-parser.js', () => ({
  parseRef: (raw: string) => ({ place: raw.split(':')[0], name: raw.split(':')[1] ?? 'src' }),
}));
vi.mock('../../utils/remote-resolve.js', () => ({
  resolveRemoteName: (name: string) => Promise.resolve({ type: 'machine', name }),
}));
vi.mock('../repo-backup-list.js', () => ({ renderBackupList: vi.fn() }));
vi.mock('../../services/repo/repo-key-deployment.js', () => ({
  deployRepoKeyIfNeeded: vi.fn().mockResolvedValue(undefined),
}));
vi.mock('../../utils/agent-guard.js', () => ({
  assertAgentRepoCreate: vi.fn().mockResolvedValue(undefined),
}));
vi.mock('../../utils/command-policy.js', () => ({
  assertCommandPolicy: vi.fn().mockResolvedValue(undefined),
  CMD: new Proxy({}, { get: (_t, p) => String(p) }),
}));
vi.mock('../_validate.js', () => ({ assertMachineExists: vi.fn().mockResolvedValue(undefined) }));
vi.mock('../backup-ops.js', () => ({ registerBackupOpsCommands: vi.fn() }));
vi.mock('../backup-strategy.js', () => ({ registerBackupStrategyCommands: vi.fn() }));
vi.mock('../../utils/local-execution-failures.js', () => ({
  renderLocalExecutionFailure: vi.fn(),
}));
const mockSuccess = vi.hoisted(() => vi.fn());
const mockWarn = vi.hoisted(() => vi.fn());
vi.mock('../../services/core/output.js', () => ({
  outputService: {
    info: vi.fn(),
    success: mockSuccess,
    warn: mockWarn,
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
const { registerBackupCommands } = await import('../backup.js');

type Executed = Record<string, unknown> & { functionName: string; jobSteps?: { name: string }[] };

const RECORD = {
  snapshotId: SNAPSHOT,
  path: '/a',
  to: '/b',
  files: 1,
  dirs: 0,
  symlinks: 0,
  skipped: 0,
  bytesWritten: 12,
  cellsTotal: 100,
  cellsSelected: 3,
  chunksFetched: 3,
  bytesFetched: 3000,
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
const BACKGROUND = { ...FINISHED, durationMs: 0, state: 'running' as const, attached: false };
const FAILED = { ...FINISHED, success: false, exitCode: 1, state: 'failed' as const };

let dir: string;
let store: InstanceType<typeof TicketStore>;
let jobCalls: Executed[];
let answer: Record<string, unknown>;

beforeEach(() => {
  vi.clearAllMocks();
  dir = mkdtempSync(join(tmpdir(), 'job-tails-restore-'));
  store = new TicketStore('test', dir);
  jobCalls = [];
  answer = FINISHED;
  mockAddRepository.mockResolvedValue(undefined);
  mockRemoveRepository.mockResolvedValue(undefined);
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

async function run(argv: string[]): Promise<void> {
  const program = new Command();
  program.exitOverride();
  registerBackupCommands(program);
  await program.parseAsync(['node', 'rdc', 'backup', ...argv]);
}

function onlyTicket() {
  const tickets = store.tickets();
  expect(tickets).toHaveLength(1);
  return tickets[0];
}

const stepNames = (call: Executed) => call.jobSteps?.map((s) => s.name);
/** The step's own machine calls; the network-id probe before the job is a read, not a second leg. */
const deployCalls = () =>
  mockPlainExecute.mock.calls.map((c) => c[0] as Executed).filter((c) => c.probe !== true);

const SNAPSHOT_RESTORE = ['restore', 'm1:src', '--as', 'copy', '-m', 'm1', '--at', SNAPSHOT];
const RESTORE_STEPS = [
  'recordBackupRun',
  'recordBackupRunFailed',
  'reportRestoreStats',
  'reportRestoreDamage',
  'rollbackRestoreRegistration',
  'reconcileBackupSchedules',
];

describe('backup restore --at (a successor and finalizers on the backup_restore job)', () => {
  it('under --background returns at the job start, with every tail on the ticket and none run', async () => {
    answer = BACKGROUND;
    await run([...SNAPSHOT_RESTORE, '--up']);

    expect(jobCalls.map((o) => o.functionName)).toEqual(['backup_restore']);
    expect(stepNames(jobCalls[0])).toEqual([...RESTORE_STEPS, 'restoreDeploy']);
    expect(deployCalls()).toEqual([]);
    expect(mockRecordBackupRun).not.toHaveBeenCalled();
    expect(mockReconcile).not.toHaveBeenCalled();
    expect(mockRemoveRepository).not.toHaveBeenCalled();
    expect(mockSuccess).not.toHaveBeenCalled();
    const ticket = onlyTicket();
    expect(ticket.steps.map((s) => s.name)).toEqual([...RESTORE_STEPS, 'restoreDeploy']);
    expect(ticket.stepsDone).toEqual([]);
  });

  it('control: followed, the run is recorded once and --up starts exactly one repository_up', async () => {
    await run([...SNAPSHOT_RESTORE, '--up']);

    expect(jobCalls.map((o) => o.functionName)).toEqual(['backup_restore']);
    expect(mockRecordBackupRun).toHaveBeenCalledExactlyOnceWith(
      'copy',
      expect.objectContaining({ kind: 'restore', status: 'ok', snapshotId: SNAPSHOT })
    );
    expect(mockReconcile).toHaveBeenCalledExactlyOnceWith('m1');
    expect(deployCalls().map((c) => c.functionName)).toEqual(['repository_up']);
    expect(deployCalls()[0].params).toMatchObject({ repository: 'copy', mount: true });
    expect(mockRemoveRepository).not.toHaveBeenCalled();
  });

  it('control: without --up no restoreDeploy is planned', async () => {
    await run(SNAPSHOT_RESTORE);

    expect(stepNames(jobCalls[0])).toEqual(RESTORE_STEPS);
    expect(deployCalls()).toEqual([]);
  });

  it('a failed restore drops the registration it made and starts no deploy', async () => {
    answer = FAILED;
    await run([...SNAPSHOT_RESTORE, '--up']);

    expect(mockRemoveRepository).toHaveBeenCalledExactlyOnceWith('copy:latest');
    expect(mockRecordBackupRun).toHaveBeenCalledExactlyOnceWith(
      'copy',
      expect.objectContaining({ kind: 'restore', status: 'failed' })
    );
    expect(deployCalls()).toEqual([]);
    expect(mockReconcile).not.toHaveBeenCalled();
  });
});

describe('backup restore without --at (the pull route, the same plan on backup_pull)', () => {
  it('under --background returns at the pull start, with the tails on the ticket and none run', async () => {
    answer = BACKGROUND;
    await run(['restore', 'm1:src', '--as', 'copy', '-m', 'm1', '--up']);

    expect(jobCalls.map((o) => o.functionName)).toEqual(['backup_pull']);
    expect(stepNames(jobCalls[0])).toEqual([...RESTORE_STEPS, 'restoreDeploy']);
    expect(deployCalls()).toEqual([]);
    expect(mockRecordBackupRun).not.toHaveBeenCalled();
    expect(onlyTicket().stepsDone).toEqual([]);
  });

  it('control: followed, the deploy starts once and a failed pull rolls the registration back', async () => {
    await run(['restore', 'm1:src', '--as', 'copy', '-m', 'm1', '--up']);
    expect(deployCalls().map((c) => c.functionName)).toEqual(['repository_up']);

    mockPlainExecute.mockClear();
    mockRemoveRepository.mockClear();
    answer = FAILED;
    await run(['restore', 'm1:src', '--as', 'copy', '-m', 'm1', '--up']);
    expect(mockRemoveRepository).toHaveBeenCalledExactlyOnceWith('copy:latest');
    expect(deployCalls()).toEqual([]);
  });
});

describe('backup restore --path (a success step: reportRestorePath)', () => {
  const PATH_RESTORE = ['restore', 'm1:src', '--at', SNAPSHOT, '--path', '/a', '--to', '/b'];

  it('under --background returns at the job start, with the record print on the ticket and not run', async () => {
    answer = BACKGROUND;
    await run(PATH_RESTORE);

    expect(jobCalls.map((o) => o.functionName)).toEqual(['backup_restore_path']);
    expect(jobCalls[0].params).toMatchObject({ path: '/a', to: '/b', at: SNAPSHOT });
    expect(stepNames(jobCalls[0])).toEqual(['reportRestorePath', 'reportRestorePathFailure']);
    expect(mockSuccess).not.toHaveBeenCalled();
    expect(onlyTicket().stepsDone).toEqual([]);
    expect(mockAddRepository).not.toHaveBeenCalled();
  });

  it('control: followed, the record is printed exactly once', async () => {
    answer = { ...FINISHED, stdout: `${JSON.stringify(RECORD)}\n` };
    await run(PATH_RESTORE);

    const printed = mockSuccess.mock.calls.filter((c) =>
      String(c[0]).startsWith('commands.backup.restore.pathRestored')
    );
    expect(printed).toHaveLength(1);
    expect(onlyTicket().stepsDone).toEqual(['reportRestorePath']);
  });

  it('a failed restore-path prints no record', async () => {
    answer = FAILED;
    await run(PATH_RESTORE);

    expect(mockSuccess).not.toHaveBeenCalled();
    expect(onlyTicket().state).toBe('failed');
  });

  it('plans the exit-18 warning as a failure step beside the record print', async () => {
    answer = BACKGROUND;
    await run(PATH_RESTORE);

    expect(stepNames(jobCalls[0])).toEqual(['reportRestorePath', 'reportRestorePathFailure']);
    const failure = onlyTicket().steps.find((s) => s.name === 'reportRestorePathFailure');
    expect(failure?.on).toBe('failure');
  });

  it('under --background a snapshot that cannot address the path warns nothing at the job start', async () => {
    answer = { ...BACKGROUND, success: false, exitCode: 18 };
    await run(PATH_RESTORE);

    expect(mockWarn).not.toHaveBeenCalled();
    expect(onlyTicket().stepsDone).toEqual([]);
  });

  it('followed, a snapshot that cannot address the path warns once and keeps exit code 18', async () => {
    answer = {
      ...FAILED,
      exitCode: 18,
      stdout: `${JSON.stringify({ reason: 'live-mount' })}\n`,
    };
    await run(PATH_RESTORE);

    const warned = mockWarn.mock.calls.filter((c) => String(c[0]).includes('pathNoListing'));
    expect(warned).toHaveLength(1);
    expect(String(warned[0][0])).toContain('commands.backup.restore.pathNoListingLiveMount');
    expect(process.exitCode).toBe(18);
    expect(onlyTicket().stepsDone).toEqual(['reportRestorePathFailure']);
  });

  it('followed, an exit-18 reason the output does not carry falls back to the generic message', async () => {
    answer = { ...FAILED, exitCode: 18, stderr: JSON.stringify({ reason: 'live-mount' }) };
    await run(PATH_RESTORE);

    expect(mockWarn).toHaveBeenCalledWith(
      expect.stringContaining('commands.backup.restore.pathNoListing:')
    );
    expect(process.exitCode).toBe(18);
  });

  it('a detached job step reads the reason from the stdout line renet now echoes beside stderr', async () => {
    const { resolveStepHandler } = await import('../../services/jobs/steps.js');
    await import('../backup-restore-path.js');
    const handler = await resolveStepHandler('reportRestorePathFailure');
    const refusal = JSON.stringify({ code: 'NO_LISTING', reason: 'absent', snapshotId: SNAPSHOT });
    await handler({
      jobId: 'j1',
      machine: 'm1',
      params: { repo: 'src', snapshot: SNAPSHOT },
      state: 'failed',
      // The job's output events fold to msg lines, exactly as run-job.ts builds `output`.
      output: `${refusal}\n`,
      exitCode: 18,
    });

    expect(mockWarn).toHaveBeenCalledWith(
      expect.stringContaining('commands.backup.restore.pathNoListingAbsent')
    );
    expect(process.exitCode).toBe(18);
  });

  it('control: any other failure warns nothing about a listing', async () => {
    answer = { ...FAILED, exitCode: 2 };
    await run(PATH_RESTORE);

    expect(mockWarn.mock.calls.filter((c) => String(c[0]).includes('pathNoListing'))).toEqual([]);
    expect(process.exitCode).not.toBe(18);
  });
});
