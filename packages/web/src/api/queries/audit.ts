import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { AuditLogEntry, AuditTraceResponse } from '@rediacc/shared/types';
export type { AuditLogEntry as AuditLog, AuditTraceRecord } from '@rediacc/shared/types';

export interface AuditLogsParams {
  startDate?: string;
  endDate?: string;
  entityFilter?: string;
  maxRecords?: number;
}

export const useAuditLogs = (params?: AuditLogsParams) => {
  return useQuery<AuditLogEntry[]>({
    queryKey: ['auditLogs', params],
    queryFn: async () => {
      try {
        return await api.audit.getLogs(
          params?.entityFilter,
          params?.startDate,
          params?.endDate,
          params?.maxRecords || 100
        );
      } catch (error) {
        console.error('Failed to fetch audit logs:', error);
        throw new Error('Unable to load audit logs. Please check your date range and try again.');
      }
    },
    retry: (failureCount, error) => {
      // Don't retry if it's a 400 Bad Request (user input error)
      if (error?.message?.includes('400')) {
        return false;
      }
      return failureCount < 2;
    },
    staleTime: 30000, // 30 seconds
    gcTime: 5 * 60 * 1000, // 5 minutes
  });
};

export const useRecentAuditLogs = (maxRecords: number = 10) => {
  return useQuery<AuditLogEntry[]>({
    queryKey: ['recentAuditLogs', maxRecords],
    queryFn: async () => {
      return api.audit.getLogs(undefined, undefined, undefined, maxRecords);
    },
  });
};

// Get entity audit trace
export const getEntityAuditTrace = async (
  entityType: string,
  entityIdentifier: string
): Promise<AuditTraceResponse> => {
  return api.audit.getEntityTrace(entityType, entityIdentifier);
};

// React Query hook for entity audit trace
export const useEntityAuditTrace = (
  entityType: string | null,
  entityIdentifier: string | null,
  enabled = true
) => {
  return useQuery({
    queryKey: ['entityAuditTrace', entityType, entityIdentifier],
    queryFn: () => {
      if (!entityType || !entityIdentifier) {
        throw new Error('Entity type and identifier are required');
      }
      return getEntityAuditTrace(entityType, entityIdentifier);
    },
    enabled: enabled && !!entityType && !!entityIdentifier,
    staleTime: 30000, // 30 seconds
    gcTime: 5 * 60 * 1000, // 5 minutes
  });
};
