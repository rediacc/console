/**
 * Queue Parsers
 */

import { extractFirstByIndex, extractPrimaryOrSecondary, extractRowsByIndex } from './base';
import { DEFAULTS } from '../../config';
import type {
  GetTeamQueueItems_ResultSet1,
  GetTeamQueueItems_ResultSet2,
  QueueListResult,
  QueueMachineStats,
  QueuePlanInfo,
  QueuePositionEntry,
  QueueTrace,
  QueueTraceLog,
  QueueTraceSummary,
  QueueVaultSnapshot,
} from '../../types';
import type { ApiResponse } from '../../types/api';

export interface QueueCreateResult {
  taskId: string | null;
}

export function parseGetTeamQueueItems(
  response: ApiResponse<GetTeamQueueItems_ResultSet1 | GetTeamQueueItems_ResultSet2>
): QueueListResult {
  let items: GetTeamQueueItems_ResultSet1[] = [];
  let statistics: GetTeamQueueItems_ResultSet2 | null = null;

  response.resultSets.forEach((set) => {
    if (set.data.length === 0) return;
    const first = set.data[0];

    if ('taskId' in first) {
      items = set.data as GetTeamQueueItems_ResultSet1[];
    } else if ('totalCount' in first || 'pendingCount' in first) {
      statistics = first;
    }
  });

  return { items, statistics };
}

export function parseGetQueueItemsNext(
  response: ApiResponse<GetTeamQueueItems_ResultSet1>
): GetTeamQueueItems_ResultSet1[] {
  return extractPrimaryOrSecondary(response).filter((item) => Boolean(item.taskId));
}

export function parseCreateQueueItem(response: ApiResponse): QueueCreateResult {
  const row = extractFirstByIndex<{ taskId?: string }>(response, 1);
  return {
    taskId: typeof row?.taskId === 'string' ? row.taskId : null,
  };
}

function parseVaultSnapshot(snapshot?: QueueVaultSnapshot | null): QueueVaultSnapshot | null {
  if (!snapshot) return null;
  return {
    hasContent: Boolean(snapshot.hasContent) || Boolean(snapshot.vaultContent),
    vaultVersion: snapshot.vaultVersion,
    vaultContent: snapshot.vaultContent,
    updatedAt: snapshot.updatedAt,
  };
}

function normalizeQueuePosition(
  entry?: Partial<QueuePositionEntry> | null
): QueuePositionEntry | null {
  if (!entry?.taskId || !entry.createdTime || !entry.status) {
    return null;
  }
  return {
    taskId: entry.taskId,
    status: entry.status,
    createdTime: entry.createdTime,
    relativePosition: entry.relativePosition ?? DEFAULTS.STATUS.CURRENT,
  };
}

function parseMachineStats(stats?: QueueMachineStats | null): QueueMachineStats | null {
  if (!stats) return null;
  return {
    currentQueueDepth: stats.currentQueueDepth,
    activeProcessingCount: stats.activeProcessingCount,
    maxConcurrentTasks: stats.maxConcurrentTasks,
  };
}

export function parseGetQueueItemTrace(response: ApiResponse): QueueTrace {
  const summary = extractFirstByIndex<QueueTraceSummary>(response, 0);
  const queueDetails = extractFirstByIndex<GetTeamQueueItems_ResultSet1>(response, 1);
  const vaultContent = parseVaultSnapshot(extractFirstByIndex<QueueVaultSnapshot>(response, 2));
  const responseVaultContent = parseVaultSnapshot(
    extractFirstByIndex<QueueVaultSnapshot>(response, 3)
  );
  const traceLogs = extractRowsByIndex<QueueTraceLog>(response, 4);
  const queuePosition = extractRowsByIndex<QueuePositionEntry>(response, 5)
    .map(normalizeQueuePosition)
    .filter((entry): entry is QueuePositionEntry => entry !== null);
  const machineStats = parseMachineStats(extractFirstByIndex<QueueMachineStats>(response, 6));
  const planInfo = extractFirstByIndex<QueuePlanInfo>(response, 7) ?? null;

  return {
    summary: summary ?? null,
    queueDetails: queueDetails ?? null,
    traceLogs,
    vaultContent,
    responseVaultContent,
    queuePosition,
    machineStats,
    planInfo,
  };
}

export const parseQueueList = parseGetTeamQueueItems;
export const parseQueueTrace = parseGetQueueItemTrace;
