/**
 * `rdc backup restore --at <t> --path <p> [--to <d>]`, the single-path restore route.
 *
 * The route must reach `backup_restore_path` and nothing of the whole-image restore:
 * no repository record, no network id, no `backup_restore`. A route that quietly fell
 * through to the whole-image path would restore a full repository while the operator
 * asked for one file, and succeed.
 */

import { Command } from 'commander';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { PlannedStep } from '../../services/jobs/steps-support.js';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key} ${JSON.stringify(params)}` : key,
}));

const mockAccountServerFetch = vi.hoisted(() => vi.fn());
// These verbs read the hosted backup plane, which needs a login (PLAN-free-license R13); a logged-in operator is the case under test.
vi.mock('../../services/account/subscription-auth.js', () => ({
  getSubscriptionTokenState: () => ({
    kind: 'ready',
    token: { token: 't' },
    serverUrl: 'https://acct.example',
  }),
  getSubscriptionServerUrl: () => 'https://acct.example',
}));
vi.mock('../../services/account/account-client.js', () => ({
  accountServerFetch: mockAccountServerFetch,
}));

const mockExecuteRepoFunction = vi.hoisted(() => vi.fn());
vi.mock('../../utils/repo-executor.js', () => ({
  executeRepoFunction: mockExecuteRepoFunction,
}));

const mockExecutorExecute = vi.hoisted(() => vi.fn());
vi.mock('../../services/executor/executor-factory.js', () => ({
  getExecutor: () => ({ execute: mockExecutorExecute }),
}));

const mockGetRepository = vi.hoisted(() => vi.fn());
const mockAddRepository = vi.hoisted(() => vi.fn());
const mockAllocateNetworkId = vi.hoisted(() => vi.fn());
vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getRepository: mockGetRepository,
    addRepository: mockAddRepository,
    allocateNetworkId: mockAllocateNetworkId,
    removeRepository: vi.fn(),
  },
}));

const mockResolveRemoteName = vi.hoisted(() => vi.fn());
vi.mock('../../utils/remote-resolve.js', () => ({
  resolveRemoteName: mockResolveRemoteName,
}));

vi.mock('../../utils/command-policy.js', () => ({
  assertCommandPolicy: vi.fn(),
  CMD: { BACKUP_RESTORE: 'backup.restore' },
}));

// The failure the executor would render (it exits the process in agent mode); the fallback renders only the one that ends the run.
const mockRenderFailure = vi.hoisted(() => vi.fn());
vi.mock('../../utils/local-execution-failures.js', () => ({
  renderLocalExecutionFailure: mockRenderFailure,
}));

const mockWarn = vi.hoisted(() => vi.fn());
const mockSuccess = vi.hoisted(() => vi.fn());
const mockInfo = vi.hoisted(() => vi.fn());
vi.mock('../../services/core/output.js', () => ({
  outputService: {
    info: mockInfo,
    success: mockSuccess,
    warn: mockWarn,
    error: vi.fn(),
    print: vi.fn(),
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

const { registerBackupCommands } = await import('../backup.js');
const { ValidationError } = await import('../../utils/errors.js');

async function run(argv: string[]): Promise<void> {
  const program = new Command();
  program.exitOverride();
  registerBackupCommands(program);
  await program.parseAsync(['node', 'rdc', 'backup', 'restore', ...argv]);
}

const SNAPSHOT = '20260814T120000Z-0011223344556677';
const record = {
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

beforeEach(() => {
  vi.clearAllMocks();
  mockResolveRemoteName.mockResolvedValue({ type: 'machine', name: 'm1' });
  mockGetRepository.mockResolvedValue({
    repositoryGuid: 'repo-guid',
    grandGuid: 'grand-guid',
    credential: 'secret',
  });
  mockExecuteRepoFunction.mockResolvedValue({
    success: true,
    exitCode: 0,
    stdout: JSON.stringify(record),
  });
});

afterEach(() => {
  process.exitCode = 0;
});

describe('backup restore --path', () => {
  it('runs backup_restore_path with the lineage and the resolved snapshot, and nothing of the whole-image restore', async () => {
    await run(['r@m1', '--at', SNAPSHOT, '--path', '/a', '--to', '/b']);

    expect(mockExecuteRepoFunction).toHaveBeenCalledTimes(1);
    const [fn, repoKey, machine, params] = mockExecuteRepoFunction.mock.calls[0];
    expect(fn).toBe('backup_restore_path');
    expect(repoKey).toBe('r');
    expect(machine).toBe('m1');
    expect(params).toEqual({ lineage: 'grand-guid', at: SNAPSHOT, path: '/a', to: '/b' });
    // THE DEFECT: falling through to the whole-image restore, which registers a repository and restores everything.
    expect(mockAddRepository).not.toHaveBeenCalled();
    expect(mockAllocateNetworkId).not.toHaveBeenCalled();
    expect(mockExecutorExecute).not.toHaveBeenCalled();
    // The record print rides the job's ticket (PLAN-detached-jobs J4): it is a step, not inline output.
    const options = mockExecuteRepoFunction.mock.calls[0][4] as {
      job: { verb: string; steps: { name: string; params: Record<string, unknown> }[] };
    };
    expect(options.job.verb).toBe('backup restore');
    expect(options.job.steps).toEqual([
      expect.objectContaining({
        name: 'reportRestorePath',
        on: 'success',
        params: { repo: 'r', snapshot: SNAPSHOT },
      }),
      expect.objectContaining({
        name: 'reportRestorePathFailure',
        on: 'failure',
        params: { repo: 'r', snapshot: SNAPSHOT },
      }),
    ]);
    expect(mockSuccess).not.toHaveBeenCalled();
  });

  it('resolves a time to a snapshot id under the source stream scope', async () => {
    mockExecutorExecute.mockResolvedValue({ success: true, exitCode: 0 });
    // The resolve route answers the one row; the anchor names the stream, and a listing is read for the index.
    mockAccountServerFetch.mockResolvedValue({
      snapshotId: SNAPSHOT,
      streamId: 's1',
      hasIndex: true,
      createdAt: '2026-08-14T09:00:00.000Z',
    });
    // The anchor read goes through backup_verify.
    mockExecuteRepoFunction.mockImplementation((fn: string) =>
      Promise.resolve(
        fn === 'backup_verify'
          ? {
              success: true,
              exitCode: 0,
              stdout: JSON.stringify({ status: 'verified', snapshotId: SNAPSHOT }),
            }
          : { success: true, exitCode: 0, stdout: JSON.stringify(record) }
      )
    );

    await run(['r@m1', '--at', '2026-08-14T12:00:00Z', '--path', '/a']);

    const call = mockExecuteRepoFunction.mock.calls.find((c) => c[0] === 'backup_restore_path');
    expect(call?.[3]).toMatchObject({ at: SNAPSHOT, to: '' });
    expect(mockExecuteRepoFunction.mock.calls.map((c) => c[0])).toContain('backup_verify');
  });

  it.each([
    ['--path without --at', ['r@m1', '--path', '/a']],
    ['--to without --path', ['r@m1', '--at', SNAPSHOT, '--to', '/b']],
    ['an empty --to without --path', ['r@m1', '--at', SNAPSHOT, '--to', '']],
    [
      '--path with --datastore (the verb takes none)',
      ['r@m1', '--at', SNAPSHOT, '--path', '/a', '--datastore', 'd'],
    ],
    ['--path with --up', ['r@m1', '--at', SNAPSHOT, '--path', '/a', '--up']],
    ['--path with --as', ['r@m1', '--at', SNAPSHOT, '--path', '/a', '--as', 'x']],
    [
      '--path with --health-window',
      ['r@m1', '--at', SNAPSHOT, '--path', '/a', '--health-window', '5'],
    ],
  ])('refuses %s with a ValidationError and executes nothing', async (_label, argv) => {
    await expect(run(argv)).rejects.toBeInstanceOf(ValidationError);
    expect(mockExecuteRepoFunction).not.toHaveBeenCalled();
    expect(mockExecutorExecute).not.toHaveBeenCalled();
    expect(mockAddRepository).not.toHaveBeenCalled();
  });

  // The message is asserted, not only the error class: with routing on truthiness an empty
  // --path falls through to the whole-image restore, which throws its own ValidationError.
  it.each([
    ['an empty --path', '--path', ['r@m1', '--at', SNAPSHOT, '--path', '']],
    ['a blank --path', '--path', ['r@m1', '--at', SNAPSHOT, '--path', '  ']],
    ['an empty --to', '--to', ['r@m1', '--at', SNAPSHOT, '--path', '/a', '--to', '']],
    ['an empty -m', '-m', ['r@m1', '--at', SNAPSHOT, '--path', '/a', '-m', '']],
  ])('refuses %s naming the empty flag and executes nothing', async (_label, flag, argv) => {
    await expect(run(argv)).rejects.toThrow(
      `commands.backup.restore.pathEmpty ${JSON.stringify({ flag })}`
    );
    expect(mockExecuteRepoFunction).not.toHaveBeenCalled();
    expect(mockExecutorExecute).not.toHaveBeenCalled();
    expect(mockAddRepository).not.toHaveBeenCalled();
  });

  it('refuses a ref whose place is not a machine', async () => {
    mockResolveRemoteName.mockResolvedValue({ type: 'cluster', name: 'c1' });

    await expect(run(['r@c1', '--at', SNAPSHOT, '--path', '/a'])).rejects.toBeInstanceOf(
      ValidationError
    );
    expect(mockExecuteRepoFunction).not.toHaveBeenCalled();
  });

  it('refuses a repo with no credential and executes nothing', async () => {
    mockGetRepository.mockResolvedValue({ repositoryGuid: 'repo-guid' });

    await expect(run(['r@m1', '--at', SNAPSHOT, '--path', '/a'])).rejects.toBeInstanceOf(
      ValidationError
    );
    expect(mockExecuteRepoFunction).not.toHaveBeenCalled();
  });

  it.each([
    ['absent', 'pathNoListingAbsent'],
    ['live-mount', 'pathNoListingLiveMount'],
    ['no-positions', 'pathNoListingNoPositions'],
    ['', 'pathNoListing'],
  ])('turns exit 18 (reason "%s") into exit code 18 and the %s message', async (reason, key) => {
    const payload = JSON.stringify({ code: 'NO_LISTING', ...(reason && { reason }) });
    // The command itself plans the failure step: its name, its trigger and its params come from the real `backup restore --path` run, not from this test.
    await run(['r@m1', '--at', SNAPSHOT, '--path', '/a']);
    const { job } = mockExecuteRepoFunction.mock.calls[0][4] as {
      job: { steps: PlannedStep[] };
    };
    const planned = job.steps.find((step) => step.name === 'reportRestorePathFailure');
    expect(planned?.params).toEqual({ repo: 'r', snapshot: SNAPSHOT });
    // The trigger the command planned, not only the registry's.
    expect(planned?.on).toBe('failure');
    const { getStepDefinition, resolveStepHandler } = await import('../../services/jobs/steps.js');
    expect(getStepDefinition('reportRestorePathFailure')?.on).toBe('failure');
    const handler = await resolveStepHandler('reportRestorePathFailure');
    await handler({
      jobId: 'j1',
      machine: 'm1',
      params: planned?.params ?? {},
      state: 'failed',
      output: `${payload}\n`,
      exitCode: 18,
    });

    expect(process.exitCode).toBe(18);
    expect(mockWarn).toHaveBeenCalledTimes(1);
    expect(mockWarn.mock.calls[0][0]).toContain(`commands.backup.restore.${key} `);
    expect(mockSuccess).not.toHaveBeenCalled();
  });

  it('leaves any other failure to the executor, adding nothing', async () => {
    mockExecuteRepoFunction.mockImplementation(() => {
      process.exitCode = 19;
      return Promise.resolve({ success: false, exitCode: 19, stdout: '' });
    });

    await run(['r@m1', '--at', SNAPSHOT, '--path', '/a']);

    expect(process.exitCode).toBe(19);
    expect(mockWarn).not.toHaveBeenCalled();
    expect(mockSuccess).not.toHaveBeenCalled();
  });

  // The record is what tells the operator that a path restore fetched a fraction of the image: 3 of 100 cells here.
  it('prints the fetched-cells line from the record, selected below total', async () => {
    await run(['r@m1', '--at', SNAPSHOT, '--path', '/a']);
    const { job } = mockExecuteRepoFunction.mock.calls[0][4] as { job: { steps: PlannedStep[] } };
    const planned = job.steps.find((step) => step.name === 'reportRestorePath');
    expect(planned, 'the command planned no reportRestorePath step').toBeDefined();
    const { resolveStepHandler } = await import('../../services/jobs/steps.js');
    const handler = await resolveStepHandler('reportRestorePath');
    expect(record.chunksFetched).toBeLessThan(record.cellsTotal);
    await handler({
      jobId: 'j1',
      machine: 'm1',
      params: planned?.params ?? {},
      state: 'succeeded',
      output: `${JSON.stringify(record)}\n`,
      exitCode: 0,
    });
    expect(mockInfo).toHaveBeenCalledTimes(1);
    expect(mockInfo.mock.calls[0][0]).toContain(
      `commands.backup.restore.pathFetched {"selected":3,"total":100,`
    );
  });

  // renet exits 19 (NO_SUCH_PATH) when the snapshot has a listing and the path is not in it. The failure step must not
  // recast it as the exit-18 "no listing" warning, nor print a success; the 19 stays the process exit code.
  it('keeps exit 19 for a path missing from a snapshot that has a listing', async () => {
    await run(['r@m1', '--at', SNAPSHOT, '--path', '/nope']);
    const { job } = mockExecuteRepoFunction.mock.calls[0][4] as { job: { steps: PlannedStep[] } };
    const planned = job.steps.find((step) => step.name === 'reportRestorePathFailure');
    expect(planned, 'the command planned no reportRestorePathFailure step').toBeDefined();
    const { resolveStepHandler } = await import('../../services/jobs/steps.js');
    const handler = await resolveStepHandler('reportRestorePathFailure');
    process.exitCode = 19;
    await handler({
      jobId: 'j1',
      machine: 'm1',
      params: planned?.params ?? {},
      state: 'failed',
      output: `${JSON.stringify({ code: 'NO_SUCH_PATH', snapshotId: SNAPSHOT })}\n`,
      exitCode: 19,
    });
    expect(process.exitCode).toBe(19);
    expect(mockWarn).not.toHaveBeenCalled();
    expect(mockSuccess).not.toHaveBeenCalled();
    expect(mockInfo).not.toHaveBeenCalled();
  });

  it('with a cluster place and -m, runs on -m and scopes the stream to -m', async () => {
    mockResolveRemoteName.mockResolvedValue({ type: 'cluster', name: 'c1' });
    mockExecutorExecute.mockResolvedValue({ success: true, exitCode: 0 });
    mockAccountServerFetch.mockResolvedValue({
      manifests: [{ snapshotId: SNAPSHOT, streamId: 's1', createdAt: '2026-08-14T09:00:00.000Z' }],
    });
    mockExecuteRepoFunction.mockImplementation((fn: string) =>
      Promise.resolve(
        fn === 'backup_verify'
          ? {
              success: true,
              exitCode: 0,
              stdout: JSON.stringify({ status: 'verified', snapshotId: SNAPSHOT }),
            }
          : { success: true, exitCode: 0, stdout: JSON.stringify(record) }
      )
    );

    await run(['r@c1', '--at', '2026-08-14T12:00:00Z', '--path', '/a', '-m', 'm2']);

    const machines = mockExecuteRepoFunction.mock.calls.map((c) => [c[0], c[2]]);
    expect(machines).toContainEqual(['backup_verify', 'm2']);
    expect(machines).toContainEqual(['backup_restore_path', 'm2']);
  });

  it('with a cluster place and no -m, refuses naming the fix', async () => {
    mockResolveRemoteName.mockResolvedValue({ type: 'cluster', name: 'c1' });
    await expect(run(['r@c1', '--at', SNAPSHOT, '--path', '/a'])).rejects.toThrow(
      'pathNeedsMachine'
    );
    expect(mockExecuteRepoFunction).not.toHaveBeenCalled();
  });

  it('with a machine place and -m other, scopes the stream to the place and runs on -m', async () => {
    mockExecutorExecute.mockResolvedValue({ success: true, exitCode: 0 });
    mockAccountServerFetch.mockResolvedValue({
      manifests: [{ snapshotId: SNAPSHOT, streamId: 's1', createdAt: '2026-08-14T09:00:00.000Z' }],
    });
    mockExecuteRepoFunction.mockImplementation((fn: string) =>
      Promise.resolve(
        fn === 'backup_verify'
          ? {
              success: true,
              exitCode: 0,
              stdout: JSON.stringify({ status: 'verified', snapshotId: SNAPSHOT }),
            }
          : { success: true, exitCode: 0, stdout: JSON.stringify(record) }
      )
    );

    await run(['r@m1', '--at', '2026-08-14T12:00:00Z', '--path', '/a', '-m', 'm2']);

    const machines = mockExecuteRepoFunction.mock.calls.map((c) => [c[0], c[2]]);
    expect(machines).toContainEqual(['backup_verify', 'm1']);
    expect(machines).toContainEqual(['backup_restore_path', 'm2']);
  });
});

describe('backup restore --path store fallback', () => {
  const failed = (error: string) => ({ success: false, exitCode: 1, error, stdout: '' });
  const ok = { success: true, exitCode: 0, stdout: JSON.stringify(record) };
  const stores = () => mockExecuteRepoFunction.mock.calls.map((c) => c[3].store);
  const toTargets = () => mockExecuteRepoFunction.mock.calls.map((c) => c[3].to);
  const FALLBACK = `commands.backup.restore.storeFallback ${JSON.stringify({ failed: 'eu-west', next: 'home' })}`;
  const ARGV = ['r@m1', '--at', SNAPSHOT, '--path', '/a', '--to', '/b'];

  /** The account ranks eu-west ahead of home; the executor answers each attempt in turn, the last repeating. */
  function answers(...results: Record<string, unknown>[]): void {
    mockAccountServerFetch.mockImplementation((path: string) =>
      Promise.resolve(
        path.includes('/stores/lineage/')
          ? {
              stores: ['eu-west', 'home'].map((storeId) => ({
                storeId,
                newestSnapshotId: SNAPSHOT,
                newestSnapshotAt: null,
                lastVerifyOk: true,
              })),
            }
          : undefined
      )
    );
    let i = 0;
    mockExecuteRepoFunction.mockImplementation(() => {
      const result = results[Math.min(i, results.length - 1)];
      i += 1;
      return Promise.resolve(result);
    });
  }

  it('falls back to the next store on a 5xx, asks for the same --to, and names the store that served', async () => {
    answers(failed('HTTP 502 bad gateway'), ok);

    await run(ARGV);

    expect(stores()).toEqual(['eu-west', undefined]);
    // renet stages the fetch and places under --to only after it, so the failed attempt wrote nothing there; the retry targets the same directory.
    expect(toTargets()).toEqual(['/b', '/b']);
    expect(mockWarn).toHaveBeenCalledWith(FALLBACK);
    expect(mockInfo).toHaveBeenCalledWith(
      `commands.backup.restore.storeServed ${JSON.stringify({ store: 'home' })}`
    );
    expect(mockRenderFailure).not.toHaveBeenCalled();
    expect(mockExecuteRepoFunction.mock.calls.every((c) => c[4].failureIsAnswer === true)).toBe(
      true
    );
  });

  it('does not fall back after a copy-out that renet rolled back, which a second store cannot cure', async () => {
    answers(failed('write failed: timed out (every path this run created was removed)'), ok);

    await run(ARGV);

    expect(stores()).toEqual(['eu-west']);
    expect(mockRenderFailure).toHaveBeenCalledTimes(1);
  });

  it('does not fall back when the snapshot is missing, and renders that failure', async () => {
    answers(failed('snapshot snap-1 not found in the manifest index'), ok);

    await run(ARGV);

    expect(stores()).toEqual(['eu-west']);
    expect(mockWarn).not.toHaveBeenCalled();
    expect(mockRenderFailure).toHaveBeenCalledTimes(1);
  });

  it('never falls back from an explicit --from, even on a 5xx', async () => {
    answers(failed('HTTP 503 service unavailable'), ok);

    await run([...ARGV, '--from', 'eu-west']);

    expect(stores()).toEqual(['eu-west']);
    expect(mockWarn).not.toHaveBeenCalled();
    expect(mockRenderFailure).toHaveBeenCalledTimes(1);
  });
});
