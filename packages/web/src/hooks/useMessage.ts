import { useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { showMessage, type MessageType } from '@/utils/messages';

/**
 * Options for message interpolation
 */
export type MessageOptions = Record<string, string | number>;

/**
 * Return type for the useMessage hook
 */
export interface UseMessageReturn {
  /**
   * Display a success toast message
   * @param keyOrMessage - i18n translation key (with namespace, e.g., 'common:copiedToClipboard') or raw message string
   * @param options - Optional interpolation values for the translation
   */
  success: (keyOrMessage: string, options?: MessageOptions) => void;

  /**
   * Display an error toast message
   * @param keyOrMessage - i18n translation key (with namespace) or raw message string
   * @param options - Optional interpolation values for the translation
   */
  error: (keyOrMessage: string, options?: MessageOptions) => void;

  /**
   * Display a warning toast message
   * @param keyOrMessage - i18n translation key (with namespace) or raw message string
   * @param options - Optional interpolation values for the translation
   */
  warning: (keyOrMessage: string, options?: MessageOptions) => void;

  /**
   * Display an info toast message
   * @param keyOrMessage - i18n translation key (with namespace) or raw message string
   * @param options - Optional interpolation values for the translation
   */
  info: (keyOrMessage: string, options?: MessageOptions) => void;
}

/**
 * Hook for displaying toast notifications with i18n support.
 *
 * Wraps the centralized showMessage utility with:
 * - Automatic i18n translation when key contains namespace separator (':')
 * - Telemetry tracking
 * - Duplicate error prevention
 * - Notification center integration
 *
 * @example
 * ```tsx
 * const message = useMessage();
 *
 * // With i18n key (recommended)
 * message.success('common:copiedToClipboard');
 * message.error('common:operationFailed', { operation: 'save' });
 *
 * // With raw string (fallback for dynamic content)
 * message.error(error.message);
 * ```
 */
export const useMessage = (): UseMessageReturn => {
  const { t } = useTranslation();

  const show = useCallback(
    (type: MessageType, keyOrMessage: string, options?: MessageOptions) => {
      // Detect i18n key vs raw string
      // i18n keys contain ':' for namespace separation (e.g., 'common:success')
      const isI18nKey = keyOrMessage.includes(':');
      const content = isI18nKey ? t(keyOrMessage, options) : keyOrMessage;
      showMessage(type, content);
    },
    [t]
  );

  // Return memoized object to prevent unnecessary re-renders
  // when hook is used in dependency arrays
  return useMemo(
    () => ({
      success: (keyOrMessage: string, options?: MessageOptions) =>
        show('success', keyOrMessage, options),
      error: (keyOrMessage: string, options?: MessageOptions) =>
        show('error', keyOrMessage, options),
      warning: (keyOrMessage: string, options?: MessageOptions) =>
        show('warning', keyOrMessage, options),
      info: (keyOrMessage: string, options?: MessageOptions) =>
        show('info', keyOrMessage, options),
    }),
    [show]
  );
};
