/**
 * Audit Parsers
 */

import { extractRowsByIndex, extractFirstByIndex } from './base';
import type {
  AuditTraceRecord,
  AuditTraceResponse,
  AuditTraceSummary,
  GetAuditLogs_ResultSet1,
} from '../../types';
import type { ApiResponse } from '../../types/api';

export function parseGetAuditLogs(
  response: ApiResponse<GetAuditLogs_ResultSet1>
): GetAuditLogs_ResultSet1[] {
  return extractRowsByIndex<GetAuditLogs_ResultSet1>(response, 1);
}

export function parseGetEntityAuditTrace(response: ApiResponse): AuditTraceResponse {
  const records = extractRowsByIndex<AuditTraceRecord>(response, 1);
  const summary = extractFirstByIndex<AuditTraceSummary>(response, 2) ?? {
    entityType: '',
    entityName: '',
    entityId: 0,
    totalAuditRecords: records.length,
    visibleAuditRecords: records.length,
    oldestVisibleActivity: null,
    lastActivity: null,
    hasAccess: true,
    isAdmin: false,
    subscriptionTier: '',
    auditRetentionDays: 0,
    hasOlderRecords: false,
    relatedCount: 0,
  };

  return { records, summary };
}

export const parseAuditLogs = parseGetAuditLogs;
export const parseEntityTrace = parseGetEntityAuditTrace;
