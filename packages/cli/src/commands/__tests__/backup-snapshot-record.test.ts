import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: object) => (params ? `${key} ${JSON.stringify(params)}` : key),
}));

const mockExecute = vi.hoisted(() => vi.fn());
const state = vi.hoisted(() => ({ format: 'table' }));

vi.mock('../../services/account/account-client.js', () => ({ accountServerFetch: vi.fn() }));
vi.mock('../../services/core/output.js', () => ({
  outputService: { info: vi.fn(), success: vi.fn(), warn: vi.fn(), error: vi.fn(), print: vi.fn() },
}));
vi.mock('../../services/core/request-context.js', () => ({ setExitCode: vi.fn() }));
vi.mock('../../services/backup/backup-runs-state.js', () => ({ recordBackupRun: vi.fn() }));
vi.mock('../../utils/errors.js', () => ({
  ValidationError: class ValidationError extends Error {},
  getOutputFormat: () => state.format,
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

import { outputService } from '../../services/core/output.js';
import { setExitCode } from '../../services/core/request-context.js';
import { registerBackupStorageCommands } from '../backup-storage.js';

const record = {
  guid: 'g1',
  status: 'stored',
  snapshotId: 'snap-42',
  imageBytes: 1048576,
  rehashReason: 'anchor-missing',
  readCapBps: 52428800,
  hashWorkers: 3,
  chunksUploaded: 7,
  bytesUploaded: 2048,
  durationMs: 1500,
};

async function snapshot(args: string[] = []) {
  const backup = new Command('backup');
  backup.exitOverride();
  registerBackupStorageCommands(backup);
  await backup.parseAsync(['snapshot', 'shop', ...args], { from: 'user' });
}

function infoText(): string {
  return vi
    .mocked(outputService.info)
    .mock.calls.map((c) => String(c[0]))
    .join('\n');
}

// REGRESSION: `rdc backup snapshot` returned 0 and printed nothing of renet's record, so the read cap, hash workers and rehash reason could not be observed.
describe('backup snapshot prints the record renet emits', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    state.format = 'table';
    mockExecute.mockResolvedValue({
      success: true,
      exitCode: 0,
      stdout: `time="x" level=info msg="hi"\n${JSON.stringify(record)}\n`,
    });
  });

  it('captures renet output', async () => {
    await snapshot();
    expect(mockExecute.mock.calls[0][4]).toMatchObject({ captureOutput: true });
  });

  it('table output carries the read cap, hash workers, id and rehash reason', async () => {
    await snapshot();
    const text = infoText();
    expect(text).toContain('snap-42');
    expect(text).toContain('anchor-missing');
    expect(text).toContain('50.0 MB');
    expect(text).toContain('"workers":3');
  });

  it('an unlimited read cap (0) prints "unlimited", an absent one prints nothing', async () => {
    const withCap = (cap: number | undefined) => ({ ...record, readCapBps: cap });
    mockExecute.mockResolvedValue({
      success: true,
      exitCode: 0,
      stdout: `${JSON.stringify(withCap(0))}\n`,
    });
    await snapshot();
    expect(infoText()).toContain('commands.backup.snapshot.readCapUnlimited');
    vi.mocked(outputService.info).mockClear();
    mockExecute.mockResolvedValue({
      success: true,
      exitCode: 0,
      stdout: `${JSON.stringify(withCap(undefined))}\n`,
    });
    await snapshot();
    expect(infoText()).not.toContain('readCap');
  });

  it('json output is the record', async () => {
    state.format = 'json';
    await snapshot();
    expect(outputService.print).toHaveBeenCalledWith(record, 'json');
  });

  it('a missing record still exits 0 and prints nothing', async () => {
    mockExecute.mockResolvedValue({ success: true, exitCode: 0, stdout: '' });
    await expect(snapshot()).resolves.toBeUndefined();
    expect(outputService.print).not.toHaveBeenCalled();
    expect(outputService.info).not.toHaveBeenCalled();
    expect(setExitCode).not.toHaveBeenCalled();
  });

  it('a quota refusal keeps exit 16 and prints no record', async () => {
    mockExecute.mockResolvedValue({ success: false, exitCode: 16, stdout: JSON.stringify(record) });
    await snapshot();
    expect(setExitCode).toHaveBeenCalledWith(16);
    expect(outputService.info).not.toHaveBeenCalled();
  });
});
