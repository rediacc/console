import toast from 'react-hot-toast'
import { store } from '@/store/store'
import { addMessage } from '@/store/ui/uiSlice'

export type MessageType = 'success' | 'error' | 'warning' | 'info'

// Track recent error messages to prevent duplicates
const recentErrors = new Map<string, number>()
const ERROR_DEDUP_WINDOW = 1000 // 1 second window for deduplication

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
  
  // Show toast
  toast[type](content)
  
  // Add to message history
  store.dispatch(addMessage({ type, content }))
}