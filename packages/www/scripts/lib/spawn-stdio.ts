/**
 * spawnSync's stdio, read safely.
 *
 * `@types/node` declares `stdout`/`stderr` as `string`, but Node returns
 * `undefined` when the process never STARTED. That is exactly the case every
 * `status !== 0` error branch is written for: a missing binary gives ENOENT and
 * `status === null`, so the branch is entered and `.slice()` on the stderr throws
 * "Cannot read properties of undefined" INSTEAD of raising the intended
 * "... failed" error. Verified against a real missing binary.
 *
 * Widened across a function boundary because TypeScript narrows an annotated
 * const straight back to the lying initializer type.
 */
export function stdio(value: string | null | undefined): string {
  return value ?? '';
}
