import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import { QUERY_KEYS } from '@/api/queryKeys';
import { useMutationWithFeedback } from '@/hooks/useMutationWithFeedback';
import i18n from '@/i18n/config';
import { invalidateAllQueueCaches } from '@/utils/cacheUtils';
import { minifyJSON } from '@/utils/json';
import type {
  CancelQueueItemParams,
  CreateQueueItemParams,
  DeleteQueueItemParams,
  GetQueueItemTraceParams,
  QueueFilters,
  QueueListResult,
  QueueTrace,
  RetryFailedQueueItemParams,
  UpdateQueueItemResponseParams,
  UpdateQueueItemToCompletedParams,
} from '@rediacc/shared/types';

export type { QueueFilters };

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
  checkboxOptions?: Array<{ value: string; label: string }>;
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
      return api.queue.list(teamName, rest);
    },
    // refetchInterval: 5000, // Disabled auto-refresh
  });
};

// Get next queue items for machine
export const useNextQueueItems = (machineName: string, itemCount: number = 5) => {
  return useQuery({
    queryKey: QUERY_KEYS.queue.next(machineName, itemCount),
    queryFn: async () => {
      return api.queue.getNext(machineName, itemCount);
    },
    enabled: !!machineName,
  });
};

// Get queue items by bridge (using GetTeamQueueItems with bridge filter)
export const useQueueItemsByBridge = (bridgeName: string, teamName?: string) => {
  return useQueueItems({
    teamName: teamName || '',
    bridgeName,
    includeCompleted: true,
    includeCancelled: false, // Don't show cancelled tasks by default
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
      const priority = data.priority && data.priority >= 1 && data.priority <= 5 ? data.priority : 3;
      // Minify the vault JSON before sending
      const params: CreateQueueItemParams = {
        teamName: data.teamName,
        machineName: data.machineName || '',
        bridgeName: data.bridgeName,
        vaultContent: minifyJSON(data.queueVault),
        priority,
      };
      return api.queue.create(params);
    },
    successMessage: i18n.t('queue:success.created'),
    errorMessage: i18n.t('queue:errors.createFailed'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.queue.items() });
    },
  });
};

// Update queue item response
export const useUpdateQueueItemResponse = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<
    unknown,
    Error,
    {
      taskId: string;
      responseVault: string;
    }
  >({
    mutationFn: async (data) => {
      // Minify the vault JSON before sending
      const params: UpdateQueueItemResponseParams = {
        taskId: data.taskId,
        vaultContent: minifyJSON(data.responseVault),
      };
      return api.queue.updateResponse(params);
    },
    successMessage: (_, vars) => i18n.t('queue:success.responseUpdated', { taskId: vars.taskId }),
    errorMessage: i18n.t('queue:errors.updateFailed'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.queue.items() });
    },
  });
};

// Complete or fail queue item
export const useCompleteQueueItem = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<
    unknown,
    Error,
    {
      taskId: string;
      finalVault: string;
      finalStatus?: 'COMPLETED' | 'FAILED';
    }
  >({
    mutationFn: async (data) => {
      // Minify the vault JSON before sending
      const params: UpdateQueueItemToCompletedParams = {
        taskId: data.taskId,
        vaultContent: minifyJSON(data.finalVault),
        finalStatus: data.finalStatus || 'COMPLETED', // Default to COMPLETED for backward compatibility
      };
      return api.queue.complete(params);
    },
    successMessage: (_, vars) => {
      const status = vars.finalStatus || 'COMPLETED';
      return status === 'FAILED'
        ? i18n.t('queue:success.markedFailed', { taskId: vars.taskId })
        : i18n.t('queue:success.completed', { taskId: vars.taskId });
    },
    errorMessage: i18n.t('queue:errors.updateFailed'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.queue.items() });
    },
  });
};

// Cancel queue item
export const useCancelQueueItem = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, string>({
    mutationFn: async (taskId) => {
      const params: CancelQueueItemParams = { taskId };
      return api.queue.cancel(params);
    },
    successMessage: (_, taskId) => i18n.t('queue:success.cancellationInitiated', { taskId }),
    errorMessage: i18n.t('queue:errors.cancelFailed'),
    onSuccess: () => {
      invalidateAllQueueCaches(queryClient);
    },
  });
};

// Delete queue item
export const useDeleteQueueItem = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, string>({
    mutationFn: async (taskId) => {
      const params: DeleteQueueItemParams = { taskId };
      return api.queue.delete(params);
    },
    successMessage: (_, taskId) => i18n.t('queue:success.deleted', { taskId }),
    errorMessage: i18n.t('queue:errors.deleteFailed'),
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
      return api.queue.retry(params);
    },
    successMessage: (_, taskId) => i18n.t('queue:success.queuedForRetry', { taskId }),
    errorMessage: i18n.t('queue:errors.retryFailed'),
    onSuccess: (_, taskId) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.queue.items() });
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.queue.itemTrace(taskId) });
    },
  });
};

// Get queue item trace
export const useQueueItemTrace = (taskId: string | null, enabled: boolean = true) => {
  return useQuery<QueueTrace | null>({
    queryKey: QUERY_KEYS.queue.itemTrace(taskId),
    queryFn: async () => {
      if (!taskId) return null;
      const params: GetQueueItemTraceParams = { taskId };
      const trace = await api.queue.getTrace(params);
      return trace;
    },
    enabled: enabled && !!taskId,
    refetchInterval: (query) => {
      // The query parameter contains the full query state, with data in query.state.data
      const data = query.state.data;
      // Stop refreshing if the task is completed, cancelled, or permanently failed
      const status = data?.queueDetails?.status;
      const retryCount = data?.queueDetails?.retryCount || 0;
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
