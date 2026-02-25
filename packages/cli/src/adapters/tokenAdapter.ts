import type { TokenAdapter } from '@rediacc/shared/api';
import { configService } from '../services/config-resources.js';

/**
 * CLI token adapter wrapping the configService.
 * Stores tokens in file-based config (platform config dir).
 */
export const tokenAdapter: TokenAdapter = {
  get: () => configService.getToken(),
  set: (token: string) => configService.setToken(token),
  clear: async () => {
    // In CLI, clearing token means clearing credentials from context
    await configService.clearCredentials();
  },
};
