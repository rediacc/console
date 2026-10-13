import { format } from 'node:util';

/**
 * Progress and diagnostic output for the e2e harness and tests.
 *
 * Writes to stdout with console.log semantics (util.format placeholders and
 * object inspection), without going through the console global that the
 * no-console rule guards. Warnings and errors keep using console.warn and
 * console.error, which that rule permits.
 */
export function log(...args: unknown[]): void {
  process.stdout.write(`${format(...args)}\n`);
}
