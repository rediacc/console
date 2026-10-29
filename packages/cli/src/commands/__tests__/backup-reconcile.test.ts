import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({ t: (key: string) => key }));

const mockFetch = vi.hoisted(() => vi.fn());
const mockPrint = vi.hoisted(() => vi.fn());
const mockSetExitCode = vi.hoisted(() => vi.fn());
const mockWarn = vi.hoisted(() => vi.fn());
const mockFormat = vi.hoisted(() => vi.fn((..._args: unknown[]) => 'TABLE'));
const mockInfo = vi.hoisted(() => vi.fn());
const outputFormat = vi.hoisted(() => ({ value: 'json' }));

vi.mock('../../services/account/account-client.js', () => ({ accountServerFetch: mockFetch }));
vi.mock('../../services/core/output.js', () => ({
  outputService: {
    info: mockInfo,
    warn: mockWarn,
    print: mockPrint,
    format: mockFormat,
  },
}));
vi.mock('../../services/core/request-context.js', () => ({ setExitCode: mockSetExitCode }));
vi.mock('../../utils/errors.js', () => ({
  getOutputFormat: () => outputFormat.value,
  handleError: (error: unknown) => {
    throw error;
  },
}));
vi.mock('../backup-storage-browse.js', () => ({
  resolveLineage: vi.fn().mockResolvedValue('lineage-1'),
}));

import { registerBackupReconcile } from '../backup-reconcile.js';

function lineage(over: Record<string, unknown> = {}) {
  return {
    lineageGuid: 'lineage-1',
    ledgerBytesBefore: 100,
    ledgerChunksBefore: 4,
    observedBytes: 100,
    observedChunks: 4,
    referencedBytes: 100,
    referencedChunks: 4,
    unreferencedBytes: 0,
    unreferencedChunks: 0,
    unreferencedPastGraceChunks: 0,
    applied: false,
    skipped: null,
    ...over,
  };
}

function response(
  over: {
    lineage?: Record<string, unknown>;
    driftBytes?: number;
    lineages?: ReturnType<typeof lineage>[];
    truncated?: boolean;
  } = {}
) {
  return {
    subscriptionId: 'sub-1',
    ...(over.truncated === undefined ? {} : { truncated: over.truncated }),
    lineages: over.lineages ?? [lineage(over.lineage)],
    ledgerBytes: 100,
    ledgerChunkCount: 4,
    bucketChunkBytes: 100,
    bucketChunkCount: 4,
    driftBytes: over.driftBytes ?? 0,
  };
}

async function run(args: string[]) {
  const backup = new Command('backup');
  registerBackupReconcile(backup);
  await backup.parseAsync(['reconcile', ...args], { from: 'user' });
}

const sentBodies = () => mockFetch.mock.calls.map((c) => (c[1] as { body: unknown }).body);

