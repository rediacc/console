/**
 * Shared error types for CLI and Web.
 * Provides a consistent error hierarchy across platforms.
 */

export type { ApiErrorCode } from '../api/client/error';
// Re-export API client errors
export { API_ERROR_CODES, ApiClientError } from '../api/client/error';

// Export validation error
export { ValidationError } from './ValidationError';
