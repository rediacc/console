import { type ChildProcess, spawn } from 'node:child_process';
import { tmpdir } from 'node:os';
import path from 'node:path';

/**
 * Kernel flock on the per-tutorial recording lock, held only while a render is about to
 * live-record browser scenes. That is the one critical section the old shell-level flock
 * (held for the WHOLE render) was protecting: setupCommand/teardownCommand create and
 * destroy named lab resources (demo forks, tunnels) and a cold scene is recorded then
 * copied into the language-independent segment cache. A warm render only READS the cache
 * and needs no lock, so N locales of one tutorial can encode concurrently.
 *
 * The lock is a real flock(1) held by a child that blocks reading stdin. If this process
 * dies for any reason the pipe closes, the child exits and the kernel drops the lock, so
 * a killed render never wedges the next one. The path matches what pool.sh used to take,
 * so a hand-run render and a pooled one still exclude each other.
 */
function segLockPath(tutorial: string): string {
  return path.join(tmpdir(), `rediacc-tut-seg.${tutorial}.lock`);
}

export interface SegLock {
  release(): void;
}

export function acquireSegLock(
  tutorial: string,
  lockFile = segLockPath(tutorial)
): Promise<SegLock> {
  return new Promise((resolve, reject) => {
    const child: ChildProcess = spawn(
      'flock',
      ['--exclusive', lockFile, 'bash', '-c', 'echo held; cat >/dev/null'],
      { stdio: ['pipe', 'pipe', 'inherit'] }
    );
    let settled = false;
    child.once('error', (err) => {
      if (!settled) {
        settled = true;
        reject(new Error(`cannot take ${lockFile}: ${String(err)}`));
      }
    });
    child.once('exit', (code) => {
      if (!settled) {
        settled = true;
        reject(new Error(`flock on ${lockFile} exited ${String(code)} before the lock was held`));
      }
    });
    child.stdout?.once('data', () => {
      if (settled) return;
      settled = true;
      resolve({
        release() {
          child.stdin?.end();
        },
      });
    });
  });
}
