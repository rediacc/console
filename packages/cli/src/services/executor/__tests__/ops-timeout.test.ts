import { spawn } from 'node:child_process';
import { chmodSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { opsExecutorService } from '../ops-executor.js';

// Captured before any fake timer is installed: readiness polling and cleanup run on the wall clock while the executor's own timers are driven by hand.
const realSetTimeout = globalThis.setTimeout;
const realClearTimeout = globalThis.clearTimeout;

const isAlive = (pid: number): boolean => {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
};

// Whether any process still belongs to the group led by `pid`. A group id is not reused while it has a member, so signalling the group cannot reach an unrelated process the way a bare recorded pid can after its process was reaped.
const groupAlive = (pid: number): boolean => Number.isInteger(pid) && isAlive(-pid);

type SettleOptions = {
  pending: Promise<unknown> | null;
  advance: (ms: number) => void;
  renetPid: () => number;
  grandchildPid: () => number;
  dir: string;
  killGroup?: (pgid: number) => void;
  settleWaitMs?: number;
  reapWaitMs?: number;
};

// Drives a run still in flight to its end. A rejected run counts as ended (its outcome is not this helper's concern), so a rejection never skips the kill and the survivor check below.
const settleRun = async (options: SettleOptions): Promise<void> => {
  if (!options.pending) return;
  options.advance(60_000);
  let timer: ReturnType<typeof setTimeout> | undefined;
  const settled = await Promise.race([
    options.pending.then(
      () => true,
      () => true
    ),
    new Promise<boolean>((resolve) => {
      timer = realSetTimeout(() => resolve(false), options.settleWaitMs ?? 5000);
    }),
  ]);
  realClearTimeout(timer);
  if (settled) return;
  const renet = options.renetPid();
  const kill =
    options.killGroup ??
    ((pgid: number) => {
      try {
        process.kill(-pgid, 'SIGKILL');
      } catch {
        // already gone
      }
    });
  if (Number.isInteger(renet)) kill(renet);
  await new Promise((resolve) => realSetTimeout(resolve, options.reapWaitMs ?? 500));
  const survivors = [
    ...(groupAlive(renet) ? [`process group ${renet}`] : []),
    ...[options.grandchildPid()]
      .filter((pid) => Number.isInteger(pid) && isAlive(pid))
      .map((pid) => `pid ${pid}`),
  ];
  throw Object.assign(
    new Error(
      survivors.length > 0
        ? `the executor never settled after the group SIGKILL and ${survivors.join(', ')} is still alive; their files are kept in ${options.dir}`
        : 'the executor never settled after the group SIGKILL; the fake renet tree was killed directly'
    ),
    { keepDir: survivors.length > 0 }
  );
};

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
  let renetPidFile: string;
  // The in-flight executor run, so a failed readiness wait still ends the process tree it started.
  let pending: Promise<unknown> | null;

  const alive = isAlive;

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
    renetPidFile = join(dir, 'renet.pid');
    pending = null;
    fakeRenet = join(dir, 'fake-renet');
    // Fake renet: ignore SIGTERM (wedged), spawn a grandchild in the SAME process group (default, not detached) that also ignores SIGTERM and hangs, then hang too. Only a group-wide SIGKILL ends it. The grandchild records its own pid once its handler is in place.
    writeFileSync(
      fakeRenet,
      `#!/usr/bin/env node
const { spawn } = require('node:child_process');
require('node:fs').writeFileSync(${JSON.stringify(renetPidFile)}, String(process.pid));
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

  const readPid = (file: string): number => {
    try {
      return Number.parseInt(readFileSync(file, 'utf8').trim(), 10);
    } catch {
      return Number.NaN; // never written
    }
  };

  // Ends a run still in flight (the readiness wait threw) through the executor's own timers: the timeout sends SIGTERM and the grace window then sends the group SIGKILL. When that does not settle it, the whole process group is killed directly, which also reaches a grandchild that is alive but had not yet recorded its pid. The returned directory is kept (and named in the thrown error) only when something survives, so a leaked tree stays diagnosable.
  const settlePending = (): Promise<void> =>
    settleRun({
      pending,
      advance: (ms) => vi.advanceTimersByTime(ms),
      renetPid: () => readPid(renetPidFile),
      grandchildPid: () => readPid(gcPidFile),
      dir,
    });

  afterEach(async () => {
    let keepDir = false;
    try {
      await settlePending();
    } catch (error) {
      keepDir = (error as { keepDir?: boolean }).keepDir === true;
      throw error;
    } finally {
      // Runs even when the settle wait throws, so fake timers and mocks never leak into later tests.
      vi.useRealTimers();
      vi.restoreAllMocks();
      if (!keepDir) rmSync(dir, { recursive: true, force: true });
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

describe('settleRun, the cleanup behind the timeout test', () => {
  const cleanups: (() => void)[] = [];
  afterEach(() => {
    for (const fn of cleanups.splice(0)) fn();
  });

  // A detached node process (its own group leader) that spawns an unrecorded node grandchild in the same group. Both ignore SIGTERM.
  const startTree = async (dir: string): Promise<{ leader: number; grandchildFile: string }> => {
    const grandchildFile = join(dir, 'unrecorded.pid');
    const child = spawn(
      process.execPath,
      [
        '-e',
        `const { spawn } = require('node:child_process');
process.on('SIGTERM', () => {});
const gc = spawn(process.execPath, ['-e', "process.on('SIGTERM',()=>{}); setInterval(()=>{},1e9)"], { stdio: 'ignore' });
require('node:fs').writeFileSync(${JSON.stringify(grandchildFile)}, String(gc.pid));
setInterval(() => {}, 1e9);`,
      ],
      { detached: true, stdio: 'ignore' }
    );
    const leader = child.pid as number;
    cleanups.push(() => {
      try {
        process.kill(-leader, 'SIGKILL');
      } catch {
        // already gone
      }
    });
    for (let i = 0; i < 500; i++) {
      try {
        readFileSync(grandchildFile, 'utf8');
        return { leader, grandchildFile };
      } catch {
        await new Promise((resolve) => realSetTimeout(resolve, 10));
      }
    }
    throw new Error('the test tree never started');
  };

  const options = (dir: string, over: Partial<SettleOptions>): SettleOptions => ({
    pending: new Promise(() => {}),
    advance: () => {},
    renetPid: () => Number.NaN,
    grandchildPid: () => Number.NaN,
    dir,
    settleWaitMs: 50,
    reapWaitMs: 50,
    ...over,
  });

  it('kills the whole group, including a grandchild that never recorded its pid, and lets the directory go', async () => {
    const dir = mkdtempSync(join(tmpdir(), 'ops-settle-'));
    cleanups.push(() => rmSync(dir, { recursive: true, force: true }));
    const { leader, grandchildFile } = await startTree(dir);
    const grandchild = Number.parseInt(readFileSync(grandchildFile, 'utf8'), 10);
    expect(isAlive(grandchild)).toBe(true);
    // Only the leader is recorded; the grandchild's pid stays unknown to the helper.
    const error = await settleRun(options(dir, { renetPid: () => leader })).catch((e) => e);
    expect((error as Error).message).toMatch(/killed directly/);
    expect((error as { keepDir?: boolean }).keepDir).toBe(false);
    for (let i = 0; i < 100 && isAlive(grandchild); i++) {
      await new Promise((resolve) => realSetTimeout(resolve, 20));
    }
    expect(isAlive(grandchild)).toBe(false);
  });

  it('keeps the directory and names the survivor when the group outlives the kill', async () => {
    const dir = mkdtempSync(join(tmpdir(), 'ops-settle-'));
    cleanups.push(() => rmSync(dir, { recursive: true, force: true }));
    const { leader } = await startTree(dir);
    const error = await settleRun(
      options(dir, { renetPid: () => leader, killGroup: () => {} })
    ).catch((e) => e);
    expect((error as Error).message).toContain(`process group ${leader} is still alive`);
    expect((error as Error).message).toContain(dir);
    expect((error as { keepDir?: boolean }).keepDir).toBe(true);
  });

  it('treats a run that rejects as ended, so no kill is sent for it', async () => {
    const dir = mkdtempSync(join(tmpdir(), 'ops-settle-'));
    cleanups.push(() => rmSync(dir, { recursive: true, force: true }));
    const killed: number[] = [];
    await expect(
      settleRun(
        options(dir, {
          pending: Promise.reject(new Error('boom')),
          renetPid: () => 1,
          killGroup: (pgid) => killed.push(pgid),
        })
      )
    ).resolves.toBeUndefined();
    expect(killed).toEqual([]);
  });
});
