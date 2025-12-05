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
 * Standard error handler for mutations
 */
export const handleMutationError = (error: unknown, fallbackMessage: string): void => {
  const message = extractErrorMessage(error, fallbackMessage);
  showMessage('error', message);
};

/**
 * Create a standard onError callback
 */
export const createErrorHandler = (fallbackMessage: string) => {
  return (error: unknown): void => {
    handleMutationError(error, fallbackMessage);
  };
};

/**
 * Create a standard onSuccess callback with message
 */
export const createSuccessHandler = (message: string) => {
  return (): void => {
    showMessage('success', message);
  };
};

export interface MutationCallbackOptions<TData = unknown, TVariables = unknown> {
  successMessage?: string | ((data: TData, variables: TVariables) => string);
  errorMessage: string;
  onSuccess?: (data: TData, variables: TVariables) => void;
  onError?: (error: unknown) => void;
}

/**
 * Create standard mutation callbacks with consistent error/success handling
 */
export const createMutationCallbacks = <TData = unknown, TVariables = unknown>(
  options: MutationCallbackOptions<TData, TVariables>
) => {
  const {
    successMessage,
    errorMessage,
    onSuccess: customOnSuccess,
    onError: customOnError,
  } = options;

  return {
    onSuccess: (data: TData, variables: TVariables) => {
      if (successMessage) {
        const message =
          typeof successMessage === 'function' ? successMessage(data, variables) : successMessage;
        showMessage('success', message);
      }
      customOnSuccess?.(data, variables);
    },
    onError: (error: unknown) => {
      handleMutationError(error, errorMessage);
      customOnError?.(error);
    },
  };
};
