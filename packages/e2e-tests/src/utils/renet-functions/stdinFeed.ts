import type { Writable } from 'node:stream';

/**
 * Write a secret to a child's stdin and close it. A child that exits before the write is flushed
 * raises EPIPE on the stream; with no 'error' listener that is an unhandled stream error, so the
 * listener swallows it and the caller reads the outcome from the child's exit instead.
 */
export function feedStdin(stdin: Writable | null | undefined, text: string): void {
  if (!stdin) return;
  stdin.on('error', () => {});
  stdin.end(text);
}
