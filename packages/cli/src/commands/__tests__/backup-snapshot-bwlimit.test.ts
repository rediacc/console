import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({ t: (key: string) => key }));

const mockExecute = vi.hoisted(() => vi.fn());

vi.mock('../../services/account/account-client.js', () => ({ accountServerFetch: vi.fn() }));
vi.mock('../../services/core/output.js', () => ({
  outputService: { info: vi.fn(), success: vi.fn(), warn: vi.fn(), error: vi.fn(), print: vi.fn() },
}));
vi.mock('../../services/core/request-context.js', () => ({ setExitCode: vi.fn() }));
vi.mock('../../services/backup/backup-runs-state.js', () => ({ recordBackupRun: vi.fn() }));
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

async function snapshot(args: string[]) {
  const backup = new Command('backup');
  backup.exitOverride();
  registerBackupStorageCommands(backup);
  await backup.parseAsync(['snapshot', 'shop', ...args], { from: 'user' });
}

function sentParams(): Record<string, unknown> {
  expect(mockExecute).toHaveBeenCalledTimes(1);
  const [fn, , , params] = mockExecute.mock.calls[0] as [string, string, string, object];
  expect(fn).toBe('backup_snapshot');
  return params as Record<string, unknown>;
}

// REGRESSION (operator order 2026-10-29): `rdc backup snapshot` had no way to carry a cap, so every ad-hoc chunk upload ran at line rate.
describe('backup snapshot carries the upload cap and parallelism to the renet function', () => {
  beforeEach(() => {
    mockExecute.mockReset();
    mockExecute.mockResolvedValue({ success: true, exitCode: 0, stdout: '' });
  });

  it('sends --bwlimit 100Mbps as bytes/second and --parallelism 2 as a number', async () => {
    await snapshot(['--bwlimit', '100Mbps', '--parallelism', '2']);
    expect(sentParams()).toMatchObject({ bwlimit: '12500000', parallelism: 2 });
  });

  it('reads 12.5M as decimal megabytes, the same as 100Mbps', async () => {
    await snapshot(['--bwlimit', '12.5M']);
    expect(sentParams()).toMatchObject({ bwlimit: '12500000' });
  });

  it('sends neither param when neither flag is given', async () => {
    await snapshot([]);
    const params = sentParams();
    expect(params).not.toHaveProperty('bwlimit');
    expect(params).not.toHaveProperty('parallelism');
  });

  it('refuses an ambiguous rate or a bad parallelism before reaching the machine', async () => {
    await expect(snapshot(['--bwlimit', '100Mb'])).rejects.toThrow(/Bandwidth limit "100Mb"/);
    await expect(snapshot(['--parallelism', '0'])).rejects.toThrow(/--parallelism/);
    expect(mockExecute).not.toHaveBeenCalled();
  });
});

describe('snapshotUploadParams refuses a blank or unparseable --bwlimit', () => {
  it.each(['', '   ', 'fast'])('refuses %j instead of uploading unlimited', async (value) => {
    const { snapshotUploadParams } = await import('../backup-storage.js');
    expect(() => snapshotUploadParams({ bwlimit: value })).toThrow();
  });
  it('leaves the cap off only when --bwlimit is absent', async () => {
    const { snapshotUploadParams } = await import('../backup-storage.js');
    expect(snapshotUploadParams({})).toEqual({});
    expect(snapshotUploadParams({ bwlimit: '100Mbps' })).toEqual({ bwlimit: '12500000' });
  });
});
