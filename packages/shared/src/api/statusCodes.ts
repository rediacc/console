/**
 * HTTP status code constants
 */
export const HTTP_STATUS = {
  OK: 200,
  BAD_REQUEST: 400,
  UNAUTHORIZED: 401,
  FORBIDDEN: 403,
  NOT_FOUND: 404,
  CONFLICT: 409,
  SERVER_ERROR: 500,
} as const;

/**
 * Error category for semantic error handling
 */
export type ErrorCategory =
  | 'invalid_request'
  | 'auth_required'
  | 'permission_denied'
  | 'not_found'
  | 'conflict'
  | 'server_error'
  | 'general_error';

/**
 * Categorize HTTP status code into semantic error category
 */
export function categorizeHttpStatus(status: number): ErrorCategory {
  switch (status) {
    case HTTP_STATUS.BAD_REQUEST:
      return 'invalid_request';
    case HTTP_STATUS.UNAUTHORIZED:
      return 'auth_required';
    case HTTP_STATUS.FORBIDDEN:
      return 'permission_denied';
    case HTTP_STATUS.NOT_FOUND:
      return 'not_found';
    case HTTP_STATUS.CONFLICT:
      return 'conflict';
    default:
      if (status >= HTTP_STATUS.SERVER_ERROR) {
        return 'server_error';
      }
      return 'general_error';
  }
}

/**
 * Check if status indicates a server error (5xx)
 */
export function isServerError(status: number): boolean {
  return status >= HTTP_STATUS.SERVER_ERROR;
}

/**
 * Check if status indicates an authentication error
 */
export function isAuthError(status: number): boolean {
  return status === HTTP_STATUS.UNAUTHORIZED || status === HTTP_STATUS.FORBIDDEN;
}
