import { endpoints } from '../../endpoints';
import type {
  QueueItem,
  QueueListResult,
  QueueStatistics,
  QueueTrace,
  QueueTraceLog,
  QueueTraceSummary,
  QueueVaultSnapshot,
  QueuePositionEntry,
  QueueMachineStats,
  QueuePlanInfo,
} from '../../types';
import type { ApiResponse } from '../../types/api';
import type { ApiClient } from './types';
import { parseResponse, responseExtractors } from '../parseResponse';

export interface QueueFilters {
  machineName?: string;
  bridgeName?: string;
  regionName?: string;
  status?: string;
  priority?: number;
  minPriority?: number;
  maxPriority?: number;
  dateFrom?: string;
  dateTo?: string;
  taskId?: string;
  includeCompleted?: boolean;
  includeCancelled?: boolean;
  onlyStale?: boolean;
  staleThresholdMinutes?: number;
  maxRecords?: number;
  createdByUserEmail?: string;
}

export interface QueueCreateResult {
  taskId: string | null;
}

function buildQueueListParams(
  teamName?: string | string[],
  filters: QueueFilters = {}
): Record<string, unknown> {
  const params: Record<string, unknown> = { ...filters };

  if (teamName) {
    params.teamName = Array.isArray(teamName) ? teamName.join(',') : teamName;
  }

  return params;
}

export function createQueueService(client: ApiClient) {
  return {
    list: async (
      teamName?: string | string[],
      filters: QueueFilters = {}
    ): Promise<QueueListResult> => {
      const response = await client.get<QueueItem | QueueStatistics>(
        endpoints.queue.getTeamQueueItems,
        buildQueueListParams(teamName, filters)
      );
      return parseQueueList(response);
    },

    getNext: async (machineName: string, itemCount = 5): Promise<QueueItem[]> => {
      const response = await client.get<QueueItem>(endpoints.queue.getQueueItemsNext, {
        machineName,
        itemCount,
      });
      return parseQueueItems(response);
    },

    create: async (
      teamName: string,
      machineName: string | undefined,
      bridgeName: string,
      queueVault: string,
      priority = 3
    ): Promise<QueueCreateResult> => {
      const response = await client.post(endpoints.queue.createQueueItem, {
        teamName,
        machineName,
        bridgeName,
        queueVault,
        priority,
      });
      return parseQueueCreateResult(response);
    },

    updateResponse: async (
      taskId: string,
      responseVault: string,
      vaultVersion?: number
    ): Promise<void> => {
      const payload: Record<string, unknown> = { taskId, responseVault };
      if (vaultVersion !== undefined) {
        payload.vaultVersion = vaultVersion;
      }
      await client.post(endpoints.queue.updateQueueItemResponse, payload);
    },

    complete: async (taskId: string, finalVault: string, finalStatus: string): Promise<void> => {
      await client.post(endpoints.queue.updateQueueItemToCompleted, {
        taskId,
        finalVault,
        finalStatus,
      });
    },

    cancel: async (taskId: string): Promise<void> => {
      await client.post(endpoints.queue.cancelQueueItem, { taskId });
    },

    delete: async (taskId: string): Promise<void> => {
      await client.post(endpoints.queue.deleteQueueItem, { taskId });
    },

    retry: async (taskId: string): Promise<void> => {
      await client.post(endpoints.queue.retryFailedQueueItem, { taskId });
    },

    updatePriority: async (taskId: string, priority: number): Promise<void> => {
      await client.post(endpoints.queue.updateQueueItemPriority, { taskId, priority });
    },

    updateProtection: async (taskId: string, isProtected: boolean): Promise<void> => {
      await client.post(endpoints.queue.updateQueueItemProtection, { taskId, isProtected });
    },

    getTrace: async (taskId: string): Promise<QueueTrace> => {
      const response = await client.get(endpoints.queue.getQueueItemTrace, { taskId });
      return parseQueueTrace(response);
    },
  };
}

function parseQueueItems(response: ApiResponse<QueueItem>): QueueItem[] {
  return parseResponse(response, {
    extractor: responseExtractors.primaryOrSecondary,
    filter: (item) => Boolean(item?.taskId),
  });
}

function parseQueueList(response: ApiResponse<QueueItem | QueueStatistics>): QueueListResult {
  let items: QueueItem[] = [];
  let statistics: QueueStatistics | null = null;

  response.resultSets?.forEach((set) => {
    const first = set.data?.[0];
    if (!first) return;

    if ('taskId' in first) {
      items = set.data as QueueItem[];
    } else if ('totalCount' in first || 'pendingCount' in first) {
      statistics = first as QueueStatistics;
    }
  });

  return { items, statistics };
}

function parseQueueTrace(response: ApiResponse): QueueTrace {
  // Result set indices (index 0 is NextRequestToken from validation):
  // 0: NextRequestToken, 1: QUEUE_ITEM_DETAILS, 2: REQUEST_VAULT, 3: RESPONSE_VAULT,
  // 4: AUDIT_USER (traceLogs), 5: RELATED_QUEUE_ITEMS, 6: QUEUE_COUNT
  const summary = getRowByIndex<QueueTraceSummary>(response, 0);
  const queueDetails = getRowByIndex<QueueItem>(response, 1);
  const vaultContent = parseVaultSnapshot(getRowByIndex<QueueVaultSnapshot>(response, 2));
  const responseVaultContent = parseVaultSnapshot(getRowByIndex<QueueVaultSnapshot>(response, 3));
  const traceLogs = getRowsByIndex<QueueTraceLog>(response, 4);
  const queuePosition = getRowsByIndex<QueuePositionEntry>(response, 5)
    .map(normalizeQueuePosition)
    .filter((entry): entry is QueuePositionEntry => entry !== null);
  const machineStats = parseMachineStats(getRowByIndex<QueueMachineStats>(response, 6));
  const planInfo = getRowByIndex<QueuePlanInfo>(response, 7) ?? null;

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

function parseVaultSnapshot(snapshot?: QueueVaultSnapshot | null): QueueVaultSnapshot | null {
  if (!snapshot) return null;

  return {
    hasContent: Boolean(snapshot.hasContent ?? snapshot.vaultContent),
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
    relativePosition: entry.relativePosition ?? 'Current',
  };
}

function parseMachineStats(stats?: QueueMachineStats | null): QueueMachineStats | null {
  if (!stats) return null;

  return {
    currentQueueDepth: stats.currentQueueDepth ?? 0,
    activeProcessingCount: stats.activeProcessingCount ?? 0,
    maxConcurrentTasks: stats.maxConcurrentTasks,
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

function parseQueueCreateResult(response: ApiResponse): QueueCreateResult {
  const row = getRowByIndex<{ taskId?: string }>(response, 1);
  return {
    taskId: typeof row?.taskId === 'string' ? row.taskId : null,
  };
}
