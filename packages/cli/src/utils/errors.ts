import { ApiClientError } from '@rediacc/shared/api';
import { CliApiError } from '../services/api.js';
import { AuthError } from '../services/auth.js';
import { outputService } from '../services/output.js';
import { telemetryService } from '../services/telemetry.js';
import { type CliError, ValidationError } from '../types/errors.js';
import { EXIT_CODES, httpStatusToExitCode, type OutputFormat } from '../types/index.js';

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

/** Output error in JSON format */
function outputJsonError(cliError: CliError): void {
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
}

/** Output error in text format */
function outputTextError(cliError: CliError): void {
  outputService.error(`Error: ${cliError.message}`);
  if (!cliError.details?.length) {
    return;
  }
  for (const detail of cliError.details) {
    if (detail !== cliError.message) {
      outputService.error(`  - ${detail}`);
    }
  }
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
    outputJsonError(cliError);
  } else {
    outputTextError(cliError);
  }

  // Fire-and-forget telemetry shutdown (don't block exit)
  void telemetryService.shutdown().catch(() => {
    // Ignore shutdown errors - we're exiting anyway
  });

  // Exit synchronously - process.exit() never returns, satisfying the `never` return type
  process.exit(cliError.exitCode);
}

/**
 * Normalize various error types into a consistent CliError structure.
 */
function normalizeError(error: unknown): CliError {
  if (error instanceof CliApiError) {
    return {
      code: error.code,
      message: error.message,
      details: error.details,
      exitCode: error.exitCode,
    };
  }

  // Handle ApiClientError (base class) - map HTTP status to exit code
  // This must come AFTER CliApiError check since CliApiError extends ApiClientError
  if (error instanceof ApiClientError) {
    // Map HTTP status code to Unix-compatible exit code
    const httpStatus = error.response?.failure ?? 0;
    const exitCode = httpStatus > 0 ? httpStatusToExitCode(httpStatus) : EXIT_CODES.GENERAL_ERROR;
    return {
      code: error.code,
      message: error.message,
      details: error.details,
      exitCode,
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
