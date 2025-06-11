import { createSlice, PayloadAction } from '@reduxjs/toolkit'

interface UIState {
  sidebarCollapsed: boolean
  activeView: string
  selectedResource: string | null
  filters: Record<string, any>
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
  activeView: 'resources',
  selectedResource: null,
  filters: {},
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
  setUiMode,
  toggleUiMode,
} = uiSlice.actions

export default uiSlice.reducer