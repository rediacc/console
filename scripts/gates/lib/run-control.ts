/**
 * Finish a gate's `--selftest` with the control harness that used to be registered beside it
 * (agent/plans/PLAN-tooling-code-reduction.md D4: the `.control.ts` registrations fold into their
 * gate's `--selftest`). The gate's run line is then the usual `tsx <gate> --selftest && tsx <gate>`,
 * and the harness's cases still red the run when one fails.
 *
 * THE CALLER WRITES THE `import()` WITH A LITERAL PATH, `finishWithControl(import('../__tests__/x.control.ts'), ...)`,
 * so knip and the path tracer follow it to the harness as they followed the npm script before. A
 * harness runs its cases on import and exits with its own code; when it returns instead, the gate
 * exits with whatever `process.exitCode` the harness left, else 0.
 *
 * NEVER AWAIT IT AT A MODULE'S TOP LEVEL. Some harnesses import the gate they control, and a gate
 * whose top-level await imports a module importing that gate never settles. Started un-awaited, the
 * import evaluates after the gate module has finished, so the harness reads a complete module.
 *
 * A harness that throws, or fails to load, is a failure (rc 1), never a pass: an unrun control
 * proves nothing.
 */
import process from 'node:process';

export function finishWithControl(loaded: Promise<unknown>, harness: string): void {
  loaded.then(
    () => process.exit(process.exitCode ?? 0),
    (e: unknown) => {
      console.error(
        `✗ control ${harness} did not run: ${e instanceof Error ? e.message : String(e)}`
      );
      process.exit(1);
    }
  );
}
