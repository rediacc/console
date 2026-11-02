import { describe, expect, it, vi } from 'vitest';
import { buildDaemonsRestartCommand, restartDaemons } from '../renet/renet-daemons.js';

const RENET = '/usr/lib/rediacc/renet/current/renet';

describe('buildDaemonsRestartCommand', () => {
  it('adds --include-docker only when asked', () => {
    expect(buildDaemonsRestartCommand(RENET, false)).not.toContain('--include-docker');
    expect(buildDaemonsRestartCommand(RENET, true)).toContain('--include-docker');
  });
});

describe('restartDaemons', () => {
  it('reports restarted, failed and stale processes', async () => {
    const exec = vi.fn().mockResolvedValue(
      JSON.stringify({
        processes: [
          { pid: 10, unit: 'rediacc-router.service', exe: '/old/renet', action: 'restarted' },
          {
            pid: 11,
            unit: 'rediacc-docker-2.service',
            exe: '/old/renet',
            action: 'failed',
            error: 'not active',
          },
          { pid: 12, unit: 'rediacc-docker-3.service', exe: '/old/renet', action: 'stale' },
          { pid: 13, unit: 'x.service', exe: '/new/renet', action: 'current' },
        ],
      })
    );
    const report = await restartDaemons({ exec }, 'm1', RENET, true);
    expect(report.restarted.map((p) => p.pid)).toEqual([10]);
    expect(report.failed).toEqual([
      { pid: 11, unit: 'rediacc-docker-2.service', exe: '/old/renet', error: 'not active' },
    ]);
    expect(report.stale.map((p) => p.pid)).toEqual([12]);
    expect(exec).toHaveBeenCalledWith(expect.stringContaining('daemons upgrade --json'));
  });

  it('answers a renet without the verb with the version-skew message', async () => {
    const exec = vi
      .fn()
      .mockRejectedValue(
        new Error('Command exited with code 1: Error: unknown command "daemons" for "renet"')
      );
    await expect(restartDaemons({ exec }, 'm1', RENET, false)).rejects.toThrow(
      'renet on m1 is older than this CLI; run machine setup'
    );
  });

  it('passes any other failure through', async () => {
    const exec = vi.fn().mockRejectedValue(new Error('Command exited with code 1: boom'));
    await expect(restartDaemons({ exec }, 'm1', RENET, false)).rejects.toThrow('boom');
  });
});
