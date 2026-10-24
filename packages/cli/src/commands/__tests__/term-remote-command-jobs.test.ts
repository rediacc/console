/**
 * buildRemoteCommand keeps the user's command a list of its own (vm:check I1.8, 2026-10-24).
 *
 * The remote command used to join the bashrc preamble to the user's command with `&&`, so a user
 * command `X & Y` parsed as `(source … || true && X) & Y`: bash ran the whole AND-list as a
 * background SUBSHELL, the subshell kept the channel's stdout and stderr and waited on X, and the
 * ssh channel stayed open for as long as X ran, which for a VS Code server or a nohup job is
 * forever. The command is run here under a real bash with stdout on a pipe, the way sshd holds
 * it, and the pipe must reach EOF while the backgrounded job is still alive.
 */
import { spawn } from 'node:child_process';
import { mkdtempSync, readdirSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { WK_DATASTORE_PATH } from '@rediacc/shared/config/well-known.generated';
import { afterAll, describe, expect, it } from 'vitest';
import type { ConnectionDetails } from '../../services/machine/ssh-connection.js';
import { buildRemoteCommand } from '../term.js';

const home = mkdtempSync(join(tmpdir(), 'term-jobs-'));
afterAll(() => rmSync(home, { recursive: true, force: true }));

const details: ConnectionDetails = {
  host: 'h',
  user: 'repo',
  port: 22,
  privateKey: 'k',
  known_hosts: 'kh',
  datastore: WK_DATASTORE_PATH,
  universalUser: 'u',
  environment: { REDIACC_REPOSITORY: 'app' },
  workingDirectory: home,
};

/** Pids whose argv[0] is `marker`, read from /proc so no external tool is needed. */
function survivors(marker: string): number[] {
  const out: number[] = [];
  let entries: string[];
  try {
    entries = readdirSync('/proc');
  } catch (error) {
    // No /proc (macOS): the scan cannot look, so it reports nothing. Any other failure (an unreadable /proc on Linux) must surface, or the leak assertion would pass vacuously.
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') return out;
    throw error;
  }
  for (const entry of entries) {
    if (!/^\d+$/.test(entry)) continue;
    try {
      if (readFileSync(`/proc/${entry}/cmdline`, 'utf8').split('\0')[0] === marker)
        out.push(Number(entry));
    } catch {
      // the process exited between the listing and the read
    }
  }
  return out;
}

/** Milliseconds until the command's stdout pipe reaches EOF, or null when it is still open after `limitMs`. */
function stdoutClosesWithin(
  command: string,
  limitMs: number
): Promise<{ ms: number | null; out: string; pgid: number | undefined }> {
  return new Promise((resolve) => {
    const started = Date.now();
    const child = spawn('bash', ['-c', command], {
      env: { ...process.env, HOME: home },
      stdio: ['ignore', 'pipe', 'ignore'],
      detached: true,
    });
    let out = '';
    child.stdout.on('data', (b) => {
      out += String(b);
    });
    const timer = setTimeout(() => {
      resolve({ ms: null, out, pgid: child.pid });
    }, limitMs);
    child.stdout.on('end', () => {
      clearTimeout(timer);
      resolve({ ms: Date.now() - started, out, pgid: child.pid });
    });
  });
}

/**
 * Kill the detached child's process group and return the marker's survivors after a short reap window.
 *
 * The child was spawned detached, so it leads a process group the backgrounded job stays in (bash -c runs without job control); killing the group ends the job with no external tool. A job that left the group (a future setsid in the preamble) would survive the kill, and the caller fails on it rather than leak it. A SIGKILLed job can still show its argv for a moment while it is reaped, so the survivors are polled briefly before judging.
 */
async function killGroupAndWait(pgid: number | undefined, marker: string): Promise<number[]> {
  if (pgid) {
    try {
      process.kill(-pgid, 'SIGKILL');
    } catch (err) {
      // ESRCH: the group already exited. Anything else (EPERM) is a real failure to clean up.
      if ((err as NodeJS.ErrnoException).code !== 'ESRCH') throw err;
    }
  }
  let left = survivors(marker);
  for (let i = 0; i < 20 && left.length > 0; i++) {
    await new Promise((r) => setTimeout(r, 100));
    left = survivors(marker);
  }
  return left;
}

describe('buildRemoteCommand with a backgrounded job', () => {
  it('lets the channel close while a redirected background job keeps running', async () => {
    const marker = `term-jobs-${process.pid}`;
    // The job outlives the check by far; it is killed below with its process group.
    const user = `nohup bash -c 'exec -a ${marker} sleep 120' >/dev/null 2>&1 & echo STARTED`;
    const { ms, out, pgid } = await stdoutClosesWithin(
      buildRemoteCommand({ command: user }, details),
      10_000
    );
    const left = await killGroupAndWait(pgid, marker);
    expect(left, 'the background job outlived its process group').toEqual([]);
    expect(out).toContain('STARTED');
    expect(ms, 'stdout stayed open: the background job held the channel').not.toBeNull();
    expect(ms as number).toBeLessThan(10_000);
  });

  it('still runs the user command after the preamble', async () => {
    const { out } = await stdoutClosesWithin(
      buildRemoteCommand({ command: 'echo "repo=$REDIACC_REPOSITORY"' }, details),
      10_000
    );
    expect(out).toContain('repo=app');
  });
});
