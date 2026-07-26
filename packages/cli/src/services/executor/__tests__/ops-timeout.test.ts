import { chmodSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { opsExecutorService } from '../ops-executor.js';

/**
 * Regression guard for the `rdc ops` timeout path (review finding F3).
 *
 * The round-31 fix rejected immediately and unref'd the SIGKILL timer, so
 * process.exit() (reached via handleError on a real ops command) fired before
 * the escalation — the SIGKILL never ran and renet's QEMU grandchild was left
 * alive. This test drives the REAL runOpsCommand against a fake "renet" that
 * ignores SIGTERM and spawns a grandchild which also ignores SIGTERM, then
 * asserts BOTH the promise rejects with the timeout AND the grandchild is
 * actually dead — i.e. the process-group SIGKILL reached the whole tree.
 */
describe('ops-executor timeout kills the process tree', () => {
  let dir: string;
  let fakeRenet: string;
  let gcPidFile: string;

  const alive = (pid: number): boolean => {
    try {
      process.kill(pid, 0);
      return true;
    } catch {
      return false;
    }
  };

  beforeEach(() => {
    dir = mkdtempSync(join(tmpdir(), 'ops-timeout-'));
    gcPidFile = join(dir, 'grandchild.pid');
    fakeRenet = join(dir, 'fake-renet');
    // Fake renet: ignore SIGTERM (wedged), spawn a grandchild in the SAME
    // process group (default, not detached) that also ignores SIGTERM and
    // hangs, record its pid, then hang too. Only a group-wide SIGKILL ends it.
    writeFileSync(
      fakeRenet,
      `#!/usr/bin/env node
const { spawn } = require('node:child_process');
const fs = require('node:fs');
process.on('SIGTERM', () => {});
const gc = spawn(process.execPath, ['-e', "process.on('SIGTERM',()=>{}); setInterval(()=>{}, 1e9)"], { stdio: 'ignore' });
fs.writeFileSync(${JSON.stringify(gcPidFile)}, String(gc.pid));
setInterval(() => {}, 1e9);
`
    );
    chmodSync(fakeRenet, 0o755);
    vi.spyOn(opsExecutorService, 'getRenetPath').mockResolvedValue(fakeRenet);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    rmSync(dir, { recursive: true, force: true });
  });

  it('escalates to SIGKILL across the group so the grandchild dies, then rejects', async () => {
    const started = Date.now();
    await expect(
      opsExecutorService.runOpsCommand('down', [], {
        capture: true,
        backend: 'kvm',
        timeout: 500,
        sigkillGraceMs: 300,
      })
    ).rejects.toThrow(/timed out/);

    // The rejection must come only AFTER the kill sequence, not immediately.
    expect(Date.now() - started).toBeGreaterThanOrEqual(500);

    // Read the grandchild pid the fake renet recorded, and prove it is dead —
    // the exact thing the old test never checked.
    const { readFileSync } = await import('node:fs');
    const gcPid = Number.parseInt(readFileSync(gcPidFile, 'utf8').trim(), 10);
    expect(Number.isInteger(gcPid)).toBe(true);

    // Give the group SIGKILL a beat to be reaped, then assert liveness is gone.
    const deadline = Date.now() + 4000;
    while (alive(gcPid) && Date.now() < deadline) {
      await new Promise((r) => setTimeout(r, 50));
    }
    expect(alive(gcPid)).toBe(false);
  }, 15_000);
});
