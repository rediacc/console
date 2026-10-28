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

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key} ${JSON.stringify(params)}` : key,
}));

const mockAccountServerFetch = vi.hoisted(() => vi.fn());
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

const mockWarn = vi.hoisted(() => vi.fn());
const mockSuccess = vi.hoisted(() => vi.fn());
vi.mock('../../services/core/output.js', () => ({
  outputService: {
    info: vi.fn(),
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
    expect(mockSuccess).toHaveBeenCalledTimes(1);
  });

  it('resolves a time to a snapshot id under the source stream scope', async () => {
    mockExecutorExecute.mockResolvedValue({ success: true, exitCode: 0 });
    mockAccountServerFetch.mockResolvedValue({
      manifests: [
        {
          snapshotId: SNAPSHOT,
          streamId: 's1',
          createdAt: '2026-08-14T09:00:00.000Z',
        },
      ],
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
    mockExecuteRepoFunction.mockResolvedValue({
      success: false,
      exitCode: 18,
      stdout: '',
      stderr: payload,
    });

    await run(['r@m1', '--at', SNAPSHOT, '--path', '/a']);

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
});
