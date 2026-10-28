import { DEFAULTS } from '@rediacc/shared/config';
import { outputService } from '../services/core/output.js';
import {
  currentRequestContext,
  DispatchExit,
  exitProcess,
  writeStdout,
} from '../services/core/request-context.js';
import { telemetryService } from '../services/telemetry/telemetry.js';
import { type CliError, ERROR_CODES, type NextAction, ValidationError } from '../types/errors.js';
import { EXIT_CODES, type OutputFormat } from '../types/index.js';
import { CliExitError } from './cli-exit-error.js';

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

/** Determine if an error is retryable based on exit code */
function isRetryable(error: CliError): boolean {
  if (error.retryable !== undefined) return error.retryable;
  const retryableCodes: number[] = [
    EXIT_CODES.NETWORK_ERROR,
    EXIT_CODES.RATE_LIMITED,
    EXIT_CODES.API_ERROR,
  ];
  return retryableCodes.includes(error.exitCode);
}

/** A CliError that also carries the named machine-readable code of the failure behind it. */
type NamedCliError = CliError & { errorCode?: string };

/**
 * A DispatchExit that keeps the named code and guidance of the failure that ended the command. The served result is built from it, so a command that opens its own SSH connection reports the same errorCode an executor.execute failure does. Still a DispatchExit, so every instanceof check on it holds.
 */
export class DispatchFailure extends DispatchExit {
  constructor(
    code: number,
    readonly errorCode: string,
    readonly guidance: string | undefined
  ) {
    super(code);
  }
}

/** The named code and guidance of an error that carries one (an SSH connect failure), or undefined. */
export function namedFailureOf(
  error: unknown
): { errorCode: string; guidance: string | undefined } | undefined {
  if (error instanceof DispatchFailure) {
    return { errorCode: error.errorCode, guidance: error.guidance };
  }
  const named = sshConnectError(error);
  return named?.errorCode ? { errorCode: named.errorCode, guidance: named.guidance } : undefined;
}

/** Get actionable guidance for an error */
function getGuidance(error: CliError): string | undefined {
  if (error.guidance) return error.guidance;
  const map: Record<number, string> = {
    [EXIT_CODES.AUTH_REQUIRED]: 'Run "rdc subscription login" or set REDIACC_MASTER_PASSWORD',
    [EXIT_CODES.PERMISSION_DENIED]: 'Check team permissions or contact admin',
    [EXIT_CODES.NOT_FOUND]: 'Verify the resource name with "rdc machine status" or "rdc repo list"',
    [EXIT_CODES.NETWORK_ERROR]: 'Check network connectivity and retry',
    [EXIT_CODES.RATE_LIMITED]: 'Wait and retry after a brief delay',
    [EXIT_CODES.PAYMENT_REQUIRED]: 'Upgrade subscription or check usage limits',
    [EXIT_CODES.INVALID_ARGUMENTS]: 'Check command usage with --help',
  };
  return map[error.exitCode];
}

/** Output error in JSON envelope format */
function outputJsonError(cliError: CliError): void {
  const envelope = {
    success: false,
    command: outputService.getCommandName() ?? DEFAULTS.TELEMETRY.UNKNOWN,
    data: null,
    errors: [
      {
        code: cliError.code,
        message: cliError.message,
        ...(cliError.details?.length && { details: cliError.details }),
        ...((cliError as NamedCliError).errorCode && {
          errorCode: (cliError as NamedCliError).errorCode,
        }),
        retryable: isRetryable(cliError),
        guidance: getGuidance(cliError),
        ...(cliError.next && { next: cliError.next }),
      },
    ],
    warnings: outputService.getWarnings(),
    metrics: { duration_ms: outputService.getDurationMs() },
  };
  // writeStdout, not process.stdout: inside an executor dispatch the envelope belongs to the
  // request that failed, and the client reads it from there.
  writeStdout(`${JSON.stringify(envelope, null, 2)}\n`);
}

