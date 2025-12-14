import { useState, useCallback } from 'react';
import { useMessage } from './useMessage';

export interface UseCopyToClipboardOptions {
  /** Success message i18n key (default: 'common:copiedToClipboard') */
  successMessage?: string;
  /** Error message i18n key (default: 'common:copyFailed') */
  errorMessage?: string;
  /** Duration in ms to show copied state (default: 2000) */
  feedbackDuration?: number;
}

export interface UseCopyToClipboardReturn {
  /** Function to copy text to clipboard */
  copy: (text: string) => Promise<boolean>;
  /** Whether the text was recently copied (for visual feedback) */
  copied: boolean;
}

/**
 * Hook for copying text to clipboard with visual feedback.
 *
 * Provides consistent copy-to-clipboard behavior with:
 * - Automatic success/error toast notifications
 * - Temporary "copied" state for button feedback
 * - Configurable feedback duration
 *
 * @example
 * ```tsx
 * const { copy, copied } = useCopyToClipboard();
 *
 * <Button
 *   icon={copied ? <CheckOutlined /> : <CopyOutlined />}
 *   onClick={() => copy(textToCopy)}
 * >
 *   {copied ? 'Copied!' : 'Copy'}
 * </Button>
 * ```
 */
export function useCopyToClipboard(
  options: UseCopyToClipboardOptions = {}
): UseCopyToClipboardReturn {
  const {
    successMessage = 'common:copiedToClipboard',
    errorMessage = 'common:copyFailed',
    feedbackDuration = 2000,
  } = options;

  const [copied, setCopied] = useState(false);
  const message = useMessage();

  const copy = useCallback(
    async (text: string): Promise<boolean> => {
      try {
        await navigator.clipboard.writeText(text);
        setCopied(true);
        message.success(successMessage);
        setTimeout(() => setCopied(false), feedbackDuration);
        return true;
      } catch {
        message.error(errorMessage);
        return false;
      }
    },
    [message, successMessage, errorMessage, feedbackDuration]
  );

  return { copy, copied };
}