describe('backup reconcile', () => {
  beforeEach(() => {
    mockFetch.mockReset();
    mockPrint.mockReset();
    mockSetExitCode.mockReset();
    mockWarn.mockReset();
    mockInfo.mockReset();
    mockFormat.mockClear();
    outputFormat.value = 'json';
  });

  it('posts the resolved lineage and dryRun', async () => {
    mockFetch.mockResolvedValue(response());
    await run(['shop']);
    expect(mockFetch).toHaveBeenCalledWith(
      '/account/api/v1/backups/reconcile',
      expect.objectContaining({ method: 'POST' })
    );
    expect(sentBodies()).toEqual([{ lineageGuid: 'lineage-1', dryRun: false }]);
    await run(['shop', '--dry-run']);
    expect(sentBodies()[1]).toEqual({ lineageGuid: 'lineage-1', dryRun: true });
  });

  it('omits the lineage when no repo-ref is given', async () => {
    mockFetch.mockResolvedValue(response());
    await run(['--dry-run']);
    expect(sentBodies()).toEqual([{ dryRun: true }]);
  });

  it('--check exits 1 on a drifting lineage and 0 on a clean one', async () => {
    mockFetch.mockResolvedValue(response({ lineage: { observedBytes: 40, observedChunks: 2 } }));
    await run(['shop', '--check']);
    expect(mockSetExitCode).toHaveBeenCalledWith(1);

    mockSetExitCode.mockReset();
    mockFetch.mockResolvedValue(response({ driftBytes: 7 }));
    await run(['shop', '--check']);
    expect(mockSetExitCode).toHaveBeenCalledWith(1);

    mockSetExitCode.mockReset();
    mockFetch.mockResolvedValue(response());
    await run(['shop', '--check']);
    expect(mockSetExitCode).not.toHaveBeenCalled();
  });

  it('never sends dryRun:false with --check or --dry-run', async () => {
    mockFetch.mockResolvedValue(response());
    await run(['shop', '--check']);
    await run(['shop', '--dry-run']);
    await run(['shop', '--check', '--dry-run']);
    expect(sentBodies()).toHaveLength(3);
    for (const body of sentBodies()) expect(body).toMatchObject({ dryRun: true });
  });

  it('prints the server response for json output', async () => {
    const res = response();
    mockFetch.mockResolvedValue(res);
    await run(['shop']);
    expect(mockPrint).toHaveBeenCalledWith(res, 'json');
  });

  it('--check ignores a skipped lineage, even one whose figures differ, and names it', async () => {
    outputFormat.value = 'table';
    const skipped = lineage({
      lineageGuid: 'busy-1',
      observedBytes: 0,
      observedChunks: 0,
      skipped: 'leased',
    });
    mockFetch.mockResolvedValue(response({ lineages: [lineage(), skipped], driftBytes: 100 }));
    await run(['--check']);
    expect(mockSetExitCode).not.toHaveBeenCalled();
    expect(mockWarn).toHaveBeenCalledWith('commands.backup.reconcile.checkSkipped');
    const rows = mockFormat.mock.calls[0][0] as { lineage: string; status: string }[];
    expect(rows.find((r) => r.lineage === 'busy-1')?.status).toBe(
      'commands.backup.reconcile.skipped.leased'
    );
  });

  it('--check still fails on a reconcilable lineage next to a skipped one', async () => {
    mockFetch.mockResolvedValue(
      response({
        lineages: [
          lineage({ observedBytes: 40, observedChunks: 2 }),
          lineage({ lineageGuid: 'busy-1', skipped: 'unreadable' }),
        ],
      })
    );
    await run(['--check']);
    expect(mockSetExitCode).toHaveBeenCalledWith(1);
  });

  it('--check fails when only driftBytes is non-zero and nothing was skipped', async () => {
    mockFetch.mockResolvedValue(response({ driftBytes: -5 }));
    await run(['--check']);
    expect(mockSetExitCode).toHaveBeenCalledWith(1);
  });

  it('table output renders rows and the summary, and warns when truncated', async () => {
    outputFormat.value = 'table';
    mockFetch.mockResolvedValue(response({ truncated: true }));
    await run(['shop']);
    expect(mockWarn).toHaveBeenCalledWith('commands.backup.reconcile.truncated');
    expect(mockFormat).toHaveBeenCalledWith(
      [
        expect.objectContaining({
          lineage: 'lineage-1',
          status: 'commands.backup.reconcile.status.clean',
        }),
      ],
      'table',
      expect.any(Array)
    );
    expect(mockPrint).toHaveBeenCalledWith('TABLE');
    expect(mockInfo).toHaveBeenCalledWith('commands.backup.reconcile.summary');
  });

  it('table output does not warn when the response is complete, and prints empty', async () => {
    outputFormat.value = 'table';
    mockFetch.mockResolvedValue(response({ lineages: [] }));
    await run(['shop']);
    expect(mockWarn).not.toHaveBeenCalled();
    expect(mockPrint).toHaveBeenCalledWith('commands.backup.reconcile.empty');
  });
});
