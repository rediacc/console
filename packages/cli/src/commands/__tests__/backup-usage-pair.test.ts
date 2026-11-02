/**
 * `backup usage` and `backup manifests` after the waiting ledger (D-ledger, D-safeguard).
 *
 * Quota counts what kept versions can restore (`liveBytes`), and chunks waiting out their grace
 * are Rediacc's to absorb. A usage line that kept printing only the physical total would show a
 * customer a figure that is neither what they are charged nor what they could free, and a capped
 * stream would be refused with no word on the screen saying why.
 */

import { Command } from 'commander';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

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
vi.mock('../../utils/repo-executor.js', () => ({ executeRepoFunction: vi.fn() }));
vi.mock('../../utils/repo-target.js', () => ({
  resolveRepoRef: vi.fn(),
  resolveRepoRefLocal: vi.fn().mockResolvedValue({ repoKey: 'shop', name: 'shop' }),
}));
vi.mock('../../services/backup/backup-runs-state.js', () => ({ recordBackupRun: vi.fn() }));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getRepository: vi.fn().mockResolvedValue({ repositoryGuid: 'r1', grandGuid: 'lin-1' }),
  },
}));
vi.mock('../../utils/guid-resolver.js', () => ({
  loadGuidMap: () => Promise.resolve({}),
  createGuidResolver: () => (guid: string) => (guid === 'lin-1' ? 'shop' : guid),
}));

