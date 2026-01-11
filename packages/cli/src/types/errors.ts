// Unified error types for CLI

// Re-export ValidationError from shared package
export { ValidationError } from '@rediacc/shared/errors';

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
  code: string;
  message: string;
  details?: string[];
  exitCode: number;
}
