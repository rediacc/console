import type { ApiResponse } from '../../types/api';

/**
 * Base error class for API client errors.
 * Platform-specific implementations can extend this (e.g., CLI adds exitCode).
 */
export class ApiClientError extends Error {
  public override readonly name: string = 'ApiClientError';

  constructor(
    message: string,
    public readonly code: string,
    public readonly details: string[] = [],
    public readonly response?: ApiResponse
  ) {
    super(message);
    // Maintain proper prototype chain for instanceof checks
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/**
 * Standard error codes for API errors.
 */
export const API_ERROR_CODES = {
  UNAUTHORIZED: 'UNAUTHORIZED',
  FORBIDDEN: 'FORBIDDEN',
  NOT_FOUND: 'NOT_FOUND',
  BAD_REQUEST: 'BAD_REQUEST',
  CONFLICT: 'CONFLICT',
  SERVER_ERROR: 'SERVER_ERROR',
  NETWORK_ERROR: 'NETWORK_ERROR',
  GENERAL_ERROR: 'GENERAL_ERROR',
} as const;

export type ApiErrorCode = (typeof API_ERROR_CODES)[keyof typeof API_ERROR_CODES];
