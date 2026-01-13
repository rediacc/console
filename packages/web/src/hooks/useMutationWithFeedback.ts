import { useMutation, UseMutationOptions, UseMutationResult } from '@tanstack/react-query';
import i18n from '@/i18n/config';
import { showMessage } from '@/utils/messages';
import { extractErrorMessage } from '@/utils/mutationUtils';
import { applyProcedureDefaults } from '@rediacc/shared/api/typedApi/defaults';
import type { StoredProcedureName } from '@rediacc/shared/types';

function buildInterpolationValues(
  data: unknown,
  variables: unknown,
  procedureName?: StoredProcedureName
): Record<string, unknown> {
  const dataObj = data && typeof data === 'object' ? (data as Record<string, unknown>) : {};
  const varsObj =
    variables && typeof variables === 'object' ? (variables as Record<string, unknown>) : {};
  const normalizedVars = procedureName ? applyProcedureDefaults(procedureName, varsObj) : varsObj;
  return { ...normalizedVars, ...dataObj };
}

function translateMessage(
  message: string,
  data: unknown,
  variables: unknown,
  procedureName?: StoredProcedureName
): string {
  return i18n.t(message, {
    ...buildInterpolationValues(data, variables, procedureName),
    defaultValue: message,
  });
}

export interface MutationFeedbackOptions<TData, TError, TVariables> {
  /**
   * Stored procedure name for centralized defaults/interpolation.
   */
  procedureName?: StoredProcedureName;
  /**
   * Success message - static string OR response-based callback.
   * If provided, shows a success toast when mutation succeeds.
   */
  successMessage?: string | ((data: TData, variables: TVariables) => string | null);
  /**
   * Error message - static string OR error-based callback.
   * Defaults to extracting the error message from the error object.
   */
  errorMessage?: string | ((error: TError, variables: TVariables) => string);
  /**
   * Disable all automatic feedback (success and error toasts).
   */
  disableFeedback?: boolean;
}

/**
 * A wrapper around useMutation that provides automatic success/error toast feedback.
 *
 * Features:
 * - Automatic success/error toasts via showMessage
 * - Response-based message generation (successMessage can be a function)
 * - Conditional feedback (return null from successMessage to skip toast)
 * - User's onSuccess/onError callbacks are preserved and called after feedback
 *
 * @example
 * // Static message
 * useMutationWithFeedback({
 *   mutationFn: api.users.create,
 *   successMessage: 'User created successfully',
 *   errorMessage: 'Failed to create user',
 * });
 *
 * @example
 * // Response-based message
 * useMutationWithFeedback({
 *   mutationFn: api.users.create,
 *   successMessage: (data) => `User ${data.email} created`,
 *   errorMessage: 'Failed to create user',
 * });
 *
 * @example
 * // Conditional success message (return null to skip)
 * useMutationWithFeedback({
 *   mutationFn: api.tfa.enable,
 *   successMessage: (data, variables) =>
 *     variables.confirmEnable ? 'TFA enabled' : null,
 * });
 */
export function useMutationWithFeedback<
  TData = unknown,
  TError = Error,
  TVariables = void,
  TContext = unknown,
>(
  options: UseMutationOptions<TData, TError, TVariables, TContext> &
    MutationFeedbackOptions<TData, TError, TVariables>
): UseMutationResult<TData, TError, TVariables, TContext> {
  const {
    successMessage,
    errorMessage,
    disableFeedback,
    procedureName,
    onSuccess: userOnSuccess,
    onError: userOnError,
    ...mutationOptions
  } = options;

  return useMutation({
    ...mutationOptions,
    onSuccess: (data, variables, onMutateResult, mutationContext) => {
      // Show success feedback
      if (!disableFeedback && successMessage) {
        const message =
          typeof successMessage === 'function'
            ? successMessage(data, variables)
            : translateMessage(successMessage, data, variables, procedureName);
        // Allow null to skip the message (for conditional feedback)
        if (message) {
          showMessage('success', message);
        }
      }
      // Call user's callback
      userOnSuccess?.(data, variables, onMutateResult, mutationContext);
    },
    onError: (error, variables, onMutateResult, mutationContext) => {
      // Show error feedback
      if (!disableFeedback) {
        const message =
          typeof errorMessage === 'function'
            ? errorMessage(error, variables)
            : translateMessage(
                extractErrorMessage(error, errorMessage ?? i18n.t('shared:errors.operationFailed')),
                error,
                variables,
                procedureName
              );
        showMessage('error', message);
      }
      // Call user's callback
      userOnError?.(error, variables, onMutateResult, mutationContext);
    },
  });
}
