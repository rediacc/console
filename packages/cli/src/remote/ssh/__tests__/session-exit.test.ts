/**
 * A one-shot ssh session ends when its command does (term connect -c on hostinger never returned, 2026-11-20).
 *
 * sshd keeps a channel open while any process holds its stdout or stderr, so a child the command
 * left running kept the local ssh, and the rdc call, alive long after the command exited. Two seams:
 * a fake ssh child that reports the exit and then keeps its stream open, and a real shell standing in
 * for the remote side, whose background child keeps the stderr pipe open the way it keeps sshd's.
 */
import { type ChildProcess, spawn } from 'node:child_process';
import { EventEmitter } from 'node:events';
import { PassThrough } from 'node:stream';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { buildSSHOptions, SSH_KEEPALIVE_OPTIONS } from '../connection.js';
import {
  createExitMarkerFilter,
  exitTrapShell,
  newExitMarker,
  waitForSessionEnd,
} from '../session-exit.js';

const MARKER = '__rdc_exit_0123456789abcdef__:';

describe('keepalives on every ssh session', () => {
  it('sends ServerAlive probes, so a silent command keeps its connection and a dead peer ends ssh', () => {
    // A `sleep 900` session to hostinger never returned without them: the remote command was gone, the local socket still ESTABLISHED (2026-11-20).
    const opts = buildSSHOptions({ knownHostsPath: '/tmp/kh', port: 22 });
    const joined = opts.join(' ');
    expect(joined).toContain('-o ServerAliveInterval=15');
    expect(joined).toContain('-o ServerAliveCountMax=4');
    expect(opts).toEqual(expect.arrayContaining([...SSH_KEEPALIVE_OPTIONS]));
  });
});

function filterAll(chunks: string[]): { text: string; statuses: number[] } {
  let text = '';
  const statuses: number[] = [];
  const filter = createExitMarkerFilter(
    MARKER,
    (t) => {
      text += t;
    },
    (s) => statuses.push(s)
  );
  for (const chunk of chunks) filter.push(chunk);
  filter.end();
  return { text, statuses };
}

describe('the exit marker filter', () => {
  it('removes the marker line and reports its status, leaving the rest byte for byte', () => {
    expect(filterAll([`warn: x\n${MARKER}3\nlate\n`])).toEqual({
      text: 'warn: x\nlate\n',
      statuses: [3],
    });
  });

  it('finds a marker split across chunks, and one after output with no trailing newline', () => {
    const line = `partial${MARKER}42\n`;
    for (let cut = 1; cut < line.length; cut++) {
      expect(filterAll([line.slice(0, cut), line.slice(cut)])).toEqual({
        text: 'partial',
        statuses: [42],
      });
    }
  });

  it('passes through text that only looks like the start of a marker', () => {
    expect(filterAll(['__rdc_exit_', '0123 nope\n'])).toEqual({
      text: '__rdc_exit_0123 nope\n',
      statuses: [],
    });
    expect(filterAll([`${MARKER}x\n`])).toEqual({ text: `${MARKER}x\n`, statuses: [] });
  });

  it('a fresh marker per call', () => {
    expect(newExitMarker()).not.toBe(newExitMarker());
    expect(newExitMarker()).toMatch(/^__rdc_exit_[0-9a-f]{16}__:$/);
  });
});

/** A stand-in for the spawned ssh: stderr is a stream, exit is an event, kill is recorded. */
class FakeSsh extends EventEmitter {
  stderr = new PassThrough();
  kill = vi.fn((_signal?: NodeJS.Signals) => {
    setImmediate(() => {
      this.emit('exit', null, 'SIGTERM');
      this.stderr.end();
    });
    return true;
  });
}

describe('waitForSessionEnd over a fake ssh', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('ends a session whose command reported its exit while the stream stays open', async () => {
    const ssh = new FakeSsh();
    let shown = '';
    const ended = waitForSessionEnd(ssh as unknown as ChildProcess, {
      marker: MARKER,
      onStderr: (t) => {
        shown += t;
      },
      graceMs: 50,
    });
    // The command printed, exited 7, and something still holds the channel: no exit, no end.
    ssh.stderr.write(`pulled\n${MARKER}7\n`);
    await expect(ended).resolves.toEqual({ code: 7, forced: true });
    expect(ssh.kill).toHaveBeenCalledWith('SIGTERM');
    expect(shown).toBe('pulled\n');
  });

  it('a session that closes by itself keeps its exit code and is not ended here', async () => {
    const ssh = new FakeSsh();
    const ended = waitForSessionEnd(ssh as unknown as ChildProcess, {
      marker: MARKER,
      onStderr: () => undefined,
      graceMs: 50,
    });
    ssh.stderr.end(`${MARKER}0\n`);
    ssh.emit('exit', 0, null);
    await expect(ended).resolves.toEqual({ code: 0, forced: false });
    expect(ssh.kill).not.toHaveBeenCalled();
  });

  it('without a marker, an exit whose stderr never ends still resolves', async () => {
    const ssh = new FakeSsh();
    const ended = waitForSessionEnd(ssh as unknown as ChildProcess, {
      onStderr: () => undefined,
      graceMs: 50,
    });
    ssh.emit('exit', 5, null);
    await expect(ended).resolves.toEqual({ code: 5, forced: false });
  });
});

// BLOCKER: spawns a real POSIX `sh` with a background `sleep` holding the stderr pipe open (the remote side of the session); Windows has no `sh` on PATH.
describe.skipIf(process.platform === 'win32')(
  'waitForSessionEnd over a real shell whose child inherits the stream',
  () => {
    // POSIX sh is the remote side here; the background sleep keeps the stderr pipe open as it would keep sshd's channel.
    const run = (script: string) =>
      spawn('sh', ['-c', script], { stdio: ['ignore', 'ignore', 'pipe'] });

    it('ends with the command, not with the child, and reports the command exit code', async () => {
      const marker = newExitMarker();
      const child = run(`${exitTrapShell(marker)}; sleep 30 & echo started >&2; exit 3`);
      let shown = '';
      const started = Date.now();
      const end = await waitForSessionEnd(child, {
        marker,
        onStderr: (t) => {
          shown += t;
        },
        graceMs: 300,
      });
      expect(Date.now() - started).toBeLessThan(10_000);
      // The shell itself exited; its stderr pipe stayed open in the sleep.
      expect(end).toEqual({ code: 3, forced: false });
      expect(shown).toBe('started\n');
    }, 20_000);

    it('the same shell without the trap is held open by the child (the defect, as a control)', async () => {
      const child = run('sleep 3 & exit 3');
      const closed = await new Promise<boolean>((resolve) => {
        const timer = setTimeout(() => resolve(false), 1_000);
        child.on('close', () => {
          clearTimeout(timer);
          resolve(true);
        });
      });
      expect(closed).toBe(false);
    }, 10_000);
  }
);
