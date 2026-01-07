/**
 * System Domain Hooks
 *
 * System-level hooks that don't use stored procedures:
 * - API health check (direct axios call)
 */
import { useQuery } from '@tanstack/react-query';
import axios from 'axios';
import { apiConnectionService } from '@/services/api';
import type { ApiHealthResponse } from '@rediacc/shared/types';

/**
 * Fetch API health status directly from /health endpoint.
 */
const fetchApiHealth = async (): Promise<ApiHealthResponse> => {
  const apiUrl = await apiConnectionService.getApiUrl();
  const response = await axios.get<ApiHealthResponse>(`${apiUrl}/health`, {
    timeout: 5000,
  });
  return response.data;
};

/**
 * Check if the API is available and healthy.
 * Polls every 60 seconds with 30 second stale time.
 */
export const useApiHealth = () => {
  return useQuery({
    queryKey: ['apiHealth'],
    queryFn: fetchApiHealth,
    staleTime: 30 * 1000,
    refetchInterval: 60 * 1000,
    retry: 1,
  });
};
