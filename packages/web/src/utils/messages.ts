import toast from 'react-hot-toast';
import i18n from '@/i18n/config';
import { telemetryService } from '@/services/telemetryService';
import { addNotification } from '@/store/notifications/notificationSlice';
import { store } from '@/store/store';

export type MessageType = 'success' | 'error' | 'warning' | 'info';

// Track recent error messages to prevent duplicates
const recentErrors = new Map<string, number>();
const ERROR_DEDUP_WINDOW_MS = 1000; // 1 second window for deduplication
const ERROR_CLEANUP_THRESHOLD_MS = ERROR_DEDUP_WINDOW_MS * 2;

const getNotificationTitle = (type: MessageType): string => {
  const titleKey = `notifications.types.${type}`;
  return i18n.t(`common:${titleKey}`) || 'Notification';
};

export const showMessage = (type: MessageType, content: string) => {
  // For error messages, check if we've shown this recently
  const isDuplicate = type === 'error' && isDuplicateError(content);

  // Track message display (including duplicates for analytics)
  telemetryService.trackEvent('ux.message_displayed', {
    'message.type': type,
    'message.content_length': content.length,
    'message.is_duplicate': isDuplicate,
    'message.content_hash': hashMessageContent(content),
    'page.url': window.location.pathname,
    'ux.error_frequency': type === 'error' ? getErrorFrequency() : 0,
  });

  if (isDuplicate) {
    // Track duplicate prevention
    telemetryService.trackEvent('ux.duplicate_message_prevented', {
      'message.type': type,
      'message.content_hash': hashMessageContent(content),
    });
    return;
  }

  displayToast(type, content);
  addToNotificationCenter(type, content);

  // Track UX quality metrics
  if (type === 'success') {
    telemetryService.trackEvent('ux.positive_feedback', {
      'feedback.type': 'success_message',
      'page.url': window.location.pathname,
    });
  } else if (type === 'error') {
    telemetryService.trackEvent('ux.negative_feedback', {
      'feedback.type': 'error_message',
      'error.content': content.substring(0, 100), // Limit for privacy
      'page.url': window.location.pathname,
    });
  }
};

function isDuplicateError(content: string): boolean {
  const now = Date.now();
  const lastShown = recentErrors.get(content);

  if (lastShown && now - lastShown < ERROR_DEDUP_WINDOW_MS) {
    return true;
  }

  recentErrors.set(content, now);
  cleanupOldErrors(now);

  return false;
}

function cleanupOldErrors(currentTime: number): void {
  for (const [message, time] of recentErrors.entries()) {
    if (currentTime - time > ERROR_CLEANUP_THRESHOLD_MS) {
      recentErrors.delete(message);
    }
  }
}

function displayToast(type: MessageType, content: string): void {
  const toastConfig = getToastConfig(type);

  if (toastConfig.isCustom) {
    toast(content, toastConfig.options);
  } else if (toastConfig.handler) {
    toastConfig.handler(content);
  }
}

interface ToastConfig {
  handler?: (message: string) => void;
  isCustom: boolean;
  options?: Record<string, unknown>;
}

const TOAST_STYLES = {
  warning: {
    icon: '⚠️',
  },
  info: {
    icon: 'ℹ️',
  },
};

const TOAST_CONFIGS: Record<MessageType, ToastConfig> = {
  success: { handler: toast.success, isCustom: false },
  error: { handler: toast.error, isCustom: false },
  warning: { isCustom: true, options: TOAST_STYLES.warning },
  info: { isCustom: true, options: TOAST_STYLES.info },
};

const getToastConfig = (type: MessageType): ToastConfig => TOAST_CONFIGS[type];

function addToNotificationCenter(type: MessageType, content: string): void {
  store.dispatch(
    addNotification({
      type,
      title: getNotificationTitle(type),
      message: content,
    })
  );
}

// Export a function that supports i18n translations
export const showTranslatedMessage = (
  type: MessageType,
  i18nKey: string,
  options?: Record<string, string | number>
) => {
  const content = i18n.t(i18nKey, options);
  showMessage(type, content);
};

// Helper functions for telemetry
function hashMessageContent(content: string): string {
  // Simple hash for content tracking (privacy-safe)
  let hash = 0;
  for (let i = 0; i < content.length; i++) {
    const char = content.charCodeAt(i);
    hash = (hash << 5) - hash + char;
    hash = hash & hash; // Convert to 32bit integer
  }
  return Math.abs(hash).toString(36);
}

function getErrorFrequency(): number {
  // Calculate error frequency in the last minute
  const now = Date.now();
  const oneMinuteAgo = now - 60000;
  let count = 0;

  for (const [, timestamp] of recentErrors.entries()) {
    if (timestamp > oneMinuteAgo) {
      count++;
    }
  }

  return count;
}
