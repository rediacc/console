import { createSlice, PayloadAction } from '@reduxjs/toolkit'

export type NotificationType = 'success' | 'error' | 'warning' | 'info'

export interface Notification {
  id: string
  type: NotificationType
  title: string
  message: string
  timestamp: number
  read: boolean
}

interface NotificationState {
  notifications: Notification[]
  unreadCount: number
}

const initialState: NotificationState = {
  notifications: [],
  unreadCount: 0
}

const notificationSlice = createSlice({
  name: 'notifications',
  initialState,
  reducers: {
    addNotification: (state, action: PayloadAction<Omit<Notification, 'id' | 'timestamp' | 'read'>>) => {
      const notification: Notification = {
        ...action.payload,
        id: `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
        timestamp: Date.now(),
        read: false
      }
      
      // Add to beginning of array (newest first)
      state.notifications.unshift(notification)
      state.unreadCount++
      
      // Keep only last 50 notifications
      if (state.notifications.length > 50) {
        state.notifications = state.notifications.slice(0, 50)
      }
    },
    
    markAsRead: (state, action: PayloadAction<string>) => {
      const notification = state.notifications.find(n => n.id === action.payload)
      if (notification && !notification.read) {
        notification.read = true
        state.unreadCount = Math.max(0, state.unreadCount - 1)
      }
    },
    
    markAllAsRead: (state) => {
      state.notifications.forEach(n => {
        n.read = true
      })
      state.unreadCount = 0
    },
    
    clearNotification: (state, action: PayloadAction<string>) => {
      const index = state.notifications.findIndex(n => n.id === action.payload)
      if (index !== -1) {
        const notification = state.notifications[index]
        if (!notification.read) {
          state.unreadCount = Math.max(0, state.unreadCount - 1)
        }
        state.notifications.splice(index, 1)
      }
    },
    
    clearAllNotifications: (state) => {
      state.notifications = []
      state.unreadCount = 0
    }
  }
})

export const { 
  addNotification, 
  markAsRead, 
  markAllAsRead, 
  clearNotification, 
  clearAllNotifications 
} = notificationSlice.actions

export default notificationSlice.reducer