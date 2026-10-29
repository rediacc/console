import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({ t: (key: string) => key }));

const mockFetch = vi.hoisted(() => vi.fn());
const mockPrint = vi.hoisted(() => vi.fn());
const mockSetExitCode = vi.hoisted(() => vi.fn());

vi.mock('../../services/account/account-client.js', () => ({ accountServerFetch: mockFetch }));
vi.mock('../../services/core/output.js', () => ({
  outputService: {
    info: vi.fn(),
    warn: vi.fn(),
    print: mockPrint,
    format: vi.fn(() => 'TABLE'),
  },
}));
vi.mock('../../services/core/request-context.js', () => ({ setExitCode: mockSetExitCode }));
vi.mock('../../utils/errors.js', () => ({
  getOutputFormat: () => 'json',
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

function response(over: { lineage?: Record<string, unknown>; driftBytes?: number } = {}) {
  return {
    subscriptionId: 'sub-1',
    lineages: [lineage(over.lineage)],
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
});
