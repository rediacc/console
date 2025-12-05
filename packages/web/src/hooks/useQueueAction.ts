import { useMemo, useCallback } from 'react';
import { useTeams } from '@/api/queries/teams';
import { useManagedQueueItem } from '@/hooks/useManagedQueueItem';
import { useQueueVaultBuilder } from '@/hooks/useQueueVaultBuilder';
import {
  QueueActionService,
  QueueActionParams,
  QueueActionResult,
} from '@/services/queueActionService';

export type { QueueActionParams, QueueActionResult } from '@/services/queueActionService';

/**
 * Generic hook for executing queue actions
 * Handles vault assembly and queue item creation for any function
 */
export function useQueueAction() {
  const { data: teams = [] } = useTeams();
  const { buildQueueVault } = useQueueVaultBuilder();
  const createQueueItemMutation = useManagedQueueItem();

  const service = useMemo(
    () =>
      new QueueActionService({
        buildQueueVault,
        createQueueItem: (data) => createQueueItemMutation.mutateAsync(data),
      }),
    [buildQueueVault, createQueueItemMutation]
  );

  const executeAction = useCallback(
    async (params: QueueActionParams): Promise<QueueActionResult> => {
      try {
        const team = teams.find((t) => t.teamName === params.teamName);
        const teamVault = params.teamVault || team?.vaultContent || '{}';
        return await service.execute(params, teamVault);
      } catch (error) {
        console.error('Failed to execute queue action:', error);
        return {
          success: false,
          error: error instanceof Error ? error.message : 'Unknown error',
        };
      }
    },
    [service, teams]
  );

  return {
    executeAction,
    isExecuting: createQueueItemMutation.isPending,
  };
}
