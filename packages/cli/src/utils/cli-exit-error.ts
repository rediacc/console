/**
 * CliExitError — a thrown error that carries a stable error code and the process
 * exit code that goes with it (spec/03 §1). The P4 refusal classes (AMBIGUOUS,
 * STATE_MISMATCH, HEALTH_GATE_FAILED, INFRA_FAILED, BUSY, DETACHED) have no
 * bespoke Error subclass the way AuthError/ValidationError do; rather than one
 * class per code, this one class carries the code and derives its exit code from
 * it via `errorToExitCode`, so `handleError` maps it faithfully.
 *
 * Deliberately light: it imports only the error-code constants (no output,
 * telemetry, or request-context), so the pure addressing modules that throw it
 * (services/addressing/*) stay cheap to import and to unit-test.
 */

import { ERROR_CODES, errorToExitCode, type NextAction } from '../types/errors.js';

export interface CliExitErrorOptions {
  /** Extra lines rendered under the message (TTY) and in `errors[].details` (JSON). */
  details?: string[];
  /** Structured "what to do next" hint, rendered in both JSON and TTY output. */
  next?: NextAction;
  /** Override the retryable flag; defaults to the code's class (§1 table). */
  retryable?: boolean;
  /**
   * Override the derived exit code. Almost never needed — the whole point is
   * that the code determines the exit code — but a couple of §1 deviations
   * (e.g. propagating a remote exit code verbatim) want an explicit value.
   */
  exitCode?: number;
}

export class CliExitError extends Error {
  readonly code: string;
  readonly exitCode: number;
  readonly details?: string[];
  readonly next?: NextAction;
  readonly retryable?: boolean;

  constructor(code: string, message: string, options: CliExitErrorOptions = {}) {
    super(message);
    this.name = 'CliExitError';
    this.code = code;
    this.exitCode = options.exitCode ?? errorToExitCode(code);
    this.details = options.details;
    this.next = options.next;
    this.retryable = options.retryable;
  }
}

/** `AMBIGUOUS` (exit 11): a name resolution needed a guess and refused. */
export function ambiguous(message: string, options?: CliExitErrorOptions): CliExitError {
  return new CliExitError(ERROR_CODES.AMBIGUOUS, message, options);
}

/** `STATE_MISMATCH` (exit 12): config's derived answer contradicts user or machine. */
export function stateMismatch(message: string, options?: CliExitErrorOptions): CliExitError {
  return new CliExitError(ERROR_CODES.STATE_MISMATCH, message, options);
}

/**
 * `BUSY` (exit 15): another process holds the resource; the same command can
 * succeed later untouched.
 *
 * `retryable` is set explicitly because `isRetryable` only defaults the network
 * classes to true, and "come back in a moment" is the entire meaning of BUSY.
 * Callers may still override it via `options`.
 */
export function busy(message: string, options?: CliExitErrorOptions): CliExitError {
  return new CliExitError(ERROR_CODES.BUSY, message, { retryable: true, ...options });
}

/** `NOT_FOUND` (exit 5): a named resource does not exist in config or on the machine. */
export function notFound(message: string, options?: CliExitErrorOptions): CliExitError {
  return new CliExitError(ERROR_CODES.NOT_FOUND, message, options);
}
