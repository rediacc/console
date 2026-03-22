import type { TokenAdapter } from '@rediacc/shared/api';
import { tokenService } from '@/services/auth/tokenService';

/**
 * Web token adapter wrapping the tokenService.
 * Provides secure in-memory token storage with locking.
 */
export const tokenAdapter: TokenAdapter = {
  get: () => tokenService.getToken(),
  set: (token: string) => tokenService.setToken(token),
  clear: () => tokenService.clearToken(),
};
