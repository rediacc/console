import { useCallback, useState } from 'react';
import { showMessage } from '@/utils/messages';

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
          error instanceof Error ? error.message : config?.errorMessage || 'An error occurred';

        setError(errorMessage);

        if (!config?.skipErrorMessage) {
          showMessage('error', config?.errorMessage || errorMessage);
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

/**
 * Extended async action with multiple operations support
 */
export interface MultiStepActionConfig<T> {
  /** Steps to execute in sequence */
  steps: Array<{
    /** Step operation */
    operation: () => Promise<unknown>;
    /** Step name for error context */
    name: string;
    /** Whether to continue on failure */
    continueOnError?: boolean;
  }>;
  /** Success message for all steps completing */
  successMessage?: string;
  /** Transform the results of all steps */
  transformResults?: (results: unknown[]) => T;
}

/**
 * Execute multiple async operations in sequence with error handling
 *
 * @example
 * const result = await executeMultiStep({
 *   steps: [
 *     { operation: () => step1(), name: 'Create resource' },
 *     { operation: () => step2(), name: 'Queue action', continueOnError: true }
 *   ],
 *   successMessage: 'All steps completed'
 * })
 */
export async function executeMultiStep<T = unknown>(
  config: MultiStepActionConfig<T>
): Promise<AsyncActionResult<T>> {
  const results: unknown[] = [];

  for (const step of config.steps) {
    try {
      const result = await step.operation();
      results.push(result);
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';

      if (!step.continueOnError) {
        showMessage('error', `${step.name} failed: ${errorMessage}`);
        return { success: false, error: `${step.name}: ${errorMessage}` };
      }

      // Continue but track the error
      results.push({ error: errorMessage });
    }
  }

  if (config.successMessage) {
    showMessage('success', config.successMessage);
  }

  const data = config.transformResults ? config.transformResults(results) : (results as T);
  return { success: true, data };
}

/**
 * Hook for form submission with standardized error handling
 *
 * @example
 * const { submit, isSubmitting } = useFormSubmission({
 *   onSubmit: async (data) => {
 *     await mutation.mutateAsync(data)
 *   },
 *   successMessage: 'Form submitted successfully',
 *   onSuccess: () => {
 *     closeModal()
 *     refetch()
 *   }
 * })
 *
 * <form onSubmit={form.handleSubmit(submit)}>
 *   ...
 *   <Button loading={isSubmitting}>Submit</Button>
 * </form>
 */
export interface UseFormSubmissionConfig<T> {
  /** Submit handler */
  onSubmit: (data: T) => Promise<void>;
  /** Success message */
  successMessage?: string;
  /** Error message prefix */
  errorMessage?: string;
  /** Callback on success */
  onSuccess?: () => void;
  /** Callback on error */
  onError?: (error: Error) => void;
}

export interface UseFormSubmissionReturn<T> {
  /** Submit handler to pass to form */
  submit: (data: T) => Promise<void>;
  /** Whether form is submitting */
  isSubmitting: boolean;
}

export function useFormSubmission<T>(
  config: UseFormSubmissionConfig<T>
): UseFormSubmissionReturn<T> {
  const { execute, isExecuting } = useAsyncAction();

  const submit = useCallback(
    async (data: T) => {
      const result = await execute(() => config.onSubmit(data), {
        successMessage: config.successMessage,
        errorMessage: config.errorMessage,
        onError: config.onError,
      });

      if (result.success) {
        config.onSuccess?.();
      }
    },
    [execute, config]
  );

  return {
    submit,
    isSubmitting: isExecuting,
  };
}
