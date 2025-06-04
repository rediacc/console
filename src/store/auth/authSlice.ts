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
}

const initialState: AuthState = {
  isAuthenticated: false,
  user: null,
  token: null,
  company: null,
}

const authSlice = createSlice({
  name: 'auth',
  initialState,
  reducers: {
    loginSuccess: (state, action: PayloadAction<{ user: User; token: string; company?: string }>) => {
      state.isAuthenticated = true
      state.user = action.payload.user
      state.token = action.payload.token
      state.company = action.payload.company || null
    },
    logout: (state) => {
      state.isAuthenticated = false
      state.user = null
      state.token = null
      state.company = null
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
  },
})

export const { loginSuccess, logout, updateToken, updateCompany } = authSlice.actions
export default authSlice.reducer