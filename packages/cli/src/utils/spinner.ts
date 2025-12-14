import ora, { Ora } from 'ora';

let currentSpinner: Ora | null = null;

/**
 * Check if we're in an interactive environment (TTY).
 * Spinners should only be shown in interactive terminals.
 */
function isInteractive(): boolean {
  return process.stdout.isTTY === true;
}

export function startSpinner(text: string): Ora | null {
  // Skip spinner in non-interactive environments (piped output, CI)
  if (!isInteractive()) {
    return null;
  }
  if (currentSpinner) {
    currentSpinner.stop();
  }
  currentSpinner = ora(text).start();
  return currentSpinner;
}

export function stopSpinner(success = true, text?: string): void {
  if (!currentSpinner) return;

  if (success) {
    currentSpinner.succeed(text);
  } else {
    currentSpinner.fail(text);
  }
  currentSpinner = null;
}

export async function withSpinner<T>(
  text: string,
  fn: () => Promise<T>,
  successText?: string
): Promise<T> {
  // In non-interactive environments, skip spinner but still print status
  if (!isInteractive()) {
    try {
      const result = await fn();
      // Always print success message for CI/piped output
      if (successText) {
        process.stdout.write(`✓ ${successText}\n`);
      }
      return result;
    } catch (error) {
      console.error(`✗ ${text.replace('...', '')} failed`);
      throw error;
    }
  }

  // Interactive mode - use spinner
  const spinner = startSpinner(text);
  try {
    const result = await fn();
    spinner?.succeed(successText || text);
    return result;
  } catch (error) {
    spinner?.fail();
    throw error;
  }
}
