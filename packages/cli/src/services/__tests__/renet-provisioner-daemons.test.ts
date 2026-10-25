/**
 * After a binary update the provisioner moves the renet daemons onto the new binary (C2), and machine
 * status / health can say which renet processes still run a replaced one (C4).
 *
 * The incident: `machine setup` on hostinger (2026-10-15) replaced renet and restarted the router,
 * while 21 renet processes (hub, plugins, per-repo supervisors) kept running the deleted binary with
 * nothing anywhere saying so.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

const { info, warn } = vi.hoisted(() => ({ info: vi.fn(), warn: vi.fn() }));
vi.mock('../core/output.js', () => ({ outputService: { info, warn, error: vi.fn() } }));

const {
  buildRenetProcessProbeCommand,
  parseDaemonUpgradeJson,
  parseStaleRenetProcesses,
  upgradeDaemons,
} = await import('../renet/renet-daemons.js');
const { REMOTE_RENET_PATH, renetProvisioner } = await import('../renet/renet-provisioner.js');

const CUR = '/usr/lib/rediacc/renet/0.9.2/renet';

/** Probe output as captured from a real run of the probe script (pid, unit, exe, current). */
const PROBE = [
  `101\trediacc-hub.service\t/usr/lib/rediacc/renet/0.9.1/renet (deleted)\t${CUR}`,
  `202\trediacc-docker-64.service\t/usr/lib/rediacc/renet/0.9.1/renet\t${CUR}`,
  `303\trediacc-router.service\t${CUR}\t${CUR}`,
  '',
].join('\n');

function fakeSftp(responses: Record<string, string | Error>) {
  const calls: string[] = [];
  return {
    calls,
    exec: (cmd: string): Promise<string> => {
      calls.push(cmd);
      for (const [needle, out] of Object.entries(responses)) {
        if (cmd.includes(needle))
          return out instanceof Error ? Promise.reject(out) : Promise.resolve(out);
      }
      return Promise.reject(new Error(`unexpected: ${cmd}`));
    },
  };
}

beforeEach(() => {
  info.mockClear();
  warn.mockClear();
});

describe('stale renet process probe (C4)', () => {
  it('flags a deleted binary and a binary other than current, not the current one', () => {
    expect(parseStaleRenetProcesses(PROBE)).toEqual([
      {
        pid: 101,
        unit: 'rediacc-hub.service',
        exe: '/usr/lib/rediacc/renet/0.9.1/renet (deleted)',
      },
      { pid: 202, unit: 'rediacc-docker-64.service', exe: '/usr/lib/rediacc/renet/0.9.1/renet' },
    ]);
  });

  it('with no current link, only a deleted binary counts', () => {
    expect(parseStaleRenetProcesses('7\t-\t/opt/renet (deleted)\t\n8\t-\t/opt/renet\t\n')).toEqual([
      { pid: 7, unit: '-', exe: '/opt/renet (deleted)' },
    ]);
  });

  it('reads /proc through sudo sh, never through renet itself', () => {
    const cmd = buildRenetProcessProbeCommand(REMOTE_RENET_PATH);
    expect(cmd.startsWith('sudo sh -c ')).toBe(true);
    expect(cmd).toContain('/proc/[0-9]*');
    expect(cmd).toContain('readlink -f /usr/lib/rediacc/renet/current/renet');
  });
});

describe('renet daemons upgrade (C2)', () => {
  it('parses restarted, stale and failed processes', () => {
    const report = parseDaemonUpgradeJson(
      JSON.stringify({
        processes: [
          { pid: 101, unit: 'rediacc-hub.service', exe: 'x (deleted)', action: 'restarted' },
          { pid: 202, unit: 'rediacc-docker-64.service', exe: 'x', action: 'stale' },
          {
            pid: 303,
            unit: 'rediacc-hub-2.service',
            exe: 'x',
            action: 'failed',
            error: 'no /health',
          },
          { pid: 404, unit: 'rediacc-router.service', exe: CUR, action: 'current' },
        ],
      })
    );
    expect(report.restarted.map((p) => p.pid)).toEqual([101]);
    expect(report.stale.map((p) => p.pid)).toEqual([202]);
    expect(report.failed).toEqual([
      { pid: 303, unit: 'rediacc-hub-2.service', exe: 'x', error: 'no /health' },
    ]);
  });

  it('refreshRouter restarts the router AND runs daemons upgrade, saying what it restarted and what is stale', async () => {
    const sftp = fakeSftp({
      'systemctl is-active --quiet rediacc-router': 'RESTARTED\n',
      'daemons upgrade --json': JSON.stringify({
        processes: [
          { pid: 101, unit: 'rediacc-hub.service', exe: 'x (deleted)', action: 'restarted' },
          { pid: 202, unit: 'rediacc-docker-64.service', exe: 'x', action: 'stale' },
        ],
      }),
    });
    expect(await renetProvisioner.refreshRouter(sftp, CUR)).toBe(true);
    expect(sftp.calls[1]).toBe(`sudo '${CUR}' daemons upgrade --json 2>/dev/null`);
    expect(info).toHaveBeenCalledWith(expect.stringContaining('rediacc-hub.service (pid 101)'));
    expect(warn).toHaveBeenCalledWith(
      expect.stringContaining('rediacc-docker-64.service (pid 202)')
    );
  });

  it('an older renet without the verb still reports what is stale, from /proc', async () => {
    const sftp = fakeSftp({
      'systemctl is-active --quiet rediacc-router': 'RESTARTED\n',
      'daemons upgrade --json': new Error('exit 1: unknown command "daemons"'),
      'sudo sh -c': PROBE,
    });
    const report = await upgradeDaemons(sftp, CUR, REMOTE_RENET_PATH);
    expect(report.ran).toBe(false);
    expect(report.stale.map((p) => p.pid)).toEqual([101, 202]);
    await renetProvisioner.refreshRouter(sftp, CUR);
    expect(warn).toHaveBeenCalledWith(expect.stringContaining('has no `daemons upgrade`'));
  });

  it('a router that is not active still gets its daemons upgraded', async () => {
    const sftp = fakeSftp({
      'systemctl is-active --quiet rediacc-router': '',
      'daemons upgrade --json': JSON.stringify({ processes: [] }),
    });
    expect(await renetProvisioner.refreshRouter(sftp, CUR)).toBe(false);
    expect(sftp.calls.some((c) => c.includes('daemons upgrade --json'))).toBe(true);
    expect(warn).not.toHaveBeenCalled();
  });
});
