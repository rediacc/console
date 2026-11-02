import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({ t: (key: string) => key }));

const mockFetch = vi.hoisted(() => vi.fn());
const mockPrint = vi.hoisted(() => vi.fn());
const mockSetExitCode = vi.hoisted(() => vi.fn());
const mockRecord = vi.hoisted(() => vi.fn());
const mockExecute = vi.hoisted(() => vi.fn());

// These verbs read the hosted backup plane, which needs a login (PLAN-free-license R13); a logged-in operator is the case under test.
vi.mock('../../services/account/subscription-auth.js', () => ({
  getSubscriptionTokenState: () => ({
    kind: 'ready',
    token: { token: 't' },
    serverUrl: 'https://acct.example',
  }),
  getSubscriptionServerUrl: () => 'https://acct.example',
}));
vi.mock('../../services/account/account-client.js', () => ({ accountServerFetch: mockFetch }));
vi.mock('../../services/core/output.js', () => ({
  outputService: {
    info: vi.fn(),
    success: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
    print: mockPrint,
  },
}));
vi.mock('../../services/core/request-context.js', () => ({ setExitCode: mockSetExitCode }));
vi.mock('../../services/backup/backup-runs-state.js', () => ({ recordBackupRun: mockRecord }));
vi.mock('../../utils/errors.js', () => ({
  getOutputFormat: () => 'json',
  handleError: (error: unknown) => {
    throw error;
  },
}));
vi.mock('../../utils/repo-executor.js', () => ({ executeRepoFunction: mockExecute }));
vi.mock('../../utils/repo-target.js', () => ({
  resolveRepoRef: vi.fn().mockResolvedValue({ repoKey: 'shop', machineName: 'm1' }),
  resolveRepoRefLocal: vi.fn().mockResolvedValue({ repoKey: 'shop' }),
}));
vi.mock('../backup-storage-browse.js', () => ({
  RENET_NO_LISTING_EXIT: 18,
  resolveLineage: vi.fn().mockResolvedValue('lineage-1'),
  runBrowseAt: vi.fn(),
}));

import { registerBackupStorageCommands } from '../backup-storage.js';

const H = (c: string) => c.repeat(64);

function page(
  checked: number,
  nextAfter: string | null,
  missing: string[] = [],
  corrupt: string[] = []
) {
  return {
    subscriptionId: 'sub-1',
    chunks: { lineageGuid: 'lineage-1', checked, missing, corrupt, nextAfter },
  };
}

async function run(args: string[]) {
  const backup = new Command('backup');
  registerBackupStorageCommands(backup);
  await backup.parseAsync(['verify', ...args], { from: 'user' });
}

describe('backup verify --store', () => {
  beforeEach(() => {
    mockFetch.mockReset();
    mockPrint.mockReset();
    mockSetExitCode.mockReset();
    mockRecord.mockReset();
    mockExecute.mockReset();
  });

  it('walks the cursor to the end and merges every page; a clean store exits 0', async () => {
    mockFetch.mockResolvedValueOnce(page(200, H('a'))).mockResolvedValueOnce(page(5, null));
    await run(['shop', '--store']);

    expect(mockFetch).toHaveBeenCalledTimes(2);
    const [path, first] = mockFetch.mock.calls[0] as [string, { method: string; body: unknown }];
    expect(path).toBe('/account/api/v1/backups/verify');
    expect(first.method).toBe('POST');
    expect(first.body).toEqual({ lineageGuid: 'lineage-1', level: 'chunks', after: undefined });
    const second = mockFetch.mock.calls[1][1] as { body: unknown };
    expect(second.body).toEqual({ lineageGuid: 'lineage-1', level: 'chunks', after: H('a') });

    expect(mockPrint).toHaveBeenCalledWith(
      { lineageGuid: 'lineage-1', checked: 205, missing: [], corrupt: [] },
      'json'
    );
    expect(mockSetExitCode).not.toHaveBeenCalled();
    expect(mockRecord).toHaveBeenCalledWith('shop', { kind: 'verify', status: 'verified' });
    // The store verify is a control-plane call: no machine is reached.
    expect(mockExecute).not.toHaveBeenCalled();
  });

  it('names corrupt and missing hashes and exits 1', async () => {
    mockFetch
      .mockResolvedValueOnce(page(200, H('a'), [], [H('b')]))
      .mockResolvedValueOnce(page(3, null, [H('c')], []));
    await run(['shop', '--store']);

    expect(mockPrint).toHaveBeenCalledWith(
      { lineageGuid: 'lineage-1', checked: 203, missing: [H('c')], corrupt: [H('b')] },
      'json'
    );
    expect(mockSetExitCode).toHaveBeenCalledWith(1);
    expect(mockRecord).toHaveBeenCalledWith('shop', { kind: 'verify', status: 'mismatch' });
  });

  it('refuses a cursor that does not advance instead of looping', async () => {
    mockFetch.mockResolvedValue(page(1, H('a')));
    await expect(run(['shop', '--store'])).rejects.toThrow(/repeated cursor/);
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  it('refuses a server that cycles through cursors (A, B, A) instead of looping', async () => {
    mockFetch
      .mockResolvedValueOnce(page(1, H('a')))
      .mockResolvedValueOnce(page(1, H('b')))
      .mockResolvedValue(page(1, H('a')));
    await expect(run(['shop', '--store'])).rejects.toThrow(/repeated cursor a{64}/);
    expect(mockFetch).toHaveBeenCalledTimes(3);
  });

  it('a lineage with no stored chunks is neither verified nor exit 0', async () => {
    mockFetch.mockResolvedValueOnce(page(0, null));
    await run(['shop', '--store']);

    expect(mockSetExitCode).toHaveBeenCalledWith(1);
    expect(mockRecord).toHaveBeenCalledWith('shop', { kind: 'verify', status: 'empty' });
    expect(mockRecord).not.toHaveBeenCalledWith(
      'shop',
      expect.objectContaining({ status: 'verified' })
    );
  });

  it('without --store, still runs the machine-side verb and never calls the server verify', async () => {
    mockExecute.mockResolvedValue({
      success: true,
      stdout: '{"status":"verified","level":"spot"}',
    });
    await run(['shop']);
    expect(mockExecute).toHaveBeenCalledWith(
      'backup_verify',
      'shop',
      'm1',
      { level: 'spot' },
      expect.anything(),
      expect.anything()
    );
    expect(mockFetch).not.toHaveBeenCalled();
  });
});
