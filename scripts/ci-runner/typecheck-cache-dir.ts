/**
 * The incremental typecheck cache's directory per checkout, in a module of its own: run.ts and lease-seed.ts need only this path, and importing it from typecheck-incremental.ts loaded that module's JSONC parser too, so the runner could not start where no full install exists (the kept-clone fixture of test_gate_ci_runner.py, `Cannot find module '@humanwhocodes/momoa'`).
 */
import os from 'node:os';
import path from 'node:path';

/** The cache directory of the checkout at `root`: one directory per checkout path, so a lease starts cold unless lease-seed.ts seeds it (PLAN-drain-throughput DT8). */
export function cacheDirFor(root: string, home: string = os.homedir()): string {
  return path.join(
    home,
    '.cache',
    'rediacc-typecheck',
    root.replace(/^\/+/, '').replace(/\//g, '-')
  );
}
