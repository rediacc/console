import { createSlice, PayloadAction } from '@reduxjs/toolkit'

interface User {
  email: string
  company?: string
  role?: string
}

interface AuthState {
  isAuthenticated: boolean
  user: User | null
  company: string | null
  masterPassword: string | null // Stored in memory only, never persisted
  companyEncryptionEnabled: boolean
  vaultCompany: string | null // Stores the VaultCompany sentinel value
  // Token removed from Redux state for security - now managed by tokenService
}

const initialState: AuthState = {
  isAuthenticated: false,
  user: null,
  company: null,
  masterPassword: null,
  companyEncryptionEnabled: false,
  vaultCompany: null,
}

const authSlice = createSlice({
  name: 'auth',
  initialState,
  reducers: {
    loginSuccess: (state, action: PayloadAction<{ 
      user: User; 
      company?: string; 
      masterPassword?: string;
      vaultCompany?: string;
      companyEncryptionEnabled?: boolean;
    }>) => {
      state.isAuthenticated = true
      state.user = action.payload.user
      state.company = action.payload.company || null
      state.masterPassword = action.payload.masterPassword || null
      state.vaultCompany = action.payload.vaultCompany || null
      state.companyEncryptionEnabled = action.payload.companyEncryptionEnabled || false
      // Token is now handled separately by tokenService for security
    },
    logout: (state) => {
      state.isAuthenticated = false
      state.user = null
      state.company = null
      state.masterPassword = null
      state.companyEncryptionEnabled = false
      state.vaultCompany = null
      // Token cleanup is handled by tokenService
    },
    setMasterPassword: (state, action: PayloadAction<string | null>) => {
      state.masterPassword = action.payload
    },
    // updateToken action removed - token updates now handled by tokenService
    updateCompany: (state, action: PayloadAction<string>) => {
      state.company = action.payload
      if (state.user) {
        state.user.company = action.payload
      }
    },
    setVaultCompany: (state, action: PayloadAction<{ vaultCompany: string | null; companyEncryptionEnabled: boolean }>) => {
      state.vaultCompany = action.payload.vaultCompany
      state.companyEncryptionEnabled = action.payload.companyEncryptionEnabled
    },
  },
})

export const { loginSuccess, logout, setMasterPassword, updateCompany, setVaultCompany } = authSlice.actions
export default authSlice.reducer