import type { TokenAdapter } from '@rediacc/shared/api';
import { contextService } from '../services/context.js';

/**
 * CLI token adapter wrapping the contextService.
 * Stores tokens in file-based config (~/.rediacc/).
 */
export const tokenAdapter: TokenAdapter = {
  get: () => contextService.getToken(),
  set: (token: string) => contextService.setToken(token),
  clear: async () => {
    // In CLI, clearing token means clearing credentials from context
    await contextService.clearCredentials();
  },
};
