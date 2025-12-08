import { parseResponse, responseExtractors } from '../parseResponse';
import type { ApiClient } from './types';
import type {
  GetTeamQueueItems_ResultSet1,
  GetTeamQueueItems_ResultSet2,
  QueueListResult,
  QueueTrace,
  QueueTraceLog,
  QueueTraceSummary,
  QueueVaultSnapshot,
  QueuePositionEntry,
  QueueMachineStats,
  QueuePlanInfo,
  GetTeamQueueItemsParams,
  CreateQueueItemParams,
  CancelQueueItemParams,
  DeleteQueueItemParams,
  RetryFailedQueueItemParams,
  GetQueueItemTraceParams,
  UpdateQueueItemResponseParams,
  UpdateQueueItemToCompletedParams,
} from '../../types';
import type { ApiResponse } from '../../types/api';

export type QueueFilters = Partial<Omit<GetTeamQueueItemsParams, 'teamName'>>;

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
      const response = await client.get<
        GetTeamQueueItems_ResultSet1 | GetTeamQueueItems_ResultSet2
      >('/GetTeamQueueItems', buildQueueListParams(teamName, filters));
      return parseQueueList(response);
    },

    getNext: async (
      machineName: string,
      itemCount = 5
    ): Promise<GetTeamQueueItems_ResultSet1[]> => {
      const response = await client.get<GetTeamQueueItems_ResultSet1>('/GetQueueItemsNext', {
        machineName,
        itemCount,
      });
      return parseQueueItems(response);
    },

    create: async (params: CreateQueueItemParams): Promise<QueueCreateResult> => {
      const response = await client.post('/CreateQueueItem', params);
      return parseQueueCreateResult(response);
    },

    updateResponse: async (params: UpdateQueueItemResponseParams): Promise<void> => {
      await client.post('/UpdateQueueItemResponse', params);
    },

    complete: async (params: UpdateQueueItemToCompletedParams): Promise<void> => {
      await client.post('/UpdateQueueItemToCompleted', params);
    },

    cancel: async (params: CancelQueueItemParams): Promise<void> => {
      await client.post('/CancelQueueItem', params);
    },

    delete: async (params: DeleteQueueItemParams): Promise<void> => {
      await client.post('/DeleteQueueItem', params);
    },

    retry: async (params: RetryFailedQueueItemParams): Promise<void> => {
      await client.post('/RetryFailedQueueItem', params);
    },

    getTrace: async (params: GetQueueItemTraceParams): Promise<QueueTrace> => {
      const response = await client.get('/GetQueueItemTrace', params);
      return parseQueueTrace(response);
    },
  };
}

function parseQueueItems(
  response: ApiResponse<GetTeamQueueItems_ResultSet1>
): GetTeamQueueItems_ResultSet1[] {
  return parseResponse(response, {
    extractor: responseExtractors.primaryOrSecondary,
    filter: (item) => Boolean(item?.taskId),
  });
}

function parseQueueList(
  response: ApiResponse<GetTeamQueueItems_ResultSet1 | GetTeamQueueItems_ResultSet2>
): QueueListResult {
  let items: GetTeamQueueItems_ResultSet1[] = [];
  let statistics: GetTeamQueueItems_ResultSet2 | null = null;

  response.resultSets?.forEach((set) => {
    const first = set.data?.[0];
    if (!first) return;

    if ('taskId' in first) {
      items = set.data as GetTeamQueueItems_ResultSet1[];
    } else if ('totalCount' in first || 'pendingCount' in first) {
      statistics = first as GetTeamQueueItems_ResultSet2;
    }
  });

  return { items, statistics };
}

function parseQueueTrace(response: ApiResponse): QueueTrace {
  // Result set indices (index 0 is NextRequestToken from validation):
  // 0: NextRequestToken, 1: QUEUE_ITEM_DETAILS, 2: REQUEST_VAULT, 3: RESPONSE_VAULT,
  // 4: AUDIT_USER (traceLogs), 5: RELATED_QUEUE_ITEMS, 6: QUEUE_COUNT
  const summary = getRowByIndex<QueueTraceSummary>(response, 0);
  const queueDetails = getRowByIndex<GetTeamQueueItems_ResultSet1>(response, 1);
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