const mockInfo = vi.hoisted(() => vi.fn());
const mockWarn = vi.hoisted(() => vi.fn());
const mockPrint = vi.hoisted(() => vi.fn());
vi.mock('../../services/core/output.js', () => ({
  outputService: {
    info: mockInfo,
    success: vi.fn(),
    warn: mockWarn,
    error: vi.fn(),
    print: mockPrint,
    format: (rows: unknown) => JSON.stringify(rows),
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

const { registerBackupStorageCommands } = await import('../backup-storage.js');

async function run(argv: string[]): Promise<void> {
  const program = new Command();
  program.exitOverride();
  const backup = program.command('backup');
  registerBackupStorageCommands(backup);
  await program.parseAsync(['node', 'rdc', 'backup', ...argv]);
}

const GIB = 1024 ** 3;
const usage = (over: Record<string, unknown> = {}) => ({
  subscriptionId: 's1',
  storedBytes: 12 * GIB,
  liveBytes: 9 * GIB,
  waitingBytes: 3 * GIB,
  waitingChunks: 700,
  churnCapBytes: 20 * GIB,
  churnCapped: false,
  chunkCount: 3000,
  usageAdjustment: 0,
  leasedBytes: 0,
  activeLeases: 0,
  usedBytes: 9 * GIB,
  quotaBytes: 10 * GIB,
  overLimit: false,
  retentionStartedAt: null,
  lineages: [
    {
      lineageGuid: 'lin-1',
      storedBytes: 12 * GIB,
      liveBytes: 9 * GIB,
      waitingBytes: 3 * GIB,
      chunkCount: 3000,
      logicalBytes: 20 * GIB,
      updatedAt: '2026-11-02T10:00:00.000Z',
    },
  ],
  ...over,
});

const infoText = () => mockInfo.mock.calls.map((c) => String(c[0])).join('\n');
const warnText = () => mockWarn.mock.calls.map((c) => String(c[0])).join('\n');
const printedText = () => mockPrint.mock.calls.map((c) => String(c[0])).join('\n');

beforeEach(() => {
  vi.clearAllMocks();
  mockFetch.mockReset();
  outputFormat.value = 'table';
});

afterEach(() => {
  process.exitCode = 0;
});

describe('backup usage: live and waiting', () => {
  it('prints what is charged (live), what waits, and the cap, in the table', async () => {
    mockFetch.mockResolvedValue(usage());
    await run(['usage']);

    // THE DEFECT: only the physical total shown, so the charged figure and the waiting pool are invisible.
    const info = infoText();
    expect(info).toContain('commands.backup.usage.summary');
    expect(info).toContain('commands.backup.usage.waiting');
    // 9 GiB is the charged (live) figure and 3 GiB the waiting one; the cap is 20 GiB.
    expect(info).toContain('"live":"9G"');
    expect(info).toContain('"waiting":"3G"');
    expect(info).toContain('"cap":"20G"');
    expect(info).toContain('"chunks":700');
  });

  it('shows live and waiting per repository', async () => {
    mockFetch.mockResolvedValue(usage());
    await run(['usage']);

    const rows = printedText();
    expect(rows).toContain('"live"');
    expect(rows).toContain('"waiting"');
  });

  it('says plainly when the churn cap is reached and a fast stream is refused', async () => {
    mockFetch.mockResolvedValue(usage({ churnCapped: true, waitingBytes: 21 * GIB }));
    await run(['usage']);

    expect(warnText()).toContain('commands.backup.usage.throttled');
  });

  it('is quiet about the cap while it is not reached', async () => {
    mockFetch.mockResolvedValue(usage());
    await run(['usage']);

    expect(warnText()).not.toContain('commands.backup.usage.throttled');
  });

  it.each(['json', 'yaml'])('carries every pair field untouched in -o %s', async (format) => {
    outputFormat.value = format;
    mockFetch.mockResolvedValue(usage({ churnCapped: true }));
    await run(['usage']);

    const [payload, used] = mockPrint.mock.calls[0] as [Record<string, unknown>, string];
    expect(used).toBe(format);
    expect(payload).toMatchObject({
      liveBytes: 9 * GIB,
      waitingBytes: 3 * GIB,
      waitingChunks: 700,
      churnCapBytes: 20 * GIB,
      churnCapped: true,
    });
    expect((payload.lineages as Record<string, unknown>[])[0]).toMatchObject({
      liveBytes: 9 * GIB,
      waitingBytes: 3 * GIB,
    });
  });

  it('prints no waiting line on a server that reports none (zero is still a number)', async () => {
    mockFetch.mockResolvedValue(usage({ waitingBytes: 0, waitingChunks: 0, liveBytes: 12 * GIB }));
    await run(['usage']);

    expect(infoText()).toContain('commands.backup.usage.summary');
    expect(infoText()).not.toContain('commands.backup.usage.waiting');
  });
});

describe('backup manifests: consistency, tombstones and pages', () => {
  const row = (over: Record<string, unknown>) => ({
    snapshotId: '20261102T100000Z-aaaaaaaaaaaaaaaa',
    lineageGuid: 'lin-1',
    streamId: 's1',
    parentSnapshotId: null,
    cellSizeBytes: 4_194_304,
    totalBytes: GIB,
    addedBytes: 1024,
    addedChunkCount: 1,
    hasIndex: true,
    createdAt: '2026-11-02T10:00:00.000Z',
    consistency: 'app-quiesced',
    deletedAt: null,
    deleteAfter: null,
    ...over,
  });

  it('shows what each snapshot declared about its consistency', async () => {
    mockFetch.mockResolvedValue({
      manifests: [
        row({}),
        row({ snapshotId: 'b', consistency: 'crash-consistent' }),
        row({ snapshotId: 'c', consistency: null }),
      ],
      nextBefore: null,
    });
    await run(['manifests', 'shop']);

    const rows = printedText();
    expect(rows).toContain('"consistency":"app-quiesced"');
    expect(rows).toContain('"consistency":"crash-consistent"');
    expect(rows).toContain('"consistency":"-"');
  });

  it('marks a delayed delete as still restorable until its due time', async () => {
    mockFetch.mockResolvedValue({
      manifests: [
        row({
          snapshotId: 'gone',
          deletedAt: '2026-11-02T11:00:00.000Z',
          deleteAfter: '2026-11-09T11:00:00.000Z',
        }),
      ],
      nextBefore: null,
    });
    await run(['manifests', 'shop', '--include-deleted']);

    expect(printedText()).toContain('"state":"deleting after 2026-11-09 11:00"');
  });

  it('asks for tombstones, a page size and a cursor only when told to', async () => {
    mockFetch.mockResolvedValue({ manifests: [], nextBefore: null });
    await run(['manifests', 'shop']);
    expect(mockFetch).toHaveBeenLastCalledWith('/account/api/v1/backups/manifests?lineage=lin-1');

    await run([
      'manifests',
      'shop',
      '--include-deleted',
      '--limit',
      '25',
      '--before',
      '2026-11-02T10:00:00.000Z~snap',
    ]);
    const url = String(mockFetch.mock.calls.at(-1)?.[0]);
    const q = new URL(url, 'https://x').searchParams;
    expect(q.get('includeDeleted')).toBe('1');
    expect(q.get('limit')).toBe('25');
    expect(q.get('before')).toBe('2026-11-02T10:00:00.000Z~snap');
  });

  it('says how to read the next page when the listing is cut at the cap', async () => {
    mockFetch.mockResolvedValue({
      manifests: [row({})],
      nextBefore: '2026-11-02T10:00:00.000Z~snap',
      total: 900,
    });
    await run(['manifests', 'shop']);

    const info = infoText();
    expect(info).toContain('commands.backup.manifests.more');
    expect(info).toContain('2026-11-02T10:00:00.000Z~snap');
    expect(info).toContain('"total":900');
  });

  it('refuses a limit that is not a whole number before any call', async () => {
    await expect(run(['manifests', 'shop', '--limit', 'many'])).rejects.toThrow(
      'commands.backup.manifests.limitInvalid'
    );
    expect(mockFetch).not.toHaveBeenCalled();
  });
});
