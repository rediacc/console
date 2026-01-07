import { CliApiError } from '../services/api.js';
import { AuthError } from '../services/auth.js';
import { outputService } from '../services/output.js';
import { telemetryService } from '../services/telemetry.js';
import { type CliError, ValidationError } from '../types/errors.js';
import { EXIT_CODES, type OutputFormat } from '../types/index.js';

// Global output format (set by main program before command execution)
let currentOutputFormat: OutputFormat = 'table';

/**
 * Set the current output format for error handling.
 * Should be called after parsing CLI options but before running commands.
 */
export function setOutputFormat(format: OutputFormat): void {
  currentOutputFormat = format;
}

export function getOutputFormat(): OutputFormat {
  return currentOutputFormat;
}

/**
 * Handle errors with format-aware output.
 *
 * - JSON mode: outputs structured error JSON to stdout (for piping)
 * - Other modes: outputs error message to stderr
 */
export function handleError(error: unknown): never {
  const cliError = normalizeError(error);

  // Track error in telemetry
  telemetryService.trackError(error, {
    code: cliError.code,
    exitCode: cliError.exitCode,
    hasDetails: Boolean(cliError.details?.length),
  });

  if (currentOutputFormat === 'json') {
    // JSON mode: output error as JSON to stdout for piping
    const errorResponse = {
      success: false,
      error: {
        code: cliError.code,
        message: cliError.message,
        ...(cliError.details?.length && { details: cliError.details }),
      },
      exitCode: cliError.exitCode,
    };
    // eslint-disable-next-line no-console -- JSON errors must go to stdout for piping
    console.log(JSON.stringify(errorResponse, null, 2));
  } else {
    // Non-JSON mode: output to stderr
    outputService.error(`Error: ${cliError.message}`);
    if (cliError.details?.length) {
      for (const detail of cliError.details) {
        if (detail !== cliError.message) {
          outputService.error(`  - ${detail}`);
        }
      }
    }
  }

  // Shutdown telemetry before exit (fire and forget with short timeout)
  void telemetryService.shutdown().finally(() => {
    process.exit(cliError.exitCode);
  });

  // If shutdown takes too long, exit anyway after 2 seconds
  setTimeout(() => {
    process.exit(cliError.exitCode);
  }, 2000).unref();

  // This never returns, but TypeScript needs a return type
  throw new Error('Unreachable');
}

/**
 * Normalize various error types into a consistent CliError structure.
 */
export function normalizeError(error: unknown): CliError {
  if (error instanceof CliApiError) {
    return {
      code: error.code,
      message: error.message,
      details: error.details,
      exitCode: error.exitCode,
    };
  }

  if (error instanceof AuthError) {
    return {
      code: 'AUTH_REQUIRED',
      message: error.message,
      exitCode: error.exitCode,
    };
  }

  if (error instanceof ValidationError) {
    return {
      code: 'VALIDATION_ERROR',
      message: error.message,
      exitCode: EXIT_CODES.INVALID_ARGUMENTS,
    };
  }

  // Unknown error
  return {
    code: 'GENERAL_ERROR',
    message: error instanceof Error ? error.message : String(error),
    exitCode: EXIT_CODES.GENERAL_ERROR,
  };
}

export { ValidationError };
