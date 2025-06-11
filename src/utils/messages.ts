import toast from 'react-hot-toast'
import { store } from '@/store/store'
import { addNotification } from '@/store/notifications/notificationSlice'

export type MessageType = 'success' | 'error' | 'warning' | 'info'

// Track recent error messages to prevent duplicates
const recentErrors = new Map<string, number>()
const ERROR_DEDUP_WINDOW = 1000 // 1 second window for deduplication

const getNotificationTitle = (type: MessageType): string => {
  switch (type) {
    case 'success':
      return 'Success'
    case 'error':
      return 'Error'
    case 'warning':
      return 'Warning'
    case 'info':
      return 'Information'
    default:
      return 'Notification'
  }
}

export const showMessage = (type: MessageType, content: string) => {
  // For error messages, check if we've shown this recently
  if (type === 'error') {
    const now = Date.now()
    const lastShown = recentErrors.get(content)
    
    if (lastShown && now - lastShown < ERROR_DEDUP_WINDOW) {
      // Skip showing duplicate error
      return
    }
    
    recentErrors.set(content, now)
    
    // Clean up old entries
    for (const [msg, time] of recentErrors.entries()) {
      if (now - time > ERROR_DEDUP_WINDOW * 2) {
        recentErrors.delete(msg)
      }
    }
  }
  
  // Show toast based on type
  // react-hot-toast only has success, error, and the base toast function
  switch (type) {
    case 'success':
      toast.success(content)
      break
    case 'error':
      toast.error(content)
      break
    case 'warning':
      // Use custom toast for warning
      toast(content, {
        icon: '⚠️',
        style: {
          background: '#FFF3CD',
          color: '#856404',
          border: '1px solid #FFEAA7',
        },
      })
      break
    case 'info':
      // Use custom toast for info
      toast(content, {
        icon: 'ℹ️',
        style: {
          background: '#D1ECF1',
          color: '#0C5460',
          border: '1px solid #BEE5EB',
        },
      })
      break
    default:
      toast(content)
  }
  
  // Add to notification center
  store.dispatch(addNotification({
    type,
    title: getNotificationTitle(type),
    message: content
  }))
}