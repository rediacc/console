import { useQuery } from '@tanstack/react-query';
import { typedApi } from '@/api/client';
import { extractByIndex, extractFirstByIndex } from '@rediacc/shared/api/typedApi';
import type {
  AuditTraceResponse,
  GetAuditLogs_ResultSet1,
  AuditTraceRecord,
  AuditTraceSummary,
} from '@rediacc/shared/types';

export type { AuditTraceRecord, GetAuditLogs_ResultSet1 } from '@rediacc/shared/types';

// Type alias for clearer usage in components
export type AuditLog = GetAuditLogs_ResultSet1;

export interface AuditLogsParams {
  startDate?: string;
  endDate?: string;
  entityFilter?: string;
  maxRecords?: number;
}

export const useAuditLogs = (params?: AuditLogsParams) => {
  return useQuery<GetAuditLogs_ResultSet1[]>({
    queryKey: ['auditLogs', params],
    queryFn: async () => {
      try {
        const response = await typedApi.GetAuditLogs({
          entityFilter: params?.entityFilter,
          startDate: params?.startDate,
          endDate: params?.endDate,
          maxRecords: params?.maxRecords ?? 100,
        });
        // Extract from index 1 (primary data after token result set)
        return extractByIndex<GetAuditLogs_ResultSet1>(response, 1);
      } catch (error) {
        console.error('Failed to fetch audit logs:', error);
        throw new Error('Unable to load audit logs. Please check your date range and try again.');
      }
    },
    retry: (failureCount, error) => {
      // Don't retry if it's a 400 Bad Request (user input error)
      if (error instanceof Error && error.message.includes('400')) {
        return false;
      }
      return failureCount < 2;
    },
    staleTime: 30000, // 30 seconds
    gcTime: 5 * 60 * 1000, // 5 minutes
  });
};

export const useRecentAuditLogs = (maxRecords: number = 10) => {
  return useQuery<GetAuditLogs_ResultSet1[]>({
    queryKey: ['recentAuditLogs', maxRecords],
    queryFn: async () => {
      const response = await typedApi.GetAuditLogs({ maxRecords });
      return extractByIndex<GetAuditLogs_ResultSet1>(response, 1);
    },
  });
};

// Get entity audit trace
const getEntityAuditTrace = async (
  entityType: string,
  entityIdentifier: string
): Promise<AuditTraceResponse> => {
  const response = await typedApi.GetEntityAuditTrace({ entityType, entityIdentifier });
  // GetEntityAuditTrace returns two result sets: records and summary
  const records = extractByIndex<AuditTraceRecord>(response, 1);
  const summaryData = extractFirstByIndex<AuditTraceSummary>(response, 2);

  if (!summaryData) {
    throw new Error('No audit trace summary returned');
  }

  return { records, summary: summaryData };
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
