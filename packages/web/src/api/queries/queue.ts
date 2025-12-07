import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import { QUERY_KEYS } from '@/api/queryKeys';
import i18n from '@/i18n/config';
import { invalidateQueueCaches, invalidateAllQueueCaches } from '@/utils/cacheUtils';
import { minifyJSON } from '@/utils/json';
import { showMessage } from '@/utils/messages';
import { createErrorHandler } from '@/utils/mutationUtils';
import type { QueueTrace, QueueListResult } from '@rediacc/shared/types';

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

export interface QueueFunction {
  name: string;
  description: string;
  category: string;
  params: Record<string, QueueFunctionParameter>;
}

// Queue functions will be loaded via the functionsService instead

// Parameters for GetTeamQueueItems
export interface QueueFilters {
  teamName?: string; // Comma-separated team names
  machineName?: string;
  bridgeName?: string;
  regionName?: string;
  status?: string; // Comma-separated status values
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

  return useMutation({
    mutationFn: async (data: {
      teamName: string;
      machineName?: string; // Made optional for bridge-only queue items
      bridgeName: string;
      queueVault: string;
      priority?: number; // Optional priority (1-5), defaults to 3
    }) => {
      // Ensure priority is within valid range
      const priority =
        data.priority && data.priority >= 1 && data.priority <= 5 ? data.priority : 3;
      // Minify the vault JSON before sending
      const minifiedData = {
        ...data,
        queueVault: minifyJSON(data.queueVault),
        priority,
      };
      const response = await api.queue.create(
        minifiedData.teamName,
        minifiedData.machineName,
        minifiedData.bridgeName,
        minifiedData.queueVault,
        minifiedData.priority
      );
      return response;
    },
    onSuccess: (response, variables) => {
      invalidateQueueCaches(queryClient, variables.bridgeName);
      const message = response.taskId
        ? i18n.t('queue:success.createdWithId', { taskId: response.taskId })
        : i18n.t('queue:success.created');
      showMessage('success', message);
    },
    onError: createErrorHandler(i18n.t('queue:errors.createFailed')),
  });
};

// Update queue item response
export const useUpdateQueueItemResponse = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: { taskId: string; responseVault: string }) => {
      // Minify the vault JSON before sending
      const minifiedData = {
        ...data,
        responseVault: minifyJSON(data.responseVault),
      };
      return api.queue.updateResponse(minifiedData.taskId, minifiedData.responseVault);
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.queue.items() });
      showMessage('success', i18n.t('queue:success.responseUpdated', { taskId: variables.taskId }));
    },
    onError: createErrorHandler(i18n.t('queue:errors.updateFailed')),
  });
};

// Complete or fail queue item
export const useCompleteQueueItem = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: {
      taskId: string;
      finalVault: string;
      finalStatus?: 'COMPLETED' | 'FAILED';
    }) => {
      // Minify the vault JSON before sending
      const minifiedData = {
        ...data,
        finalVault: minifyJSON(data.finalVault),
        finalStatus: data.finalStatus || 'COMPLETED', // Default to COMPLETED for backward compatibility
      };
      return api.queue.complete(
        minifiedData.taskId,
        minifiedData.finalVault,
        minifiedData.finalStatus
      );
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.queue.items() });
      const status = variables.finalStatus || 'COMPLETED';
      const message =
        status === 'FAILED'
          ? i18n.t('queue:success.markedFailed', { taskId: variables.taskId })
          : i18n.t('queue:success.completed', { taskId: variables.taskId });
      showMessage('success', message);
    },
    onError: createErrorHandler(i18n.t('queue:errors.updateFailed')),
  });
};

// Update queue item priority
export const useUpdateQueueItemPriority = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: { taskId: string; priority: number }) => {
      // Ensure priority is within valid range
      const priority = data.priority >= 1 && data.priority <= 5 ? data.priority : 3;
      return api.queue.updatePriority(data.taskId, priority);
    },
    onSuccess: (_, variables) => {
      invalidateAllQueueCaches(queryClient);
      showMessage(
        'success',
        i18n.t('queue:success.priorityUpdated', {
          taskId: variables.taskId,
          priority: variables.priority,
        })
      );
    },
    onError: createErrorHandler(i18n.t('queue:errors.updatePriorityFailed')),
  });
};

// Update queue item protection status
export const useUpdateQueueItemProtection = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: { taskId: string; protection: boolean }) => {
      return api.queue.updateProtection(data.taskId, data.protection);
    },
    onSuccess: (_, variables) => {
      invalidateAllQueueCaches(queryClient);
      const message = variables.protection
        ? i18n.t('queue:success.protectionEnabled', { taskId: variables.taskId })
        : i18n.t('queue:success.protectionDisabled', { taskId: variables.taskId });
      showMessage('success', message);
    },
    onError: createErrorHandler(i18n.t('queue:errors.updateProtectionFailed')),
  });
};

// Cancel queue item
export const useCancelQueueItem = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (taskId: string) => {
      return api.queue.cancel(taskId);
    },
    onSuccess: (_, taskId) => {
      invalidateAllQueueCaches(queryClient);
      showMessage('success', i18n.t('queue:success.cancellationInitiated', { taskId }));
    },
    onError: createErrorHandler(i18n.t('queue:errors.cancelFailed')),
  });
};

// Delete queue item
export const useDeleteQueueItem = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (taskId: string) => {
      return api.queue.delete(taskId);
    },
    onSuccess: (_, taskId) => {
      invalidateAllQueueCaches(queryClient);
      showMessage('success', i18n.t('queue:success.deleted', { taskId }));
    },
    onError: createErrorHandler(i18n.t('queue:errors.deleteFailed')),
  });
};

// Retry failed queue item
export const useRetryFailedQueueItem = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (taskId: string) => {
      return api.queue.retry(taskId);
    },
    onSuccess: (_, taskId) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.queue.items() });
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.queue.itemTrace(taskId) });
      showMessage('success', i18n.t('queue:success.queuedForRetry', { taskId }));
    },
    onError: createErrorHandler(i18n.t('queue:errors.retryFailed')),
  });
};

// Get queue item trace
export const useQueueItemTrace = (taskId: string | null, enabled: boolean = true) => {
  return useQuery<QueueTrace | null>({
    queryKey: QUERY_KEYS.queue.itemTrace(taskId),
    queryFn: async () => {
      if (!taskId) return null;
      const trace = await api.queue.getTrace(taskId);
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
