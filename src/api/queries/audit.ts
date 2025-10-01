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
      try {
        // Build request body, only including defined parameters
        const requestBody: Record<string, any> = {
          maxRecords: params?.maxRecords || 100
        };

        // Only include date parameters if they have valid values
        if (params?.startDate) {
          requestBody.startDate = params.startDate;
        }
        if (params?.endDate) {
          requestBody.endDate = params.endDate;
        }
        if (params?.entityFilter) {
          requestBody.entityFilter = params.entityFilter;
        }

        const response = await apiClient.post('/GetAuditLogs', requestBody);

        return response.resultSets?.[1]?.data as AuditLog[] || [];
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
  return useQuery({
    queryKey: ['recentAuditLogs', maxRecords],
    queryFn: async () => {
      const response = await apiClient.post('/GetAuditLogs', {
        maxRecords
      });
      
      return response.resultSets?.[1]?.data as AuditLog[] || [];
    }
  });
};

// Audit Trace Response Types
export interface AuditTraceRecord {
  action: string;
  details: string;
  performedBy: string;
  timestamp: string;
  actionType: string;
  timeAgo: string;
  iconHint: string;
}

export interface AuditTraceSummary {
  entityType: string;
  entityName: string;
  entityId: number;
  totalAuditRecords: number;
  visibleAuditRecords: number;
  oldestVisibleActivity: string | null;
  lastActivity: string | null;
  hasAccess: boolean;
  isAdmin: boolean;
  subscriptionTier: string;
  auditRetentionDays: number;
  hasOlderRecords: boolean;
  relatedCount: number;
}

export interface AuditTraceResponse {
  records: AuditTraceRecord[];
  summary: AuditTraceSummary;
}

// Get entity audit trace
export const getEntityAuditTrace = async (
  entityType: string,
  entityIdentifier: string
): Promise<AuditTraceResponse> => {
  const response = await apiClient.post('/GetEntityAuditTrace', {
    entityType,
    entityIdentifier
  });

  // The stored procedure returns three result sets:
  // Table 0: Token rotation (nextRequestToken)
  // Table 1: Audit records
  // Table 2: Summary information
  const records = response.resultSets?.[1]?.data || [];
  const summary = response.resultSets?.[2]?.data?.[0] || null;

  return {
    records,
    summary
  };
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