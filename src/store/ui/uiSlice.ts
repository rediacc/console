import { createSlice, PayloadAction } from '@reduxjs/toolkit'

export interface Message {
  id: string
  type: 'success' | 'error' | 'warning' | 'info'
  content: string
  timestamp: number
  read: boolean
}

interface UIState {
  sidebarCollapsed: boolean
  activeView: string
  selectedResource: string | null
  filters: Record<string, any>
  messages: Message[]
  unreadMessageCount: number
  uiMode: 'simple' | 'expert'
  modals: {
    vaultConfig: {
      open: boolean
      resourceType?: string
      resourceId?: string
    }
  }
}

const getStoredUiMode = (): 'simple' | 'expert' => {
  const stored = localStorage.getItem('uiMode')
  return stored === 'expert' ? 'expert' : 'simple'
}

const initialState: UIState = {
  sidebarCollapsed: false,
  activeView: 'organization',
  selectedResource: null,
  filters: {},
  messages: [],
  unreadMessageCount: 0,
  uiMode: getStoredUiMode(),
  modals: {
    vaultConfig: {
      open: false,
    },
  },
}

const uiSlice = createSlice({
  name: 'ui',
  initialState,
  reducers: {
    toggleSidebar: (state) => {
      state.sidebarCollapsed = !state.sidebarCollapsed
    },
    setActiveView: (state, action: PayloadAction<string>) => {
      state.activeView = action.payload
    },
    setSelectedResource: (state, action: PayloadAction<string | null>) => {
      state.selectedResource = action.payload
    },
    setFilters: (state, action: PayloadAction<Record<string, any>>) => {
      state.filters = action.payload
    },
    openVaultModal: (state, action: PayloadAction<{ resourceType: string; resourceId: string }>) => {
      state.modals.vaultConfig = {
        open: true,
        resourceType: action.payload.resourceType,
        resourceId: action.payload.resourceId,
      }
    },
    closeVaultModal: (state) => {
      state.modals.vaultConfig = {
        open: false,
      }
    },
    addMessage: (state, action: PayloadAction<Omit<Message, 'id' | 'timestamp' | 'read'>>) => {
      const message: Message = {
        ...action.payload,
        id: Date.now().toString(),
        timestamp: Date.now(),
        read: false,
      }
      state.messages.unshift(message)
      state.unreadMessageCount += 1
      // Keep only last 50 messages
      if (state.messages.length > 50) {
        state.messages = state.messages.slice(0, 50)
      }
    },
    markMessageAsRead: (state, action: PayloadAction<string>) => {
      const message = state.messages.find(m => m.id === action.payload)
      if (message && !message.read) {
        message.read = true
        state.unreadMessageCount = Math.max(0, state.unreadMessageCount - 1)
      }
    },
    markAllMessagesAsRead: (state) => {
      state.messages.forEach(message => {
        message.read = true
      })
      state.unreadMessageCount = 0
    },
    clearMessages: (state) => {
      state.messages = []
      state.unreadMessageCount = 0
    },
    setUiMode: (state, action: PayloadAction<'simple' | 'expert'>) => {
      state.uiMode = action.payload
      localStorage.setItem('uiMode', action.payload)
    },
    toggleUiMode: (state) => {
      const newMode = state.uiMode === 'simple' ? 'expert' : 'simple'
      state.uiMode = newMode
      localStorage.setItem('uiMode', newMode)
    },
  },
})

export const {
  toggleSidebar,
  setActiveView,
  setSelectedResource,
  setFilters,
  openVaultModal,
  closeVaultModal,
  addMessage,
  markMessageAsRead,
  markAllMessagesAsRead,
  clearMessages,
  setUiMode,
  toggleUiMode,
} = uiSlice.actions

export default uiSlice.reducer