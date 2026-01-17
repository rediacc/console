/**
 * Queue Domain Hooks
 *
 * Thin wrappers around generated hooks that provide:
 * - Filter object transformation
 * - Priority validation
 * - Custom cache invalidation patterns
 */

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { typedApi } from '@/api/client';
import { useMutationWithFeedback } from '@/hooks/useMutationWithFeedback';
import i18n from '@/i18n/config';
import { minifyJSON } from '@/platform/utils/json';
import { invalidateAllQueueCaches } from '@/utils/cacheUtils';
import {
  parseCreateQueueItem,
  parseGetQueueItemTrace,
  type QueueCreateResult,
} from '@rediacc/shared/api/parsers/queue';
import type {
  CancelQueueItemParams,
  CreateQueueItemParams,
  QueueFilters,
  QueueTrace,
  RetryFailedQueueItemParams,
} from '@rediacc/shared/types';
import { useGetTeamQueueItems } from './api-hooks.generated';

/**
 * Query queue items with a filter object.
 * Wraps useGetTeamQueueItems to accept a single filter object instead of individual params.
 */
export const useQueueItemsWithFilters = (filters: QueueFilters = {}) => {
  const {
    teamName,
    machineName,
    bridgeName,
    status,
    priority,
    minPriority,
    maxPriority,
    dateFrom,
    dateTo,
    taskId,
    includeCompleted,
    includeCancelled,
    onlyStale,
    staleThresholdMinutes,
    maxRecords,
    createdByUserEmail,
  } = filters;

  return useGetTeamQueueItems(
    teamName,
    machineName,
    bridgeName,
    status,
    priority,
    minPriority,
    maxPriority,
    dateFrom,
    dateTo,
    taskId,
    includeCompleted,
    includeCancelled,
    onlyStale,
    staleThresholdMinutes,
    maxRecords,
    createdByUserEmail
  );
};

/**
 * Create a queue item with priority validation and JSON minification.
 */
export const useCreateQueueItemWithValidation = () => {
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
      const priority =
        data.priority && data.priority >= 1 && data.priority <= 5 ? data.priority : 3;
      const params: CreateQueueItemParams = {
        teamName: data.teamName,
        machineName: data.machineName ?? '',
        bridgeName: data.bridgeName,
        vaultContent: minifyJSON(data.queueVault),
        priority,
      };
      const response = await typedApi.CreateQueueItem(params);
      return parseCreateQueueItem(response as never);
    },
    successMessage: i18n.t('queue:success.created'),
    errorMessage: i18n.t('queue:errors.createFailed'),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['queue', 'items'] });
    },
  });
};

/**
 * Cancel a queue item with full cache invalidation.
 */
export const useCancelQueueItemWithInvalidation = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, CancelQueueItemParams>({
    mutationFn: async (params) => {
      return typedApi.CancelQueueItem(params);
    },
    successMessage: (_, params) =>
      i18n.t('queue:success.cancellationInitiated', { taskId: params.taskId }),
    errorMessage: i18n.t('queue:errors.cancelFailed'),
    onSuccess: () => {
      invalidateAllQueueCaches(queryClient);
    },
  });
};

/**
 * Retry a failed queue item with full cache invalidation.
 */
export const useRetryQueueItemWithInvalidation = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, RetryFailedQueueItemParams>({
    mutationFn: async (params) => {
      return typedApi.RetryFailedQueueItem(params);
    },
    successMessage: (_, params) =>
      i18n.t('queue:success.queuedForRetry', { taskId: params.taskId }),
    errorMessage: i18n.t('queue:errors.retryFailed'),
    onSuccess: () => {
      invalidateAllQueueCaches(queryClient);
    },
  });
};

/**
 * Query queue item trace with enabled option.
 * Wraps useQueueItemTrace to support conditional fetching.
 */
export const useQueueItemTraceWithEnabled = (taskId: string | null, enabled = true) => {
  return useQuery<QueueTrace>({
    queryKey: ['queue', 'trace', taskId ?? ''],
    queryFn: async () => {
      const response = await typedApi.GetQueueItemTrace({ taskId: taskId! });
      return parseGetQueueItemTrace(response as never);
    },
    enabled: enabled && !!taskId,
    staleTime: 5000,
    refetchInterval: 5000,
  });
};
