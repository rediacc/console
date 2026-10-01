/**
 * Console Color Utilities
 *
 * ANSI color codes for terminal output.
 * Colors are automatically disabled when stdout is not a TTY.
 */

const isTTY = process.stdout.isTTY;

export const RED = isTTY ? '\x1b[31m' : '';
export const GREEN = isTTY ? '\x1b[32m' : '';
export const YELLOW = isTTY ? '\x1b[33m' : '';
export const BLUE = isTTY ? '\x1b[34m' : '';
export const DIM = isTTY ? '\x1b[2m' : '';
export const NC = isTTY ? '\x1b[0m' : ''; // No Color (reset)

/**
 * Join a gate's final report lines into one string for a single `console.log`/`console.error` call.
 *
 * NAMES A SHAPE THAT ALREADY EXISTED, IDENTICALLY, IN THREE FILES. `check-backup-bucket-conformance.ts`, `check-ci-fetch-integrity.ts` and `check-deps.ts` each built their closing report the same way: a template-literal head plus several string-literal continuations, each carrying its own trailing `\n`, joined with `+`. `check:ci-shape-duplication` measured the six-line span byte-identical
 * across all three. Each line here is expected to already carry the newline it wants BETWEEN itself and the next line (or none, for the last), matching what those three call sites already wrote -- this is a name for the existing convention, not a new one.
 */
export function joinReport(...lines: string[]): string {
  return lines.join('');
}

/**
 * Print several lines to stderr as ONE `console.error` call.
 *
 * NAMES THE SHAPE `check:ci-shape-duplication` found in `check-docker-image-freshness.ts`, `check-embed-asset-freshness.ts` and `check-translation-key-usage.ts`: a run of consecutive `console.error(...)` calls, each carrying one line of a failure report. The output is byte-identical to the run it replaces (each line followed by a newline), so a caller keeps its wording and only stops repeating the call.
 */
export function errorLines(...lines: string[]): void {
  console.error(lines.join('\n'));
}
