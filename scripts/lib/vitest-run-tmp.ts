/**
 * Vitest `globalSetup` for every vitest config in the repo: one run directory per `vitest run`, with TMPDIR pointed at it
 * BEFORE the workers fork, so every `mkdtempSync(os.tmpdir(), ...)` a test leaks lands under it. Teardown removes it; a
 * run killed before teardown leaves a stamped directory that the next run's `runDir` sweeps (scripts/lib/runtmp.ts).
 *
 * Listed in each config as `globalSetup`, as a path relative to that config (agent/plans/PLAN-host-temp-disposal.md HT7).
 * Control: scripts/__tests__/vitest-run-tmp.control.ts.
 */
import process from 'node:process';
import { removeTree, runDir } from './runtmp.js';

export default function setup(): () => void {
  const outer = process.env.TMPDIR;
  const dir = runDir('rediacc-vitest-');
  process.env.TMPDIR = dir;
  return () => {
    if (outer === undefined) delete process.env.TMPDIR;
    else process.env.TMPDIR = outer;
    removeTree(dir);
  };
}
