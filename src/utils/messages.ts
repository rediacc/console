import toast from 'react-hot-toast'
import { store } from '@/store/store'
import { addMessage } from '@/store/ui/uiSlice'

export type MessageType = 'success' | 'error' | 'warning' | 'info'

export const showMessage = (type: MessageType, content: string) => {
  // Show toast
  toast[type](content)
  
  // Add to message history
  store.dispatch(addMessage({ type, content }))
}