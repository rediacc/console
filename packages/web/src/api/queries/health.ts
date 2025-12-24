import { useQuery } from '@tanstack/react-query';
import axios from 'axios';
import { apiConnectionService } from '@/services/api';

export interface ApiHealthResponse {
  status: string;
  version: string;
  environment: string;
  instanceName: string;
  timestamp: string;
  uptime: {
    days: number;
    hours: number;
    minutes: number;
  };
  database: {
    status: string;
    database?: string;
    error?: string;
  };
  shuttingDown?: boolean;
  ciMode?: boolean;
}

const fetchApiHealth = async (): Promise<ApiHealthResponse> => {
  const apiUrl = await apiConnectionService.getApiUrl();
  const response = await axios.get<ApiHealthResponse>(`${apiUrl}/health`, {
    timeout: 5000,
  });
  return response.data;
};

export const useApiHealth = () => {
  return useQuery({
    queryKey: ['apiHealth'],
    queryFn: fetchApiHealth,
    staleTime: 30 * 1000, // 30 seconds
    refetchInterval: 60 * 1000, // Refresh every minute
    retry: 1,
  });
};
