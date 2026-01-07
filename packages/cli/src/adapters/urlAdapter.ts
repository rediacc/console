import type { ApiUrlProvider } from '@rediacc/shared/api';
import { contextService } from '../services/context.js';

/**
 * CLI API URL provider wrapping the contextService.
 * Gets URL from stored context or environment variable.
 */
export const urlAdapter: ApiUrlProvider = {
  getApiUrl: () => contextService.getApiUrl(),
};
