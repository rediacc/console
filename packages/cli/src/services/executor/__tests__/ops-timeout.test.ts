import { chmodSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { opsExecutorService } from '../ops-executor.js';

/**
 * Regression guard for the `rdc ops` timeout path (review finding F3).
 *
 * The round-31 fix rejected immediately and unref'd the SIGKILL timer, so
 * process.exit() (reached via handleError on a real ops command) fired before
 * the escalation, the SIGKILL never ran and renet's QEMU grandchild was left
 * alive. This test drives the REAL runOpsCommand against a fake "renet" that
 * ignores SIGTERM and spawns a grandchild which also ignores SIGTERM, then
 * asserts BOTH the promise rejects with the timeout AND the grandchild is
 * actually dead, i.e. the process-group SIGKILL reached the whole tree.
 */
describe('ops-executor timeout kills the process tree', () => {
  let dir: string;
  let fakeRenet: string;
  let gcPidFile: string;
  let termFile: string;
  // The in-flight executor run, so a failed readiness wait still ends the process tree it started.
  let pending: Promise<unknown> | null;

  const alive = (pid: number): boolean => {
    try {
      process.kill(pid, 0);
      return true;
    } catch {
      return false;
    }
  };

  // Captured before any fake timer is installed: readiness polling must run on the wall clock while the executor's own timers are driven by hand.
  const realSetTimeout = globalThis.setTimeout;
  const realSleep = (ms: number): Promise<void> =>
    new Promise((resolve) => realSetTimeout(resolve, ms));

  // The grandchild writes its pid only after its SIGTERM handler is installed, so a pid on disk means "ready to be killed the hard way". Polling a readiness file with a deadline is the wait; no fixed delay stands in for it.
  const tryReadGrandchildPid = (): number | null => {
    try {
      const pid = Number.parseInt(readFileSync(gcPidFile, 'utf8').trim(), 10);
      return Number.isInteger(pid) ? pid : null;
    } catch {
      return null; // not written yet
    }
  };
  // The fake renet appends to this file when SIGTERM reaches it, so the test sees the signal itself and not only its absence of effect.
  // The three wall-clock waits (10s pid, 3s SIGTERM, 3s reap) sum to 16s, inside the 20s test timeout, so a missed signal fails on its own assertion and not on the test timeout.
  const waitForSigterm = async (): Promise<boolean> => {
    const deadline = Date.now() + 3000;
    while (Date.now() < deadline) {
      try {
        if (readFileSync(termFile, 'utf8').length > 0) return true;
      } catch {
        // not delivered yet
      }
      await realSleep(10);
    }
    return false;
  };
  const readGrandchildPid = async (): Promise<number> => {
    const deadline = Date.now() + 10_000;
    for (let pid = tryReadGrandchildPid(); ; pid = tryReadGrandchildPid()) {
      if (pid !== null) return pid;
      if (Date.now() > deadline) throw new Error('fake renet never recorded its grandchild pid');
      await realSleep(10);
    }
  };

  beforeEach(() => {
    dir = mkdtempSync(join(tmpdir(), 'ops-timeout-'));
    gcPidFile = join(dir, 'grandchild.pid');
    termFile = join(dir, 'sigterm.mark');
    pending = null;
    fakeRenet = join(dir, 'fake-renet');
    // Fake renet: ignore SIGTERM (wedged), spawn a grandchild in the SAME process group (default, not detached) that also ignores SIGTERM and hangs, then hang too. Only a group-wide SIGKILL ends it. The grandchild records its own pid once its handler is in place.
    writeFileSync(
      fakeRenet,
      `#!/usr/bin/env node
const { spawn } = require('node:child_process');
process.on('SIGTERM', () => { require('node:fs').appendFileSync(${JSON.stringify(termFile)}, 'term\\n'); });
const grandchild = "process.on('SIGTERM',()=>{}); require('node:fs').writeFileSync(" + JSON.stringify(${JSON.stringify(gcPidFile)}) + ", String(process.pid)); setInterval(()=>{}, 1e9)";
spawn(process.execPath, ['-e', grandchild], { stdio: 'ignore' });
setInterval(() => {}, 1e9);
`
    );
    chmodSync(fakeRenet, 0o755);
    vi.spyOn(opsExecutorService, 'getRenetPath').mockResolvedValue(fakeRenet);
    // Only the executor's timeout and escalation timers are faked. They are advanced by hand once the process tree is up, so the verdict does not depend on how long a loaded machine takes to boot two node processes (a wall-clock 500ms timeout used to fire before the grandchild existed, and the pid file read threw ENOENT).
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
  });

  afterEach(async () => {
    // A run still in flight (the readiness wait threw) is ended through the executor's own timers: the timeout sends SIGTERM and the grace window then sends the group SIGKILL.
    try {
      if (pending) {
        vi.advanceTimersByTime(60_000);
        const settled = await Promise.race([
          pending.then(() => true),
          realSleep(5000).then(() => false),
        ]);
        if (!settled)
          throw new Error(
            'the executor never settled after the group SIGKILL; the fake renet tree may still be alive'
          );
      }
    } finally {
      // Runs even when the settle wait throws, so fake timers, mocks and the temp dir never leak into later tests.
      vi.useRealTimers();
      vi.restoreAllMocks();
      rmSync(dir, { recursive: true, force: true });
    }
  }, 10_000);

  it('escalates to SIGKILL across the group so the grandchild dies, then rejects', async () => {
    let settled = false;
    const outcome = opsExecutorService
      .runOpsCommand('down', [], {
        capture: true,
        backend: 'kvm',
        timeout: 500,
        sigkillGraceMs: 300,
      })
      .finally(() => {
        settled = true;
      });
    // Observe the rejection from the start; it is asserted below.
    const rejection = outcome.then(
      () => undefined,
      (error: unknown) => error
    );
    pending = rejection;

    const gcPid = await readGrandchildPid();
    expect(alive(gcPid)).toBe(true);

    // The timeout elapses: SIGTERM goes to the group, and both processes ignore it.
    vi.advanceTimersByTime(500);
    expect(await waitForSigterm()).toBe(true);
    expect(settled).toBe(false);
    expect(alive(gcPid)).toBe(true);

    // The grace window elapses: SIGKILL goes to the whole group, and only then does the promise settle.
    vi.advanceTimersByTime(300);
    const error = await rejection;
    expect(error).toBeInstanceOf(Error);
    expect((error as Error).message).toMatch(/timed out/);

    // Prove the grandchild is dead, the exact thing the old test never checked. The kill is already delivered; this only waits for the kernel to reap it.
    const deadline = Date.now() + 3000;
    while (alive(gcPid) && Date.now() < deadline) {
      await realSleep(20);
    }
    expect(alive(gcPid)).toBe(false);
  }, 20_000);
});
