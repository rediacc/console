// Unified error types for CLI

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
  | 'PRECONDITION_MISMATCH';

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
} as const satisfies Record<ErrorCode, ErrorCode>;

/**
 * One concrete next-action option a human or agent can take. The CLI
 * surfaces these in error envelopes (JSON: errors[].next.options[]; TTY:
 * "What to do:" bulleted list). Agents should relay `run` verbatim to the
 * human rather than synthesizing their own command.
 */
export interface NextActionOption {
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
