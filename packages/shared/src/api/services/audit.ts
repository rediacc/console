import { endpoints } from '../../endpoints';
import type {
  AuditHistoryEntry,
  AuditLogEntry,
  AuditTraceResponse,
  AuditTraceRecord,
  AuditTraceSummary,
} from '../../types';
import type { ApiResponse } from '../../types/api';
import { parseResponse, responseExtractors } from '../parseResponse';
import type { ApiClient } from './types';

export interface AuditLogOptions {
  offset?: number;
}

export function createAuditService(client: ApiClient) {
  return {
    getLogs: async (
      entityType?: string,
      startDate?: string,
      endDate?: string,
      maxRecords = 100,
      options: AuditLogOptions = {}
    ): Promise<AuditLogEntry[]> => {
      const response = await client.post<AuditLogEntry>(endpoints.audit.getAuditLogs, {
        entityFilter: entityType,
        startDate,
        endDate,
        maxRecords,
        offset: options.offset,
      });

      return parseResponse(response, {
        extractor: responseExtractors.byIndex<AuditLogEntry>(1),
      });
    },

    getEntityTrace: async (entityType: string, entityName: string): Promise<AuditTraceResponse> => {
      const response = await client.post(endpoints.audit.getEntityAuditTrace, {
        entityType,
        entityIdentifier: entityName,
      });

      const records = getRowsByIndex<AuditTraceRecord>(response, 1);
      const summary = getRowByIndex<AuditTraceSummary>(response, 2);

      if (!summary) {
        throw new Error('Missing audit trace summary');
      }

      return {
        records,
        summary,
      };
    },

    getEntityHistory: async (
      entityType: string,
      entityName: string
    ): Promise<AuditHistoryEntry[]> => {
      const response = await client.post<AuditHistoryEntry>(endpoints.audit.getEntityHistory, {
        entityType,
        entityIdentifier: entityName,
      });

      return parseResponse(response, {
        extractor: responseExtractors.byIndex<AuditHistoryEntry>(1),
      });
    },
  };
}

function getRowsByIndex<T>(response: ApiResponse, index: number): T[] {
  if (!response.resultSets || !response.resultSets[index]) {
    return [];
  }

  const table = response.resultSets[index];
  return (table?.data as T[]) ?? [];
}

function getRowByIndex<T>(response: ApiResponse, index: number): T | null {
  const rows = getRowsByIndex<T>(response, index);
  return rows.length > 0 ? rows[0] : null;
}
