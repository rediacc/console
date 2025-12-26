// Unified error types for CLI

const _ERROR_CODES = {
  GENERAL_ERROR: 'GENERAL_ERROR',
  INVALID_REQUEST: 'INVALID_REQUEST',
  AUTH_REQUIRED: 'AUTH_REQUIRED',
  PERMISSION_DENIED: 'PERMISSION_DENIED',
  NOT_FOUND: 'NOT_FOUND',
  NETWORK_ERROR: 'NETWORK_ERROR',
  SERVER_ERROR: 'SERVER_ERROR',
  VALIDATION_ERROR: 'VALIDATION_ERROR',
} as const;

export type ErrorCode = (typeof _ERROR_CODES)[keyof typeof _ERROR_CODES];

export interface CliError {
  code: ErrorCode;
  message: string;
  details?: string[];
  exitCode: number;
}

/**
 * Validation error for invalid user input or missing required options.
 * Thrown when command arguments/options don't meet requirements.
 */
export class ValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ValidationError';
  }
}
