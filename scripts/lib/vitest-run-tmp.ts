/**
 * Vitest `globalSetup` for every vitest config in the repo: one run directory per `vitest run`, with TMPDIR, TEMP and TMP (the pair `os.tmpdir()` reads on Windows) pointed at it
 * BEFORE the workers fork, so every `mkdtempSync(os.tmpdir(), ...)` a test leaks lands under it. Teardown removes it; a
 * run killed before teardown leaves a stamped directory that the next run's `runDir` sweeps (scripts/lib/runtmp.ts).
 *
 * Listed in each config as `globalSetup`, as a path relative to that config (agent/plans/PLAN-host-temp-disposal.md HT7).
 * Control: scripts/__tests__/vitest-run-tmp.control.ts.
 */
import process from 'node:process';
import { removeTree, runDir } from './runtmp.js';

const VARS = ['TMPDIR', 'TEMP', 'TMP'] as const;

export default function setup(): () => void {
  const outer = VARS.map((k) => [k, process.env[k]] as const);
  const dir = runDir('rediacc-vitest-');
  for (const k of VARS) process.env[k] = dir;
  return () => {
    for (const [k, v] of outer) {
      if (v === undefined) delete process.env[k];
      else process.env[k] = v;
    }
    removeTree(dir);
  };
}
