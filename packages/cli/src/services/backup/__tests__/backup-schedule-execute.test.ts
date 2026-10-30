import { describe, expect, it, vi } from 'vitest';
import type { SFTPClient } from '../../../remote/sftp/client.js';
import { outputService } from '../../core/output.js';
import { executePlan } from '../backup-schedule-execute.js';
import type { ReconcilePlan, RemoteUnitState, StrategyDiff } from '../backup-schedule-reconcile.js';

/** A fake SFTP client that records every remote command and fails `systemctl disable` on a missing unit, as systemd does. */
function fakeSftp(units: Set<string>) {
  const commands: string[] = [];
  const sftp = {
    execStreaming: (command: string) => {
      commands.push(command);
      const disable = /systemctl disable --now (\S+)/.exec(command);
      return Promise.resolve(disable && !units.has(disable[1]) ? 1 : 0);
    },
  } as unknown as SFTPClient;
  return { sftp, commands };
}

function file(path: string, exists: boolean) {
  return { path, exists, sha256: exists ? 'x' : null };
}

function removed(name: string, timer: boolean): StrategyDiff {
  const remote: RemoteUnitState = {
    serviceFile: file(`/etc/systemd/system/rediacc-backup-${name}.service`, timer),
    timerFile: file(`/etc/systemd/system/rediacc-backup-${name}.timer`, timer),
    envFile: file(`/etc/rediacc/backup-${name}.env`, true),
    isActiveService: false,
    isActiveAdhoc: false,
    isEnabledTimer: timer,
    isActiveTimer: timer,
    isFailed: false,
  };
  return { name, action: 'remove', desired: null, remote, changedFiles: [] } as StrategyDiff;
}

function plan(toRemove: StrategyDiff[]): ReconcilePlan {
  return {
    toCreate: [],
    toUpdate: [],
    toRemove,
    unchanged: [],
    skippedInFlight: [],
    daemonReloadNeeded: false,
  };
}

describe('executePlan removals', () => {
  it('removes a strategy whose units are gone but whose env file was left behind, without disabling a missing timer', async () => {
    const { sftp, commands } = fakeSftp(new Set());
    await executePlan(sftp, plan([removed('weekly-cold', false)]), {});
    expect(commands.some((c) => c.includes('systemctl disable'))).toBe(false);
    expect(commands.some((c) => c.includes("rm -f '/etc/rediacc/backup-weekly-cold.env'"))).toBe(
      true
    );
  });

  it('stops a timer systemd still runs after its unit file is gone', async () => {
    const { sftp, commands } = fakeSftp(new Set());
    const diff = removed('ghost', false);
    if (diff.remote) diff.remote.isActiveTimer = true;
    await executePlan(sftp, plan([diff]), {});
    expect(commands.some((c) => c.includes('systemctl stop rediacc-backup-ghost.timer'))).toBe(
      true
    );
    expect(commands.some((c) => c.includes('systemctl disable'))).toBe(false);
  });

  it('drops the dangling enable link of a timer that is only enabled, and a failure there only warns', async () => {
    const commands: string[] = [];
    const sftp = {
      execStreaming: (command: string) => {
        commands.push(command);
        return Promise.resolve(command.includes('systemctl stop') ? 5 : 0);
      },
    } as unknown as SFTPClient;
    const diff = removed('linked', false);
    if (diff.remote) diff.remote.isEnabledTimer = true;
    const warn = vi.spyOn(outputService, 'warn').mockImplementation(() => undefined);
    try {
      await executePlan(sftp, plan([diff]), {});
      expect(warn).toHaveBeenCalledWith(
        expect.stringContaining('removed strategy "linked" (exit 5)')
      );
    } finally {
      warn.mockRestore();
    }
    const stop = commands.find((c) => c.includes('systemctl stop rediacc-backup-linked.timer'));
    expect(stop).toContain(
      'rm -f /etc/systemd/system/timers.target.wants/rediacc-backup-linked.timer'
    );
    // A failed stop fails the whole command, whatever the steps after it return.
    expect(stop).toContain('systemctl stop rediacc-backup-linked.timer || rc=$?');
    expect(stop).toContain('exit $rc');
    // The env file is still removed after the failed stop: the schedule went on.
    expect(commands.some((c) => c.includes("rm -f '/etc/rediacc/backup-linked.env'"))).toBe(true);
  });

  it('still disables a timer that exists before removing its files', async () => {
    const { sftp, commands } = fakeSftp(new Set(['rediacc-backup-nightly.timer']));
    await executePlan(sftp, plan([removed('nightly', true)]), {});
    const disable = commands.findIndex((c) =>
      c.includes('systemctl disable --now rediacc-backup-nightly.timer')
    );
    const rm = commands.findIndex((c) => c.startsWith("sudo rm -f '"));
    expect(disable).toBeGreaterThanOrEqual(0);
    expect(rm).toBeGreaterThan(disable);
  });
});
