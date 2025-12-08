import { showMessage } from './messages';

/**
 * Extract error message from various error formats
 */
export const extractErrorMessage = (error: unknown, fallback: string): string => {
  if (error instanceof Error) {
    return error.message || fallback;
  }
  if (typeof error === 'object' && error !== null) {
    const err = error as Record<string, unknown>;
    if (typeof err.message === 'string') {
      return err.message || fallback;
    }
  }
  if (typeof error === 'string') {
    return error || fallback;
  }
  return fallback;
};

/**
 * Create a standard onError callback
 */
export const createErrorHandler = (fallbackMessage: string) => {
  return (error: unknown): void => {
    const message = extractErrorMessage(error, fallbackMessage);
    showMessage('error', message);
  };
};
