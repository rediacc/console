import { createSlice, PayloadAction } from '@reduxjs/toolkit'

interface User {
  email: string
  company?: string
  role?: string
}

interface AuthState {
  isAuthenticated: boolean
  user: User | null
  token: string | null
  company: string | null
  masterPassword: string | null // Stored in memory only, never persisted
  companyEncryptionEnabled: boolean
  vaultCompany: string | null // Stores the VaultCompany sentinel value
}

const initialState: AuthState = {
  isAuthenticated: false,
  user: null,
  token: null,
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
      token: string; 
      company?: string; 
      masterPassword?: string;
      vaultCompany?: string;
      companyEncryptionEnabled?: boolean;
    }>) => {
      state.isAuthenticated = true
      state.user = action.payload.user
      state.token = action.payload.token
      state.company = action.payload.company || null
      state.masterPassword = action.payload.masterPassword || null
      state.vaultCompany = action.payload.vaultCompany || null
      state.companyEncryptionEnabled = action.payload.companyEncryptionEnabled || false
    },
    logout: (state) => {
      state.isAuthenticated = false
      state.user = null
      state.token = null
      state.company = null
      state.masterPassword = null
      state.companyEncryptionEnabled = false
      state.vaultCompany = null
    },
    setMasterPassword: (state, action: PayloadAction<string | null>) => {
      state.masterPassword = action.payload
    },
    updateToken: (state, action: PayloadAction<string>) => {
      state.token = action.payload
    },
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

export const { loginSuccess, logout, setMasterPassword, updateToken, updateCompany, setVaultCompany } = authSlice.actions
export default authSlice.reducer