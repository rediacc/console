import { createSlice, PayloadAction } from '@reduxjs/toolkit';

interface User {
  email: string;
  organization?: string;
  role?: string;
  preferredLanguage?: string;
}

interface AuthState {
  isAuthenticated: boolean;
  user: User | null;
  organization: string | null;
  // masterPassword removed from Redux state for security - now managed by masterPasswordService
  organizationEncryptionEnabled: boolean;
  vaultOrganization: string | null; // Stores the VaultOrganization sentinel value
  // Token removed from Redux state for security - now managed by tokenService
  showSessionExpiredModal: boolean;
  stayLoggedOutMode: boolean; // User chose to stay on page after session expired
}

const initialState: AuthState = {
  isAuthenticated: false,
  user: null,
  organization: null,
  organizationEncryptionEnabled: false,
  vaultOrganization: null,
  showSessionExpiredModal: false,
  stayLoggedOutMode: false,
};

const authSlice = createSlice({
  name: 'auth',
  initialState,
  reducers: {
    loginSuccess: (
      state,
      action: PayloadAction<{
        user: User;
        organization?: string;
        vaultOrganization?: string;
        organizationEncryptionEnabled?: boolean;
      }>
    ) => {
      state.isAuthenticated = true;
      state.user = action.payload.user;
      state.organization = action.payload.organization ?? null;
      state.vaultOrganization = action.payload.vaultOrganization ?? null;
      state.organizationEncryptionEnabled = action.payload.organizationEncryptionEnabled ?? false;
      // Token is now handled separately by tokenService for security
      // masterPassword is now handled separately by masterPasswordService for security
    },
    logout: (state) => {
      state.isAuthenticated = false;
      state.user = null;
      state.organization = null;
      state.organizationEncryptionEnabled = false;
      state.vaultOrganization = null;
      state.showSessionExpiredModal = false;
      state.stayLoggedOutMode = false;
      // Token cleanup is handled by tokenService
      // masterPassword cleanup is handled by masterPasswordService
    },
    // setMasterPassword action removed - masterPassword updates now handled by masterPasswordService
    // updateToken action removed - token updates now handled by tokenService
    updateOrganization: (state, action: PayloadAction<string>) => {
      state.organization = action.payload;
      if (state.user) {
        state.user.organization = action.payload;
      }
    },
    setVaultOrganization: (
      state,
      action: PayloadAction<{
        vaultOrganization: string | null;
        organizationEncryptionEnabled: boolean;
      }>
    ) => {
      state.vaultOrganization = action.payload.vaultOrganization;
      state.organizationEncryptionEnabled = action.payload.organizationEncryptionEnabled;
    },
    showSessionExpiredModal: (state) => {
      state.showSessionExpiredModal = true;
    },
    hideSessionExpiredModal: (state) => {
      state.showSessionExpiredModal = false;
    },
    setStayLoggedOutMode: (state, action: PayloadAction<boolean>) => {
      state.stayLoggedOutMode = action.payload;
    },
  },
});

export const {
  loginSuccess,
  logout,
  updateOrganization,
  showSessionExpiredModal,
  hideSessionExpiredModal,
  setStayLoggedOutMode,
} = authSlice.actions;
export default authSlice.reducer;
