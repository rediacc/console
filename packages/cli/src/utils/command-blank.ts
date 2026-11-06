import { ValidationError } from './errors.js';

// An empty or whitespace-only `-c` is falsy to the one-shot check and would open an interactive shell that waits on stdin, so it is refused before any resolution or SSH.
export function assertCommandNotBlank(options: { command?: string }): void {
  if (options.command !== undefined && options.command.trim() === '') {
    throw new ValidationError(
      'The -c command is empty. Pass a command to run, or omit -c for an interactive shell.'
    );
  }
}
