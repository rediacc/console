import { useCallback, useState } from 'react';
import { showMessage } from '@/utils/messages';
import { DEFAULTS } from '@rediacc/shared/config';

/**
 * Result of an async action
 */
export interface AsyncActionResult<T = unknown> {
  /** Whether the action succeeded */
  success: boolean;
  /** Data returned from the action */
  data?: T;
  /** Error message if failed */
  error?: string;
}

/**
 * Configuration for an async action
 */
export interface AsyncActionConfig {
  /** Success message to display */
  successMessage?: string;
  /** Error message to display (defaults to error.message) */
  errorMessage?: string;
  /** Skip showing the default error message */
  skipErrorMessage?: boolean;
  /** Skip showing the success message */
  skipSuccessMessage?: boolean;
  /** Custom error handler */
  onError?: (error: Error) => void;
  /** Custom success handler */
  onSuccess?: (data: unknown) => void;
}

/**
 * Return type for useAsyncAction hook
 */
export interface UseAsyncActionReturn {
  /** Execute an async action with error handling */
  execute: <T>(
    operation: () => Promise<T>,
    config?: AsyncActionConfig
  ) => Promise<AsyncActionResult<T>>;
  /** Whether an action is currently executing */
  isExecuting: boolean;
  /** Last error message (null if no error) */
  error: string | null;
  /** Reset error state */
  resetError: () => void;
}

/**
 * Hook for executing async actions with standardized error handling
 *
 * Replaces repetitive try/catch patterns with consistent error handling,
 * automatic message display, and loading state management.
 *
 * @example
 * const { execute, isExecuting } = useAsyncAction()
 *
 * const handleSubmit = async (data: FormData) => {
 *   const result = await execute(
 *     () => createMutation.mutateAsync(data),
 *     {
 *       successMessage: 'Item created successfully',
 *       errorMessage: 'Failed to create item'
 *     }
 *   )
 *
 *   if (result.success) {
 *     closeModal()
 *     refetch()
 *   }
 * }
 */
export function useAsyncAction(): UseAsyncActionReturn {
  const [isExecuting, setIsExecuting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const execute = useCallback(
    async <T>(
      operation: () => Promise<T>,
      config?: AsyncActionConfig
    ): Promise<AsyncActionResult<T>> => {
      setIsExecuting(true);
      setError(null);

      try {
        const data = await operation();

        if (config?.successMessage && !config.skipSuccessMessage) {
          showMessage('success', config.successMessage);
        }

        config?.onSuccess?.(data);

        return { success: true, data };
      } catch (error) {
        const errorMessage =
          error instanceof Error
            ? error.message
            : (config?.errorMessage ?? DEFAULTS.ERROR.AN_ERROR_OCCURRED);

        setError(errorMessage);

        if (!config?.skipErrorMessage) {
          showMessage('error', config?.errorMessage ?? errorMessage);
        }

        config?.onError?.(error instanceof Error ? error : new Error(errorMessage));

        return { success: false, error: errorMessage };
      } finally {
        setIsExecuting(false);
      }
    },
    []
  );

  const resetError = useCallback(() => {
    setError(null);
  }, []);

  return { execute, isExecuting, error, resetError };
}
