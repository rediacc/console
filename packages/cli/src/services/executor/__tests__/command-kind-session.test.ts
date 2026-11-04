/**
 * PLAN-detached-jobs section 14: a command-kind job brings renet to the machine with the access its kind needs and
 * starts the job with an empty vault, with none of the function-session work (verify, license, converge).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockAcquire = vi.hoisted(() => vi.fn());
const mockRun = vi.hoisted(() => vi.fn());
vi.mock('../../renet/renet-execution.js', () => ({ acquireRemoteRenet: mockAcquire }));
vi.mock('../detached-execution.js', () => ({ runJobExecution: mockRun }));

const { commandKindAccess, runCommandKindSession } = await import('../command-kind-session.js');

const MACHINE = { ip: '10.0.0.1', user: 'u' } as never;
const SFTP = {} as never;

beforeEach(() => {
  vi.clearAllMocks();
  mockAcquire.mockResolvedValue({ remotePath: '/usr/bin/renet', uploaded: false, drift: null });
  mockRun.mockResolvedValue({ success: true, exitCode: 0, durationMs: 1, state: 'succeeded' });
});

describe('commandKindAccess', () => {
  it('provisions renet for the kinds that change the machine and reads for the rest', () => {
    expect(commandKindAccess('setup')).toBe('provision');
    expect(commandKindAccess('backup-unit')).toBe('provision');
    expect(commandKindAccess('daemons-restart')).toBe('provision');
    expect(commandKindAccess('list-all')).toBe('read-only');
    expect(commandKindAccess('backup-status')).toBe('read-only');
    expect(commandKindAccess('anything-else')).toBe('read-only');
  });
});

describe('runCommandKindSession', () => {
  it('acquires renet with the kind access, then runs one job with an empty vault', async () => {
    const options = {
      functionName: 'backup-unit',
      machineName: 'm1',
      commandKind: { name: 'backup-unit', args: { units: ['rediacc-backup-a'] } },
    };
    const result = await runCommandKindSession(
      SFTP,
      { renetPath: '/local/renet' },
      MACHINE,
      'key',
      options,
      Date.now()
    );

    expect(mockAcquire).toHaveBeenCalledTimes(1);
    expect(mockAcquire.mock.calls[0][0]).toBe('provision');
    expect(mockRun).toHaveBeenCalledTimes(1);
    expect(mockRun.mock.calls[0].slice(0, 3)).toEqual(['/usr/bin/renet', '', options]);
    expect(result.success).toBe(true);
  });
});
