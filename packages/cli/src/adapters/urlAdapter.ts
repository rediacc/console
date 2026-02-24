import type { ApiUrlProvider } from '@rediacc/shared/api';
import { configService } from '../services/config-resources.js';

/**
 * CLI API URL provider wrapping the configService.
 * Gets URL from stored context or environment variable.
 */
export const urlAdapter: ApiUrlProvider = {
  getApiUrl: () => configService.getApiUrl(),
};
