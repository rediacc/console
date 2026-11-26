/**
 * A gate's `--selftest` ends with the control harness that used to be registered beside it
 * (agent/plans/PLAN-tooling-code-reduction.md D4: the `.control.ts` registrations fold into their
 * gate's `--selftest`). The gate's run line is then the usual `tsx <gate> --selftest && tsx <gate>`,
 * and the harness's cases still red the run when one fails.
 *
 * THE CALLER WRITES THE `import()` WITH A LITERAL PATH, `foldedControl(() => import('../__tests__/x.control.ts'))`,
 * so knip and the path tracer follow it to the harness as they followed the npm script before. A
 * harness runs its cases on import and exits with its own code; when it returns instead, the process
 * is left to drain its event loop (as the old standalone run line did), so a harness that starts async
 * cases and reports through `process.exitCode` is not cut off, and the gate exits with that code.
 *
 * NEVER AWAITED. Some harnesses import the gate they control, and a gate whose top-level await
 * imports a module importing that gate never settles. Started un-awaited, the import evaluates after
 * the gate module has finished, so the harness reads a complete module.
 *
 * A harness that throws, or fails to load, is a failure (rc 1), never a pass: an unrun control
 * proves nothing.
 */
import process from 'node:process';

/** True on a `--selftest` run, which has then started the harness: the caller must not run the gate. False otherwise, and nothing is loaded. */
export function foldedControl(load: () => Promise<unknown>): boolean {
  if (!process.argv.includes('--selftest')) return false;
  load().then(
    () => undefined,
    (e: unknown) => {
      console.error(
        `✗ control harness ${harnessName(load)} did not run: ${e instanceof Error ? e.message : String(e)}`
      );
      process.exit(1);
    }
  );
  return true;
}

/** The literal path inside the caller's `() => import('<path>')`, so a failure names the harness. */
export function harnessName(load: () => Promise<unknown>): string {
  return /import\(\s*['"`]([^'"`]+)['"`]/.exec(load.toString())?.[1] ?? '(unnamed harness)';
}
