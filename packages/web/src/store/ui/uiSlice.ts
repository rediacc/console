import { createSlice, PayloadAction } from '@reduxjs/toolkit';

interface UIState {
  sidebarCollapsed: boolean;
  activeView: string;
  selectedResource: string | null;
  filters: UIFilters;
  uiMode: 'simple' | 'expert';
  modals: {
    vaultConfig: {
      open: boolean;
      resourceType?: string;
      resourceId?: string;
    };
  };
}

const UI_MODE_KEY = 'uiMode';
const DEFAULT_UI_MODE = 'simple' as const;

const getStoredUiMode = (): 'simple' | 'expert' => {
  const stored = localStorage.getItem(UI_MODE_KEY);
  return stored === 'expert' ? 'expert' : DEFAULT_UI_MODE;
};

const persistUiMode = (mode: 'simple' | 'expert'): void => {
  localStorage.setItem(UI_MODE_KEY, mode);
};

type UIFilterValue = string | number | boolean | undefined;
type UIFilters = Record<string, UIFilterValue>;

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
};

const uiSlice = createSlice({
  name: 'ui',
  initialState,
  reducers: {
    toggleSidebar: (state) => {
      state.sidebarCollapsed = !state.sidebarCollapsed;
    },
    setActiveView: (state, action: PayloadAction<string>) => {
      state.activeView = action.payload;
    },
    setSelectedResource: (state, action: PayloadAction<string | null>) => {
      state.selectedResource = action.payload;
    },
    setFilters: (state, action: PayloadAction<UIFilters>) => {
      state.filters = action.payload;
    },
    openVaultModal: (
      state,
      action: PayloadAction<{ resourceType: string; resourceId: string }>
    ) => {
      state.modals.vaultConfig = {
        open: true,
        resourceType: action.payload.resourceType,
        resourceId: action.payload.resourceId,
      };
    },
    closeVaultModal: (state) => {
      state.modals.vaultConfig = {
        open: false,
      };
    },
    setUiMode: (state, action: PayloadAction<'simple' | 'expert'>) => {
      state.uiMode = action.payload;
      persistUiMode(action.payload);
    },
    toggleUiMode: (state) => {
      const newMode = state.uiMode === 'simple' ? 'expert' : 'simple';
      state.uiMode = newMode;
      persistUiMode(newMode);
    },
  },
});

export const {
  toggleSidebar,
  setActiveView,
  setSelectedResource,
  setFilters,
  openVaultModal,
  closeVaultModal,
  setUiMode,
  toggleUiMode,
} = uiSlice.actions;

export default uiSlice.reducer;
