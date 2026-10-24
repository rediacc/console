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
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
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
  datastore: '/mnt/rediacc',
  universalUser: 'u',
  environment: { REDIACC_REPOSITORY: 'app' },
  workingDirectory: home,
};

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

describe('buildRemoteCommand with a backgrounded job', () => {
  it('lets the channel close while a redirected background job keeps running', async () => {
    const marker = `term-jobs-${process.pid}`;
    // The job outlives the check by far; it is killed below with its process group.
    const user = `nohup bash -c 'exec -a ${marker} sleep 120' >/dev/null 2>&1 & echo STARTED`;
    const { ms, out, pgid } = await stdoutClosesWithin(
      buildRemoteCommand({ command: user }, details),
      10_000
    );
    // The child was spawned detached, so it leads a process group the backgrounded job stays in
    // (bash -c runs without job control); killing the group ends the job with no external tool.
    if (pgid) {
      try {
        process.kill(-pgid, 'SIGKILL');
      } catch {
        // already gone
      }
    }
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
