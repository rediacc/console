import { RootState } from '../store'

export const selectIsAuthenticated = (state: RootState) => state.auth.isAuthenticated
export const selectUser = (state: RootState) => state.auth.user
export const selectCompany = (state: RootState) => state.auth.company
export const selectMasterPassword = (state: RootState) => state.auth.masterPassword
// selectToken removed for security - tokens are now managed by tokenService