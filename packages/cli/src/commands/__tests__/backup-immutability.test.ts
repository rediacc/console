/**
 * `backup immutability show|set`, `backup undelete`, `backup purge --cancel`, and the way every
 * delete verb reports a delayed answer (D-immutable, decision O4).
 *
 * What this protects is delayed deletion, not immutability: a delete under a window is held for
 * `immutableDays` and can be undone until then. The failure that matters is a verb that reads the
 * server's 202 ("held, not deleted") as a completed delete, because the operator then believes
 * the data is gone while it is still stored and charged, or believes a shortened window already
 * protects less than it does.
 */

import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key} ${JSON.stringify(params)}` : key,
}));

const mockFetch = vi.hoisted(() => vi.fn());
vi.mock('../../services/account/subscription-auth.js', () => ({
  getSubscriptionTokenState: () => ({
    kind: 'ready',
    token: { token: 't' },
    serverUrl: 'https://acct.example',
  }),
  getSubscriptionServerUrl: () => 'https://acct.example',
}));
vi.mock('../../services/account/account-client.js', () => ({ accountServerFetch: mockFetch }));

const mockInfo = vi.hoisted(() => vi.fn());
const mockSuccess = vi.hoisted(() => vi.fn());
const mockWarn = vi.hoisted(() => vi.fn());
const mockPrint = vi.hoisted(() => vi.fn());
vi.mock('../../services/core/output.js', () => ({
  outputService: {
    info: mockInfo,
    success: mockSuccess,
    warn: mockWarn,
    error: vi.fn(),
    print: mockPrint,
  },
}));

const outputFormat = vi.hoisted(() => ({ value: 'table' }));
vi.mock('../../utils/errors.js', async () => {
  const actual =
    await vi.importActual<typeof import('../../utils/errors.js')>('../../utils/errors.js');
  return {
    ...actual,
    getOutputFormat: () => outputFormat.value,
    handleError: (e: unknown) => {
      throw e;
    },
  };
});

vi.mock('../backup-storage-browse.js', () => ({
  resolveLineage: vi.fn().mockResolvedValue('lin-1'),
  lineageOf: (r: { grandGuid?: string; repositoryGuid: string }) => r.grandGuid ?? r.repositoryGuid,
}));
vi.mock('../../utils/guid-resolver.js', () => ({
  loadGuidMap: () => Promise.resolve({}),
  createGuidResolver: () => (guid: string) => guid,
}));

const { registerBackupImmutability } = await import('../backup-immutability.js');
const { registerBackupSnapshots } = await import('../backup-retention-commands.js');

async function run(argv: string[]): Promise<void> {
  const program = new Command();
  program.exitOverride();
  const backup = program.command('backup');
  registerBackupImmutability(backup);
  registerBackupSnapshots(backup);
  await program.parseAsync(['node', 'rdc', 'backup', ...argv]);
}

const text = (mock: ReturnType<typeof vi.fn>) =>
  mock.mock.calls.map((c) => String(c[0])).join('\n');
const IMMUTABILITY = '/account/api/v1/backups/immutability';

beforeEach(() => {
  vi.clearAllMocks();
  mockFetch.mockReset();
  outputFormat.value = 'table';
});

describe('backup immutability show', () => {
  it('reads the window in force from the server', async () => {
    mockFetch.mockResolvedValue({ immutableDays: 7, pendingDays: null, shortenAfter: null });
    await run(['immutability', 'show']);

    expect(mockFetch).toHaveBeenCalledWith(IMMUTABILITY);
    expect(text(mockInfo)).toContain('commands.backup.immutability.show.window');
    expect(text(mockInfo)).toContain('"days":7');
  });

  it('says a window of 0 is no delay, not "delayed by zero"', async () => {
    mockFetch.mockResolvedValue({ immutableDays: 0, pendingDays: null, shortenAfter: null });
    await run(['immutability', 'show']);

    expect(text(mockInfo)).toContain('commands.backup.immutability.show.off');
  });

  it('names when a shortened window takes effect, and keeps the old one in force until then', async () => {
    mockFetch.mockResolvedValue({
      immutableDays: 7,
      pendingDays: 1,
      shortenAfter: '2026-11-09T08:00:00.000Z',
    });
    await run(['immutability', 'show']);

    expect(text(mockInfo)).toContain('"days":7');
    const warned = text(mockWarn);
    expect(warned).toContain('commands.backup.immutability.pending');
    expect(warned).toContain('"days":1');
    expect(warned).toContain('2026-11-09 08:00');
  });

  it('prints the whole record in -o json', async () => {
    outputFormat.value = 'json';
    const record = { immutableDays: 7, pendingDays: 1, shortenAfter: '2026-11-09T08:00:00.000Z' };
    mockFetch.mockResolvedValue(record);
    await run(['immutability', 'show']);

    expect(mockPrint).toHaveBeenCalledWith(record, 'json');
  });
});

describe('backup immutability set', () => {
  it('sends whole days as a number', async () => {
    mockFetch.mockResolvedValue({ immutableDays: 14, pendingDays: null, shortenAfter: null });
    await run(['immutability', 'set', '14']);

    const [url, init] = mockFetch.mock.calls[0] as [string, { method: string; body: unknown }];
    expect(url).toBe(IMMUTABILITY);
    expect(init.method).toBe('PUT');
    expect(init.body).toEqual({ immutableDays: 14 });
  });

  it('says a raise applies at once', async () => {
    mockFetch.mockResolvedValue({ immutableDays: 14, pendingDays: null, shortenAfter: null });
    await run(['immutability', 'set', '14']);

    expect(text(mockSuccess)).toContain('commands.backup.immutability.set.applied');
    expect(text(mockWarn)).not.toContain('commands.backup.immutability.pending');
  });

  it('says when a shortening takes effect instead of claiming it applied', async () => {
    mockFetch.mockResolvedValue({
      immutableDays: 7,
      pendingDays: 0,
      shortenAfter: '2026-11-09T08:00:00.000Z',
    });
    await run(['immutability', 'set', '0']);

    // THE DEFECT: "window is now 0 days" printed while the server still holds the old 7.
    expect(text(mockSuccess)).not.toContain('commands.backup.immutability.set.applied');
    const warned = text(mockWarn);
    expect(warned).toContain('commands.backup.immutability.pending');
    expect(warned).toContain('2026-11-09 08:00');
    expect(warned).toContain('"current":7');
  });

  it.each(['-1', '31', '1.5', 'week', ''])('refuses %j before any call', async (days) => {
    await expect(run(['immutability', 'set', days])).rejects.toThrow(
      'commands.backup.immutability.set.invalid'
    );
    expect(mockFetch).not.toHaveBeenCalled();
  });
});

describe('backup undelete', () => {
  it('restores a delayed delete through the undelete route', async () => {
    mockFetch.mockResolvedValue({ snapshotId: 'snap-1', undeleted: true });
    await run(['undelete', 'snap-1']);

    const [url, init] = mockFetch.mock.calls[0] as [string, { method: string }];
    expect(url).toBe('/account/api/v1/backups/snapshots/snap-1/undelete');
    expect(init.method).toBe('POST');
    expect(text(mockSuccess)).toContain('commands.backup.undelete.success');
  });

  it('says so when the snapshot was not waiting for deletion', async () => {
    mockFetch.mockResolvedValue({ snapshotId: 'snap-1', undeleted: false });
    await run(['undelete', 'snap-1']);

    expect(text(mockSuccess)).not.toContain('commands.backup.undelete.success');
    expect(text(mockInfo)).toContain('commands.backup.undelete.notWaiting');
  });

  it('lets the server refusal of a final delete through unchanged', async () => {
    mockFetch.mockRejectedValue(
      Object.assign(
        new Error('Snapshot snap-1 cannot be undeleted: its deletion is already final'),
        {
          status: 404,
        }
      )
    );
    await expect(run(['undelete', 'snap-1'])).rejects.toThrow('already final');
  });
});

describe('backup snapshots delete under a delayed-deletion window', () => {
  const owned = { snapshotId: 'snap-1', lineageGuid: 'lin-1' };

  beforeEach(() => {
    mockFetch.mockImplementation((path: string) =>
      Promise.resolve(path.includes('/snapshots/resolve') ? owned : { deleted: ['snap-1'] })
    );
  });

  async function deleteWith(answer: Record<string, unknown>): Promise<void> {
    mockFetch.mockImplementation((path: string) =>
      Promise.resolve(path.includes('/snapshots/resolve') ? owned : answer)
    );
    await run(['snapshots', 'delete', 'shop', 'snap-1']);
  }

  it('window 0: the 200 says deleted', async () => {
    await deleteWith({ deleted: ['snap-1'] });

    expect(text(mockSuccess)).toContain('commands.backup.snapshots.delete.success');
    expect(text(mockWarn)).not.toContain('delayed');
  });

  it('window 7: the 202 says delayed, with the due time and the way back, never "deleted"', async () => {
    await deleteWith({
      deleted: [],
      delayed: true,
      code: 'BACKUP_DELETION_DELAYED',
      deleteAfter: '2026-11-09T08:00:00.000Z',
    });

    // THE DEFECT: success text for a 202 whose `deleted` list is empty ("Deleted 0 snapshot(s)").
    expect(text(mockSuccess)).not.toContain('commands.backup.snapshots.delete.success');
    const info = text(mockInfo) + text(mockWarn);
    expect(info).toContain('commands.backup.snapshots.delete.delayed');
    expect(info).toContain('2026-11-09 08:00');
    expect(info).toContain('snap-1');
  });

  it('prints the answer untouched in -o json', async () => {
    outputFormat.value = 'json';
    const answer = {
      deleted: [],
      delayed: true,
      code: 'BACKUP_DELETION_DELAYED',
      deleteAfter: 'x',
    };
    await deleteWith(answer);

    expect(mockPrint).toHaveBeenCalledWith(answer, 'json');
  });
});
