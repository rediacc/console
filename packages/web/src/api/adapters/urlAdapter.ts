import { apiConnectionService } from '@/services/api';
import type { ApiUrlProvider } from '@rediacc/shared/api';

/**
 * Web API URL provider wrapping the apiConnectionService.
 * Performs health checks and endpoint selection.
 */
export const urlAdapter: ApiUrlProvider = {
  getApiUrl: () => apiConnectionService.getApiUrl(),
};
