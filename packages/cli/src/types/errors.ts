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
  | 'VALIDATION_ERROR';

export interface CliError {
  code: string;
  message: string;
  details?: string[];
  exitCode: number;
}
