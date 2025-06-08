import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../client';

export interface AuditLog {
  entity: string;
  entityName: string;
  action: string;
  details: string;
  actionByUser: string;
  timestamp: string;
}

export interface AuditLogsParams {
  startDate?: string;
  endDate?: string;
  entityFilter?: string;
  maxRecords?: number;
}

export const useAuditLogs = (params?: AuditLogsParams) => {
  return useQuery({
    queryKey: ['auditLogs', params],
    queryFn: async () => {
      const response = await apiClient.post('/GetAuditLogs', {
        startDate: params?.startDate,
        endDate: params?.endDate,
        entityFilter: params?.entityFilter,
        maxRecords: params?.maxRecords || 100
      });
      
      return response.tables?.[1]?.data as AuditLog[] || [];
    }
  });
};

export const useRecentAuditLogs = (maxRecords: number = 10) => {
  return useQuery({
    queryKey: ['recentAuditLogs', maxRecords],
    queryFn: async () => {
      const response = await apiClient.post('/GetAuditLogs', {
        maxRecords
      });
      
      return response.tables?.[1]?.data as AuditLog[] || [];
    }
  });
};