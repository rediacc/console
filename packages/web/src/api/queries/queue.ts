import { useQuery, useQueryClient } from '@tanstack/react-query';
import { typedApi } from '@/api/client';
import { QUERY_KEYS } from '@/api/queryKeys';
import { useMutationWithFeedback } from '@/hooks/useMutationWithFeedback';
import i18n from '@/i18n/config';
import { minifyJSON } from '@/platform/utils/json';
import { invalidateAllQueueCaches } from '@/utils/cacheUtils';
import { extractByIndex, extractFirstByIndex } from '@rediacc/shared/api/typedApi';
import type {
  CancelQueueItemParams,
  CreateQueueItemParams,
  GetQueueItemTraceParams,
  QueueFilters,
  QueueListResult,
  QueueTrace,
  QueueTraceLog,
  RetryFailedQueueItemParams,
  GetTeamQueueItems_ResultSet1,
  GetTeamQueueItems_ResultSet2,
  GetQueueItemTrace_ResultSet1,
  GetQueueItemTrace_ResultSet2,
  GetQueueItemTrace_ResultSet3,
  GetQueueItemTrace_ResultSet4,
  GetQueueItemTrace_ResultSet5,
  GetQueueItemTrace_ResultSet6,
  QueueStatus,
} from '@rediacc/shared/types';

export type { QueueFilters } from '@rediacc/shared/types';

export interface QueueFunctionParameter {
  type: string;
  required?: boolean;
  default?: unknown;
  help?: string;
  label?: string;
  format?: string;
  units?: string[];
  options?: string[];
  ui?: string;
  checkboxOptions?: { value: string; label: string }[];
}

export interface QueueFunctionRequirements {
  machine?: boolean;
  team?: boolean;
  company?: boolean;
  repository?: boolean;
  storage?: boolean;
  plugin?: boolean;
  bridge?: boolean;
}

export interface QueueFunction {
  name: string;
  description: string;
  category: string;
  params: Record<string, QueueFunctionParameter>;
  showInMenu?: boolean;
  requirements?: QueueFunctionRequirements;
}

export interface QueueCreateResult {
  taskId: string | null;
}

// Queue functions will be loaded via the functionsService instead

// Get queue items with advanced filtering
export const useQueueItems = (filters: QueueFilters = {}) => {
  return useQuery<QueueListResult>({
    queryKey: QUERY_KEYS.queue.items(filters),
    queryFn: async () => {
      const { teamName, ...rest } = filters;
      const response = await typedApi.GetTeamQueueItems({ teamName, ...rest });
      // Extract queue items from result set 1 and statistics from result set 2
      const items = extractByIndex<GetTeamQueueItems_ResultSet1>(response, 1);
      const statistics = extractFirstByIndex<GetTeamQueueItems_ResultSet2>(response, 2);
      return { items, statistics };
    },
    // refetchInterval: 5000, // Disabled auto-refresh
  });
};

// Create queue item (direct API call - use useManagedQueueItem for high-priority items)
export const useCreateQueueItem = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<
    QueueCreateResult,
    Error,
    {
      teamName: string;
      machineName?: string;
      bridgeName: string;
      queueVault: string;
      priority?: number;
    }
  >({
    mutationFn: async (data) => {
      // Ensure priority is within valid range
      const priority =
        data.priority && data.priority >= 1 && data.priority <= 5 ? data.priority : 3;
      // Minify the vault JSON before sending
      const params: CreateQueueItemParams = {
        teamName: data.teamName,
        machineName: data.machineName ?? '',
        bridgeName: data.bridgeName,
        vaultContent: minifyJSON(data.queueVault),
        priority,
      };
      const response = await typedApi.CreateQueueItem(params);
      const result = extractFirstByIndex<QueueCreateResult>(response, 0);
      return result ?? { taskId: null };
    },
    successMessage: i18n.t('queue:success.created'),
    errorMessage: i18n.t('queue:errors.createFailed'),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: QUERY_KEYS.queue.items() });
    },
  });
};

// Cancel queue item
export const useCancelQueueItem = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, string>({
    mutationFn: async (taskId) => {
      const params: CancelQueueItemParams = { taskId };
      return typedApi.CancelQueueItem(params);
    },
    successMessage: (_, taskId) => i18n.t('queue:success.cancellationInitiated', { taskId }),
    errorMessage: i18n.t('queue:errors.cancelFailed'),
    onSuccess: () => {
      invalidateAllQueueCaches(queryClient);
    },
  });
};

// Retry failed queue item
export const useRetryFailedQueueItem = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, string>({
    mutationFn: async (taskId) => {
      const params: RetryFailedQueueItemParams = { taskId };
      return typedApi.RetryFailedQueueItem(params);
    },
    successMessage: (_, taskId) => i18n.t('queue:success.queuedForRetry', { taskId }),
    errorMessage: i18n.t('queue:errors.retryFailed'),
    onSuccess: (_, taskId) => {
      void queryClient.invalidateQueries({ queryKey: QUERY_KEYS.queue.items() });
      void queryClient.invalidateQueries({ queryKey: QUERY_KEYS.queue.itemTrace(taskId) });
    },
  });
};

