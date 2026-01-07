import type { ErrorHandler } from '@rediacc/shared/api';

/**
 * CLI error handler.
 * In CLI, error handling is mainly done by throwing errors.
 * The command wrapper handles exit codes.
 */
export const errorHandler: ErrorHandler = {
  onUnauthorized: () => {
    // In CLI, we let the error propagate up and be handled by the command
    // The CliApiError will contain the appropriate exit code
  },

  onServerError: (_message: string) => {
    // In CLI, we let the error propagate up
  },

  onNetworkError: (_message: string) => {
    // In CLI, we let the error propagate up
  },
};
