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
  ValidationError: class ValidationError extends Error {},
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
    await expect(snapshot(['--bwlimit', '100Mb'])).rejects.toThrow(
      /commands\.backup\.strategy\.bandwidthUnconvertible/
    );
    await expect(snapshot(['--parallelism', '0'])).rejects.toThrow(
      /commands\.backup\.snapshot\.parallelismInvalid/
    );
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

describe('backup snapshot carries the read cap and hash parallelism', () => {
  beforeEach(() => {
    mockExecute.mockReset();
    mockExecute.mockResolvedValue({ success: true, exitCode: 0, stdout: '' });
  });

  it('sends --read-bwlimit 50M as bytes/second and --hash-parallelism 1 as a number', async () => {
    await snapshot(['--read-bwlimit', '50M', '--hash-parallelism', '1']);
    expect(sentParams()).toMatchObject({ read_bwlimit: '50000000', hash_parallelism: 1 });
  });

  it('sends --read-bwlimit 0 as the string 0 (unlimited), not as an omission', async () => {
    await snapshot(['--read-bwlimit', '0', '--hash-parallelism', '0']);
    expect(sentParams()).toMatchObject({ read_bwlimit: '0', hash_parallelism: 0 });
  });

  it('sends neither read param when neither flag is given', async () => {
    await snapshot([]);
    const params = sentParams();
    expect(params).not.toHaveProperty('read_bwlimit');
    expect(params).not.toHaveProperty('hash_parallelism');
  });

  it('refuses a bad rate, a blank rate or a bad count before reaching the machine', async () => {
    await expect(snapshot(['--read-bwlimit', '100Mb'])).rejects.toThrow(
      /commands\.backup\.strategy\.readBandwidthUnconvertible/
    );
    await expect(snapshot(['--read-bwlimit', ' '])).rejects.toThrow(
      /commands\.backup\.snapshot\.readBwlimitInvalid/
    );
    await expect(snapshot(['--hash-parallelism', '17'])).rejects.toThrow(
      /commands\.backup\.snapshot\.hashParallelismInvalid/
    );
    await expect(snapshot(['--hash-parallelism', '-1'])).rejects.toThrow(
      /commands\.backup\.snapshot\.hashParallelismInvalid/
    );
    await expect(snapshot(['--hash-parallelism', '1.5'])).rejects.toThrow(
      /commands\.backup\.snapshot\.hashParallelismInvalid/
    );
    expect(mockExecute).not.toHaveBeenCalled();
  });
});

describe('backup snapshot carries the CPU ceiling', () => {
  beforeEach(() => {
    mockExecute.mockReset();
    mockExecute.mockResolvedValue({ success: true, exitCode: 0, stdout: '' });
  });

  it('sends --cpu-limit 30 as the number cpu_limit', async () => {
    await snapshot(['--cpu-limit', '30']);
    expect(sentParams()).toMatchObject({ cpu_limit: 30 });
  });

  it('sends 100, the top of the range', async () => {
    await snapshot(['--cpu-limit', '100']);
    expect(sentParams()).toMatchObject({ cpu_limit: 100 });
  });

  it('omits cpu_limit when the flag is absent, so renet applies its default of 50', async () => {
    await snapshot([]);
    expect(sentParams()).not.toHaveProperty('cpu_limit');
  });

  it.each(['0', '101', '-5', '2.5', 'half', ' '])(
    'refuses --cpu-limit %j before reaching the machine',
    async (value) => {
      await expect(snapshot(['--cpu-limit', value])).rejects.toThrow(
        /commands\.backup\.snapshot\.cpuLimitInvalid/
      );
      expect(mockExecute).not.toHaveBeenCalled();
    }
  );
});

describe('the snapshot summary prints the CPU limit', () => {
  it('names the limit and quota, or says plainly that none was enforced', async () => {
    vi.resetModules();
    vi.doMock('../../utils/errors.js', () => ({
      ValidationError: class ValidationError extends Error {},
      getOutputFormat: () => 'table',
      handleError: (error: unknown) => {
        throw error;
      },
    }));
    const { registerBackupStorageCommands: register } = await import('../backup-storage.js');
    const { outputService } = await import('../../services/core/output.js');
    const { executeRepoFunction } = await import('../../utils/repo-executor.js');
    const run = async (record: object) => {
      vi.mocked(executeRepoFunction).mockResolvedValue({
        success: true,
        exitCode: 0,
        stdout: JSON.stringify({ status: 'ok', ...record }),
      } as never);
      vi.mocked(outputService.info).mockClear();
      const backup = new Command('backup');
      backup.exitOverride();
      register(backup);
      await backup.parseAsync(['snapshot', 'shop'], { from: 'user' });
      return vi.mocked(outputService.info).mock.calls.map((c) => String(c[0]));
    };
    expect(await run({ cpuLimitPercent: 50, cpuQuota: '400%' })).toContain(
      'commands.backup.snapshot.cpuLimit'
    );
    expect(await run({ cpuLimitPercent: 50, cpuQuota: null })).toContain(
      'commands.backup.snapshot.cpuLimitUnenforced'
    );
    const noCeiling = await run({ cpuLimitPercent: 100, cpuQuota: null });
    expect(noCeiling).not.toContain('commands.backup.snapshot.cpuLimitUnenforced');
    expect(noCeiling).not.toContain('commands.backup.snapshot.cpuLimit');
    vi.doUnmock('../../utils/errors.js');
  });
});
