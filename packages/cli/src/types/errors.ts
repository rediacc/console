// Unified error types for CLI

import { EXIT_CODES } from './index.js';

// Re-export ValidationError from shared package
export { ValidationError } from '@rediacc/shared/errors';

export type ErrorCode =
  | 'GENERAL_ERROR'
  | 'INVALID_REQUEST'
  | 'AUTH_REQUIRED'
  | 'PERMISSION_DENIED'
  | 'NOT_FOUND'
  | 'NETWORK_ERROR'
  | 'SERVER_ERROR'
  | 'VALIDATION_ERROR'
  | 'PRECONDITION_MISMATCH'
  // P4 refusal classes (spec/03 §1). Each string mirrors its exit-code name so
  // `errors[].code` and the process exit code carry the same word.
  | 'AMBIGUOUS'
  | 'STATE_MISMATCH'
  | 'HEALTH_GATE_FAILED'
  | 'INFRA_FAILED'
  | 'BUSY'
  | 'DETACHED';

/**
 * Stable error-code strings for switch-on-able CliError.code.
 * Use these constants instead of string literals so agents can program
 * against a known shape and so renames are caught by the type system.
 */
export const ERROR_CODES = {
  GENERAL_ERROR: 'GENERAL_ERROR',
  INVALID_REQUEST: 'INVALID_REQUEST',
  AUTH_REQUIRED: 'AUTH_REQUIRED',
  PERMISSION_DENIED: 'PERMISSION_DENIED',
  NOT_FOUND: 'NOT_FOUND',
  NETWORK_ERROR: 'NETWORK_ERROR',
  SERVER_ERROR: 'SERVER_ERROR',
  VALIDATION_ERROR: 'VALIDATION_ERROR',
  PRECONDITION_MISMATCH: 'PRECONDITION_MISMATCH',
  AMBIGUOUS: 'AMBIGUOUS',
  STATE_MISMATCH: 'STATE_MISMATCH',
  HEALTH_GATE_FAILED: 'HEALTH_GATE_FAILED',
  INFRA_FAILED: 'INFRA_FAILED',
  BUSY: 'BUSY',
  DETACHED: 'DETACHED',
} as const satisfies Record<ErrorCode, ErrorCode>;

/**
 * Map an ERROR_CODES string to its process exit code (spec/03 §1). The sibling
 * of `httpStatusToExitCode` (types/index.ts): that one turns an HTTP status into
 * an exit code, this one turns a stable error-code name into one, so a thrown
 * CliExitError can derive its exit code from its code alone.
 *
 * Unknown/unmapped codes fall back to GENERAL_ERROR (1). LICENSE_REQUIRED (10)
 * is deliberately absent: renet's exit 10 is propagated verbatim by the recovery
 * framework, never reconstructed from a code string here.
 */
export function errorToExitCode(code: string): number {
  const map: Record<string, number> = {
    [ERROR_CODES.GENERAL_ERROR]: EXIT_CODES.GENERAL_ERROR,
    [ERROR_CODES.INVALID_REQUEST]: EXIT_CODES.INVALID_ARGUMENTS,
    [ERROR_CODES.VALIDATION_ERROR]: EXIT_CODES.INVALID_ARGUMENTS,
    [ERROR_CODES.PRECONDITION_MISMATCH]: EXIT_CODES.INVALID_ARGUMENTS,
    [ERROR_CODES.AUTH_REQUIRED]: EXIT_CODES.AUTH_REQUIRED,
    [ERROR_CODES.PERMISSION_DENIED]: EXIT_CODES.PERMISSION_DENIED,
    [ERROR_CODES.NOT_FOUND]: EXIT_CODES.NOT_FOUND,
    [ERROR_CODES.NETWORK_ERROR]: EXIT_CODES.NETWORK_ERROR,
    [ERROR_CODES.SERVER_ERROR]: EXIT_CODES.API_ERROR,
    [ERROR_CODES.AMBIGUOUS]: EXIT_CODES.AMBIGUOUS,
    [ERROR_CODES.STATE_MISMATCH]: EXIT_CODES.STATE_MISMATCH,
    [ERROR_CODES.HEALTH_GATE_FAILED]: EXIT_CODES.HEALTH_GATE_FAILED,
    [ERROR_CODES.INFRA_FAILED]: EXIT_CODES.INFRA_FAILED,
    [ERROR_CODES.BUSY]: EXIT_CODES.BUSY,
    [ERROR_CODES.DETACHED]: EXIT_CODES.DETACHED,
  };
  return map[code] ?? EXIT_CODES.GENERAL_ERROR;
}

/**
 * One concrete next-action option a human or agent can take. The CLI
 * surfaces these in error envelopes (JSON: errors[].next.options[]; TTY:
 * "What to do:" bulleted list). Agents should relay `run` verbatim to the
 * human rather than synthesizing their own command.
 */
interface NextActionOption {
  /** Human-readable: "Re-read current digest, then retry with --current" */
  description: string;
  /** Canonical command the user pastes: "rdc repo secret get --name X --key Y" */
  run: string;
}

/**
 * Structured "what to do next" hint attached to a CliError. Replaces
 * unstructured English in `guidance`. When set, both JSON and TTY paths
 * render it; MCP tools see it through the JSON envelope automatically.
 */
export interface NextAction {
  /** One-liner: "Provide the current value or acknowledge rotation." */
  summary: string;
  options?: NextActionOption[];
}

export interface CliError {
  code: string;
  message: string;
  details?: string[];
  exitCode: number;
  retryable?: boolean;
  /** Free-text hint (legacy). Prefer `next` for new code. */
  guidance?: string;
  /** Structured next-action hint, rendered in both JSON and TTY output. */
  next?: NextAction;
}
