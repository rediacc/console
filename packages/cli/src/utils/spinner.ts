import type { Ora } from 'ora';
import { getOutputFormat } from './errors.js';

// esbuild bundles this literal `require` and defers ora's module init
// (chalk / cli-cursor / string-width setup) to the first interactive
// spinner. Spinners only run in a TTY, so piped/CI/JSON-output runs —
// including --version/--help — never pay ora's startup cost.
declare const require: NodeJS.Require;
let oraFactory: typeof import('ora')['default'] | undefined;
function loadOra(): typeof import('ora')['default'] {
  oraFactory ??= (require('ora') as typeof import('ora')).default;
  return oraFactory;
}

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
  const ora = loadOra();
  currentSpinner = ora({ text, stream: process.stderr }).start();
  return currentSpinner;
}

/**
 * Retitle the running spinner in place, for when a step learns mid-flight WHY it
 * is slow (say, queued behind another process). Returns false when there is no
 * spinner to update, which is the caller's cue to say it another way.
 */
export function updateSpinnerText(text: string): boolean {
  if (!currentSpinner) return false;
  currentSpinner.text = text;
  return true;
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
      // Avoid polluting machine-readable output formats
      const format = getOutputFormat();
      if (successText && format === 'table') {
        process.stderr.write(`✓ ${successText}\n`);
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
    spinner?.succeed(successText ?? text);
    return result;
  } catch (error) {
    spinner?.fail();
    throw error;
  }
}
