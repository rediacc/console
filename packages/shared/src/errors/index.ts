/**
 * Shared error types for CLI and Web.
 * Provides a consistent error hierarchy across platforms.
 */

// Re-export API client errors
export { ApiClientError, API_ERROR_CODES } from '../api/client/error';
export type { ApiErrorCode } from '../api/client/error';

// Export validation error
export { ValidationError } from './ValidationError';
