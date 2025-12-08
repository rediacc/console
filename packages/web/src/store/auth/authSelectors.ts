import { RootState } from '@/store/store';

export const selectIsAuthenticated = (state: RootState) => state.auth.isAuthenticated;
export const selectUser = (state: RootState) => state.auth.user;
export const selectCompany = (state: RootState) => state.auth.company;
// selectMasterPassword removed for security - master passwords are now managed by masterPasswordService
// selectToken removed for security - tokens are now managed by tokenService
