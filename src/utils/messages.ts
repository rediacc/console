import toast from 'react-hot-toast'
import { store } from '@/store/store'
import { addNotification } from '@/store/notifications/notificationSlice'
import i18n from '@/i18n/config'

export type MessageType = 'success' | 'error' | 'warning' | 'info'

// Track recent error messages to prevent duplicates
const recentErrors = new Map<string, number>()
const ERROR_DEDUP_WINDOW_MS = 1000 // 1 second window for deduplication
const ERROR_CLEANUP_THRESHOLD_MS = ERROR_DEDUP_WINDOW_MS * 2

const NOTIFICATION_TITLES: Record<MessageType, string> = {
  success: 'Success',
  error: 'Error',
  warning: 'Warning',
  info: 'Information'
}

const getNotificationTitle = (type: MessageType): string => 
  NOTIFICATION_TITLES[type] ?? 'Notification'

export const showMessage = (type: MessageType, content: string) => {
  // For error messages, check if we've shown this recently
  if (type === 'error' && isDuplicateError(content)) {
    return
  }
  
  displayToast(type, content)
  addToNotificationCenter(type, content)
}

function isDuplicateError(content: string): boolean {
  const now = Date.now()
  const lastShown = recentErrors.get(content)
  
  if (lastShown && now - lastShown < ERROR_DEDUP_WINDOW_MS) {
    return true
  }
  
  recentErrors.set(content, now)
  cleanupOldErrors(now)
  
  return false
}

function cleanupOldErrors(currentTime: number): void {
  for (const [message, time] of recentErrors.entries()) {
    if (currentTime - time > ERROR_CLEANUP_THRESHOLD_MS) {
      recentErrors.delete(message)
    }
  }
}

function displayToast(type: MessageType, content: string): void {
  const toastConfig = getToastConfig(type)
  
  if (toastConfig.isCustom) {
    toast(content, toastConfig.options)
  } else if (toastConfig.handler) {
    toastConfig.handler(content)
  }
}

interface ToastConfig {
  handler?: (message: string) => void
  isCustom: boolean
  options?: any
}

const TOAST_STYLES = {
  warning: {
    icon: '⚠️',
    style: {
      background: '#FFF3CD',
      color: '#856404',
      border: '1px solid #FFEAA7',
    },
  },
  info: {
    icon: 'ℹ️',
    style: {
      background: '#D1ECF1',
      color: '#0C5460',
      border: '1px solid #BEE5EB',
    },
  },
}

const TOAST_CONFIGS: Record<MessageType, ToastConfig> = {
  success: { handler: toast.success, isCustom: false },
  error: { handler: toast.error, isCustom: false },
  warning: { isCustom: true, options: TOAST_STYLES.warning },
  info: { isCustom: true, options: TOAST_STYLES.info }
}

const getToastConfig = (type: MessageType): ToastConfig => 
  TOAST_CONFIGS[type] ?? { handler: toast, isCustom: false }

function addToNotificationCenter(type: MessageType, content: string): void {
  store.dispatch(addNotification({
    type,
    title: getNotificationTitle(type),
    message: content
  }))
}

// Export a function that supports i18n translations
export const showTranslatedMessage = (
  type: MessageType, 
  i18nKey: string, 
  options?: Record<string, string | number>
) => {
  const content = i18n.t(i18nKey, options)
  showMessage(type, content)
}