import { createSlice, PayloadAction } from '@reduxjs/toolkit'

interface UIState {
  sidebarCollapsed: boolean
  activeView: string
  selectedResource: string | null
  filters: Record<string, any>
  modals: {
    vaultConfig: {
      open: boolean
      resourceType?: string
      resourceId?: string
    }
  }
}

const initialState: UIState = {
  sidebarCollapsed: false,
  activeView: 'dashboard',
  selectedResource: null,
  filters: {},
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
  },
})

export const {
  toggleSidebar,
  setActiveView,
  setSelectedResource,
  setFilters,
  openVaultModal,
  closeVaultModal,
} = uiSlice.actions

export default uiSlice.reducer