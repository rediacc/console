import type { ApiUrlProvider } from '@rediacc/shared/api';
import { apiConnectionService } from '@/services/api';

/**
 * Web API URL provider wrapping the apiConnectionService.
 * Performs health checks and endpoint selection.
 */
export const urlAdapter: ApiUrlProvider = {
  getApiUrl: () => apiConnectionService.getApiUrl(),
};
