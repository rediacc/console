import i18n from '@/i18n/config';
import { logout, showSessionExpiredModal } from '@/store/auth/authSlice';
import { store } from '@/store/store';
import { showMessage } from '@/utils/messages';
import type { ErrorHandler } from '@rediacc/shared/api';

/**
 * Web error handler with Redux integration and UI messages.
 */
export const errorHandler: ErrorHandler = {
  onUnauthorized: () => {
    const currentPath = window.location.pathname;
    const isAlreadyOnLogin = currentPath.includes('/login');

    // Only show dialog if not already on login page and dialog not already shown
    if (!isAlreadyOnLogin) {
      const state = store.getState();
      if (!state.auth.showSessionExpiredModal) {
        showMessage('error', 'Session expired. Please login again.');
        store.dispatch(logout());
        store.dispatch(showSessionExpiredModal());
      }
    }
  },

  onServerError: (message: string) => {
    showMessage('error', message);
  },

  onNetworkError: (message: string) => {
    showMessage('error', message);
  },

  onValidationError: (error) => {
    const message = i18n.t('common:errors.schemaValidationFailed');
    showMessage('error', message);
    // Log details for debugging (visible in browser console)
    console.error('[API Validation Error]', error.procedure, error.zodError.issues);
  },
};