// Get queue item trace
export const useQueueItemTrace = (taskId: string | null, enabled = true) => {
  return useQuery<QueueTrace | null>({
    queryKey: QUERY_KEYS.queue.itemTrace(taskId),
    queryFn: async () => {
      if (!taskId) return null;
      const params: GetQueueItemTraceParams = { taskId };
      const response = await typedApi.GetQueueItemTrace(params);
      // GetQueueItemTrace returns multiple result sets:
      // Index 0: NEXT_REQUEST_CREDENTIAL (token)
      // Index 1: QUEUE_ITEM_DETAILS
      // Index 2: REQUEST_VAULT
      // Index 3: RESPONSE_VAULT (console output)
      // Index 4: AUDIT_USER (trace logs)
      // Index 5: RELATED_QUEUE_ITEMS
      // Index 6: QUEUE_COUNT (machine stats)
      const queueDetails = extractFirstByIndex<GetQueueItemTrace_ResultSet1>(response, 1);
      const requestVault = extractFirstByIndex<GetQueueItemTrace_ResultSet2>(response, 2);
      const responseVault = extractFirstByIndex<GetQueueItemTrace_ResultSet3>(response, 3);
      const traceLogs = extractByIndex<GetQueueItemTrace_ResultSet4>(response, 4);
      const relatedItems = extractByIndex<GetQueueItemTrace_ResultSet5>(response, 5);
      const machineStats = extractFirstByIndex<GetQueueItemTrace_ResultSet6>(response, 6);

      if (!queueDetails) return null;

      // Build QueueTrace structure - extracting fields from queueDetails for summary
      return {
        summary: {
          taskId: queueDetails.taskId,
          status: queueDetails.status as QueueStatus | undefined,
          healthStatus: undefined, // Not in result set
          progress: undefined, // Not in result set
          consoleOutput: undefined, // Not in result set
          errorMessage: undefined, // Not in result set
          lastFailureReason: queueDetails.lastFailureReason ?? undefined,
          priority: queueDetails.priority ?? undefined,
          retryCount: queueDetails.retryCount,
          ageInMinutes: undefined, // Not in result set
          hasResponse: queueDetails.lastResponseAt !== null,
          teamName: queueDetails.teamName,
          machineName: queueDetails.machineName,
          bridgeName: queueDetails.bridgeName,
          createdTime: queueDetails.createdTime,
        },
        queueDetails: queueDetails as unknown as GetTeamQueueItems_ResultSet1,
        traceLogs: traceLogs as unknown as QueueTraceLog[],
        vaultContent: requestVault
          ? { vaultContent: requestVault.vaultContent, hasContent: !!requestVault.hasContent }
          : null,
        responseVaultContent: responseVault
          ? { vaultContent: responseVault.vaultContent, hasContent: !!responseVault.hasContent }
          : null,
        queuePosition: relatedItems as unknown as QueueTrace['queuePosition'],
        machineStats: machineStats as unknown as QueueTrace['machineStats'],
        planInfo: null,
      };
    },
    enabled: enabled && !!taskId,
    refetchInterval: (query) => {
      // The query parameter contains the full query state, with data in query.state.data
      const data = query.state.data;
      // Stop refreshing if the task is completed, cancelled, or permanently failed
      const status = data?.queueDetails?.status;
      const retryCount = data?.queueDetails?.retryCount ?? 0;
      const permanentlyFailed = data?.queueDetails?.permanentlyFailed;
      const lastFailureReason = data?.queueDetails?.lastFailureReason;

      // Stop polling for completed or cancelled tasks
      if (status === 'COMPLETED' || status === 'CANCELLED') {
        return false;
      }

      // Continue polling for CANCELLING status (it will transition to CANCELLED)
      if (status === 'CANCELLING') {
        return enabled && taskId ? 1000 : false;
      }

      // Stop polling for permanently failed tasks (retry count >= 3)
      if (status === 'FAILED' && (permanentlyFailed || retryCount >= 3)) {
        return false;
      }

      // Stop polling for tasks with specific permanent failure messages
      if ((status === 'FAILED' || status === 'PENDING') && lastFailureReason) {
        // Check for bridge reported failure or other permanent failures
        const permanentFailureMessages = [
          'Bridge reported failure',
          'Task permanently failed',
          'Fatal error',
        ];
        if (permanentFailureMessages.some((msg) => lastFailureReason.includes(msg))) {
          return false;
        }
      }

      // Stop polling for PENDING tasks that have reached max retries (3)
      // These are tasks that failed 3 times and are stuck in PENDING status
      if (status === 'PENDING' && retryCount >= 3 && lastFailureReason) {
        return false;
      }

      // Continue polling for all other states, including FAILED tasks that can be retried
      // Refresh every 1 second when enabled
      return enabled && taskId ? 1000 : false;
    },
    // Ensure that refetch waits for the previous request to complete
    refetchIntervalInBackground: false,
    // This ensures new requests wait for the previous one to complete
    networkMode: 'online',
  });
};

export type { QueueStatistics } from '@rediacc/shared/types';
