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
  // masterPassword removed from Redux state for security - now managed by masterPasswordService
  companyEncryptionEnabled: boolean
  vaultCompany: string | null // Stores the VaultCompany sentinel value
  // Token removed from Redux state for security - now managed by tokenService
}

const initialState: AuthState = {
  isAuthenticated: false,
  user: null,
  company: null,
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
      vaultCompany?: string;
      companyEncryptionEnabled?: boolean;
    }>) => {
      state.isAuthenticated = true
      state.user = action.payload.user
      state.company = action.payload.company || null
      state.vaultCompany = action.payload.vaultCompany || null
      state.companyEncryptionEnabled = action.payload.companyEncryptionEnabled || false
      // Token is now handled separately by tokenService for security
      // masterPassword is now handled separately by masterPasswordService for security
    },
    logout: (state) => {
      state.isAuthenticated = false
      state.user = null
      state.company = null
      state.companyEncryptionEnabled = false
      state.vaultCompany = null
      // Token cleanup is handled by tokenService
      // masterPassword cleanup is handled by masterPasswordService
    },
    // setMasterPassword action removed - masterPassword updates now handled by masterPasswordService
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

export const { loginSuccess, logout, updateCompany, setVaultCompany } = authSlice.actions
export default authSlice.reducer