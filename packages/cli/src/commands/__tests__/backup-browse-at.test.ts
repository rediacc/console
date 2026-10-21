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

const mockResolveRepoRef = vi.hoisted(() => vi.fn());
const mockResolveRepoRefLocal = vi.hoisted(() => vi.fn());
vi.mock('../../utils/repo-target.js', () => ({
  resolveRepoRef: mockResolveRepoRef,
  resolveRepoRefLocal: mockResolveRepoRefLocal,
}));

vi.mock('../../services/backup/backup-runs-state.js', () => ({
  recordBackupRun: vi.fn(),
}));

const mockGetRepository = vi.hoisted(() => vi.fn());
vi.mock('../../services/config/config-resources.js', () => ({
  configService: { getRepository: mockGetRepository },
}));

const mockResolveSnapshotAt = vi.hoisted(() => vi.fn());
vi.mock('../backup.js', () => ({
  resolveSnapshotAt: mockResolveSnapshotAt,
}));

const mockPrint = vi.hoisted(() => vi.fn());
const mockWarn = vi.hoisted(() => vi.fn());
vi.mock('../../services/core/output.js', () => ({
  outputService: {
    info: vi.fn(),
    success: vi.fn(),
    warn: mockWarn,
    error: vi.fn(),
    print: mockPrint,
    format: (rows: unknown) => JSON.stringify(rows),
  },
}));

