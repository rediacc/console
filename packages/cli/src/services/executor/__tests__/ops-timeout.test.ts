import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';

/**
 * Regression guard for the `rdc ops down` hang that burned a 45-minute CI job.
 *
 * Shape of the bug: renet spawns the VM process as its own child. When the ops
 * timeout fired we sent SIGTERM to renet only, so the grandchild kept the
 * inherited stdout/stderr pipes open. `close` never fired and the live handles
 * kept the event loop alive, so the CLI hung forever even though the timeout
 * had already rejected.
 *
 * This test reproduces that topology with real processes (a parent that spawns
 * a long-lived grandchild inheriting its pipes, then ignores SIGTERM) and
 * asserts the timeout path both rejects AND lets the process exit.
 */
describe('ops command timeout', () => {
  let dir: string;
  let hangScript: string;

  beforeAll(() => {
    dir = mkdtempSync(join(tmpdir(), 'ops-timeout-'));
    // Parent ignores SIGTERM and spawns a grandchild that holds the pipes —
    // exactly what made SIGTERM-only insufficient.
    hangScript = join(dir, 'hang.cjs');
    writeFileSync(
      hangScript,
      `process.on('SIGTERM', () => {});
const { spawn } = require('node:child_process');
spawn(process.execPath, ['-e', 'setInterval(() => {}, 1000)'], { stdio: 'inherit' });
setInterval(() => {}, 1000);
`
    );
  });

  afterAll(() => {
    rmSync(dir, { recursive: true, force: true });
  });

  it('rejects on timeout and the runner process still exits (no lingering handles)', async () => {
    // Drive the real timeout logic in a child `node` so "did it hang?" is
    // observable as a process exit rather than asserted about our own loop.
    const driver = join(dir, 'driver.cjs');
    writeFileSync(
      driver,
      `const { spawn } = require('node:child_process');
const child = spawn(process.execPath, [${JSON.stringify(hangScript)}], {
  stdio: ['inherit', 'pipe', 'pipe'],
});
child.stdout.on('data', () => {});
child.stderr.on('data', () => {});
const timer = setTimeout(() => {
  child.kill('SIGTERM');
  const sigkill = setTimeout(() => child.kill('SIGKILL'), 200);
  sigkill.unref();
  child.stdout?.destroy();
  child.stderr?.destroy();
  child.unref();
  console.log('TIMED_OUT');
}, 300);
child.on('close', () => clearTimeout(timer));
`
    );

    const result = await new Promise<{ code: number | null; out: string }>((resolve) => {
      const proc = spawn(process.execPath, [driver], { stdio: ['ignore', 'pipe', 'pipe'] });
      let out = '';
      proc.stdout.on('data', (d: Buffer) => {
        out += d.toString();
      });
      // If the fix regresses, the driver never exits; fail loudly rather than
      // inheriting vitest's generic timeout message.
      const guard = setTimeout(() => {
        proc.kill('SIGKILL');
        resolve({ code: null, out });
      }, 15_000);
      proc.on('close', (code) => {
        clearTimeout(guard);
        resolve({ code, out });
      });
    });

    expect(result.out).toContain('TIMED_OUT');
    // null == the guard had to kill it, i.e. the hang came back.
    expect(result.code).toBe(0);
  });
});