/** Output error in text format */
function outputTextError(cliError: CliError): void {
  outputService.error(`Error: ${cliError.message}`);
  if (cliError.details?.length) {
    for (const detail of cliError.details) {
      if (detail !== cliError.message) {
        outputService.error(`  - ${detail}`);
      }
    }
  }
  if (cliError.next) {
    outputService.error('');
    outputService.error(`What to do: ${cliError.next.summary}`);
    for (const opt of cliError.next.options ?? []) {
      outputService.error(`  • ${opt.description}`);
      outputService.error(`      ${opt.run}`);
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

  // Fire-and-forget telemetry shutdown (don't block exit). Inside an executor dispatch the process keeps serving other callers, and a shut-down SDK cannot be restarted, so one failed request would silence telemetry for all of them.
  if (!currentRequestContext()) {
    void telemetryService.shutdown().catch(() => {
      // Ignore shutdown errors - we're exiting anyway
    });
  }

  // Exit synchronously. On a laptop this is process.exit() as it always was. Inside an executor dispatch it throws instead, because a command that fails
  // for one tenant must not kill the process serving everyone else.
  const named = namedFailureOf(error);
  if (named && currentRequestContext()) {
    throw new DispatchFailure(cliError.exitCode, named.errorCode, named.guidance);
  }
  exitProcess(cliError.exitCode);
}

/**
 * Authentication/credential error (master password, subscription token).
 */
export class AuthError extends Error {
  readonly exitCode: number;
  constructor(message: string, exitCode: number = EXIT_CODES.AUTH_REQUIRED) {
    super(message);
    this.name = 'AuthError';
    this.exitCode = exitCode;
  }
}

/**
 * Validation error that carries a structured `next` action hint.
 * Use this (instead of plain ValidationError) when you can suggest
 * concrete commands the user/agent can run to resolve the failure.
 */
export class PreconditionValidationError extends ValidationError {
  readonly next: NextAction;
  readonly code: string;
  constructor(message: string, next: NextAction, code: string = ERROR_CODES.PRECONDITION_MISMATCH) {
    super(message);
    // ValidationError's `name` is a read-only literal; instanceof PreconditionValidationError
    // is sufficient discriminator. Don't reassign.
    this.next = next;
    this.code = code;
  }
}

/**
 * The remote-config adapter's errors (adapters/remote-config-errors.ts), matched by name so this module does not
 * import the adapter. Before 2026-09-26 every one reached the envelope as GENERAL_ERROR, so an agent could not tell
 * "re-enroll this device" from a crash; the eu live test showed it on RemoteStaleSlotError after a CEK rotation.
 */
const REMOTE_CONFIG_ERRORS: Record<
  string,
  {
    code: 'AUTH_REQUIRED' | 'NETWORK_ERROR' | 'PERMISSION_DENIED' | 'NOT_FOUND' | 'STATE_MISMATCH';
    retryable: boolean;
  }
> = {
  RemoteAuthError: { code: 'AUTH_REQUIRED', retryable: false },
  RemoteTokenExpiredError: { code: 'AUTH_REQUIRED', retryable: false },
  RemoteTokenIpMismatchError: { code: 'AUTH_REQUIRED', retryable: false },
  RemoteStaleSlotError: { code: 'AUTH_REQUIRED', retryable: false },
  RemotePasskeySecretMissingError: { code: 'AUTH_REQUIRED', retryable: false },
  RemoteUnreachableError: { code: 'NETWORK_ERROR', retryable: true },
  RemoteWriteFailedClosedError: { code: 'NETWORK_ERROR', retryable: true },
  RemoteTeamForbiddenError: { code: 'PERMISSION_DENIED', retryable: false },
  RemoteTeamNotFoundError: { code: 'NOT_FOUND', retryable: false },
  RemoteVersionConflictError: { code: 'STATE_MISMATCH', retryable: true },
  RemotePreconditionError: { code: 'STATE_MISMATCH', retryable: false },
  RemoteRollbackError: { code: 'STATE_MISMATCH', retryable: false },
  RemoteConfigUndecryptableError: { code: 'STATE_MISMATCH', retryable: false },
};

/** The CliError for a remote-config adapter error, or undefined for any other error. */
function remoteConfigError(error: unknown): CliError | undefined {
  const remote = error instanceof Error ? REMOTE_CONFIG_ERRORS[error.name] : undefined;
  if (!remote) return undefined;
  const message = (error as Error).message;
  return {
    code: ERROR_CODES[remote.code],
    message,
    exitCode: EXIT_CODES[remote.code],
    retryable: remote.retryable,
    // The message already names the remedy (`rdc config remote enable`, `rdc subscription login`, ...); the exit code's generic guidance would contradict it.
    guidance: message,
  };
}

/**
 * A named SSH connect failure (remote/sftp/connect-error.ts), matched by name like the remote-config errors so this module does not import the SFTP client.
 */
function sshConnectError(error: unknown): NamedCliError | undefined {
  if (!(error instanceof Error) || error.name !== 'SshConnectError') return undefined;
  const named = error as Error & {
    exitCode?: number;
    retryable?: boolean;
    guidance?: string;
    errorCode?: string;
  };
  const network = named.exitCode === EXIT_CODES.NETWORK_ERROR;
  return {
    code: network ? ERROR_CODES.NETWORK_ERROR : ERROR_CODES.GENERAL_ERROR,
    message: error.message,
    exitCode: network ? EXIT_CODES.NETWORK_ERROR : EXIT_CODES.GENERAL_ERROR,
    retryable: named.retryable === true,
    ...(named.errorCode && { errorCode: named.errorCode }),
    ...(named.guidance && { guidance: named.guidance }),
  };
}

/** The CliError for an error matched by name (remote-config or SSH connect), or undefined. */
function namedCliError(error: unknown): CliError | undefined {
  return remoteConfigError(error) ?? sshConnectError(error);
}

/**
 * Normalize various error types into a consistent CliError structure.
 */
function normalizeError(error: unknown): CliError {
  // CliExitError already carries its code, exit code, and any next-action hint;
  // pass them through unchanged so the P4 refusal classes (AMBIGUOUS, STATE_MISMATCH, ...) surface with the exit code they were thrown with.
  if (error instanceof CliExitError) {
    return {
      code: error.code,
      message: error.message,
      exitCode: error.exitCode,
      ...(error.details?.length && { details: error.details }),
      ...(error.retryable !== undefined && { retryable: error.retryable }),
      ...(error.next && { next: error.next }),
      ...(error.guidance && { guidance: error.guidance }),
    };
  }

  if (error instanceof AuthError) {
    return {
      code: ERROR_CODES.AUTH_REQUIRED,
      message: error.message,
      exitCode: error.exitCode,
    };
  }

  // PreconditionValidationError must come BEFORE ValidationError since it extends.
  if (error instanceof PreconditionValidationError) {
    return {
      code: error.code,
      message: error.message,
      exitCode: EXIT_CODES.INVALID_ARGUMENTS,
      next: error.next,
    };
  }

  if (error instanceof ValidationError) {
    return {
      code: ERROR_CODES.VALIDATION_ERROR,
      message: error.message,
      exitCode: EXIT_CODES.INVALID_ARGUMENTS,
    };
  }

  const named = namedCliError(error);
  if (named) return named;

  // Unknown error
  return {
    code: ERROR_CODES.GENERAL_ERROR,
    message: error instanceof Error ? error.message : String(error),
    exitCode: EXIT_CODES.GENERAL_ERROR,
  };
}

export { ValidationError };