vi.mock('../../utils/guid-resolver.js', () => ({
  loadGuidMap: () => Promise.resolve({}),
  createGuidResolver: () => (guid: string) => guid,
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

const { registerBackupStorageCommands } = await import('../backup-storage.js');
const { ValidationError } = await import('../../utils/errors.js');

async function run(argv: string[]): Promise<void> {
  const program = new Command();
  program.exitOverride();
  const backup = program.command('backup');
  registerBackupStorageCommands(backup);
  await program.parseAsync(['node', 'rdc', 'backup', ...argv]);
}

const SNAPSHOT = '01J0000000000000000000SNAP';

const listingStdout = JSON.stringify({
  source: 'snapshot',
  entries: [
    { path: '/app', type: 'dir', size: 0, modTime: '2026-08-16T06:36:28Z' },
    { path: '/readme.txt', type: 'file', size: 12, modTime: '2026-08-16T06:36:28Z' },
  ],
  truncated: false,
  totalSize: 12,
});

beforeEach(() => {
  vi.clearAllMocks();
  mockResolveRepoRef.mockResolvedValue({ repoKey: 'shop', machineName: 'm1' });
  mockGetRepository.mockResolvedValue({
    repositoryGuid: 'repo-guid',
    grandGuid: undefined,
    credential: 'secret',
  });
  mockResolveSnapshotAt.mockResolvedValue(SNAPSHOT);
  mockExecuteRepoFunction.mockResolvedValue({
    success: true,
    exitCode: 0,
    stdout: listingStdout,
  });
});

afterEach(() => {
  process.exitCode = 0;
});

describe('backup browse without --at (regression control)', () => {
  it('runs backup_browse exactly as before and never touches the repo record or the server', async () => {
    await run(['browse', 'shop']);

    expect(mockExecuteRepoFunction).toHaveBeenCalledTimes(1);
    const [fn, repoKey, machine, params, options] = mockExecuteRepoFunction.mock.calls[0];
    expect(fn).toBe('backup_browse');
    expect(repoKey).toBe('shop');
    expect(machine).toBe('m1');
    expect(Object.keys(params).sort()).toEqual(['depth', 'limit', 'path']);
    expect(params.path).toBe('');
    expect(options).toEqual({ debug: undefined, captureOutput: true });
    expect(mockGetRepository).not.toHaveBeenCalled();
    expect(mockAccountServerFetch).not.toHaveBeenCalled();
    expect(mockResolveSnapshotAt).not.toHaveBeenCalled();
  });
});

describe('backup browse --at', () => {
  it('dispatches backup_browse_at with a snapshot id as given', async () => {
    await run(['browse', 'shop', '--at', SNAPSHOT, '--path', '/app']);

    expect(mockResolveSnapshotAt).toHaveBeenCalledWith('repo-guid', SNAPSHOT);
    expect(mockExecuteRepoFunction).toHaveBeenCalledTimes(1);
    const [fn, repoKey, machine, params, options] = mockExecuteRepoFunction.mock.calls[0];
    expect(fn).toBe('backup_browse_at');
    expect(repoKey).toBe('shop');
    expect(machine).toBe('m1');
    expect(params).toMatchObject({ lineage: 'repo-guid', at: SNAPSHOT, path: '/app' });
    expect(options).toEqual({ debug: undefined, captureOutput: true });
  });

  it('uses the grand GUID as the lineage for a fork', async () => {
    mockGetRepository.mockResolvedValue({
      repositoryGuid: 'fork-guid',
      grandGuid: 'grand-guid',
      credential: 'secret',
    });
    await run(['browse', 'shop', '--at', SNAPSHOT]);

    expect(mockResolveSnapshotAt).toHaveBeenCalledWith('grand-guid', SNAPSHOT);
    expect(mockExecuteRepoFunction.mock.calls[0][3]).toMatchObject({ lineage: 'grand-guid' });
  });

  it('dispatches the snapshot id a time resolves to', async () => {
    await run(['browse', 'shop', '--at', '2026-08-16T00:00:00Z']);

    expect(mockResolveSnapshotAt).toHaveBeenCalledWith('repo-guid', '2026-08-16T00:00:00Z');
    expect(mockExecuteRepoFunction.mock.calls[0][3]).toMatchObject({ at: SNAPSHOT });
  });

  it('refuses a repo with no credential and executes nothing', async () => {
    mockGetRepository.mockResolvedValue({ repositoryGuid: 'repo-guid' });

    await expect(run(['browse', 'shop', '--at', SNAPSHOT])).rejects.toBeInstanceOf(ValidationError);
    expect(mockExecuteRepoFunction).not.toHaveBeenCalled();
  });

  it('turns exit 18 into a warning and exit code 18, printing nothing', async () => {
    mockExecuteRepoFunction.mockResolvedValue({ success: false, exitCode: 18, stdout: '' });

    await run(['browse', 'shop', '--at', SNAPSHOT]);

    expect(mockWarn).toHaveBeenCalledTimes(1);
    expect(mockWarn.mock.calls[0][0]).toContain('commands.backup.browse.noListing');
    expect(process.exitCode).toBe(18);
    expect(mockPrint).not.toHaveBeenCalled();
  });

  it('renders the listing rows on success', async () => {
    await run(['browse', 'shop', '--at', SNAPSHOT]);

    expect(mockPrint).toHaveBeenCalledTimes(1);
    const rows = JSON.parse(mockPrint.mock.calls[0][0] as string);
    expect(rows.map((r: { name: string }) => r.name)).toEqual(['/app', '/readme.txt']);
    expect(mockWarn).not.toHaveBeenCalled();
  });

  it('notes once that a live-mount listing may differ from the stored image, and still renders it', async () => {
    mockExecuteRepoFunction.mockResolvedValue({
      success: true,
      exitCode: 0,
      stdout: JSON.stringify({ ...JSON.parse(listingStdout), listingSource: 'live-mount' }),
    });

    await run(['browse', 'shop', '--at', SNAPSHOT]);

    expect(mockWarn).toHaveBeenCalledTimes(1);
    expect(mockWarn.mock.calls[0][0]).toContain('commands.backup.browse.liveMountListing');
    expect(mockWarn.mock.calls[0][0]).toContain(SNAPSHOT);
    expect(mockPrint).toHaveBeenCalledTimes(1);
  });

  it('adds no note for a staged listing', async () => {
    mockExecuteRepoFunction.mockResolvedValue({
      success: true,
      exitCode: 0,
      stdout: JSON.stringify({ ...JSON.parse(listingStdout), listingSource: 'staged' }),
    });

    await run(['browse', 'shop', '--at', SNAPSHOT]);

    expect(mockWarn).not.toHaveBeenCalled();
    expect(mockPrint).toHaveBeenCalledTimes(1);
  });
});
