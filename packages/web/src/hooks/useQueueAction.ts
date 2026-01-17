import { useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useGetOrganizationTeams } from '@/api/api-hooks.generated';
import { useManagedQueueItem } from '@/hooks/useManagedQueueItem';
import { useQueueVaultBuilder } from '@/hooks/useQueueVaultBuilder';
import {
  type DynamicQueueActionParams,
  QueueActionResult,
  QueueActionService,
  type TypedQueueActionParams,
} from '@/services/queue';
import type { BridgeFunctionName } from '@rediacc/shared/queue-vault';

/**
 * Generic hook for executing queue actions
 * Handles vault assembly and queue item creation for any function
 */
export function useQueueAction() {
  const { i18n } = useTranslation();
  const { data: teams = [] } = useGetOrganizationTeams();
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

  /**
   * Internal execution handler for both typed and dynamic calls.
   * Automatically injects the current UI language for task output localization.
   */
  const executeInternal = useCallback(
    async (params: DynamicQueueActionParams): Promise<QueueActionResult> => {
      try {
        const team = teams.find((t) => t.teamName === params.teamName);
        const teamVault = params.teamVault ?? team?.vaultContent ?? '{}';
        // Inject current UI language for task output localization
        const paramsWithLanguage = { ...params, language: params.language ?? i18n.language };
        return await service.execute(paramsWithLanguage, teamVault);
      } catch (error) {
        console.error('Failed to execute queue action:', error);
        return {
          success: false,
          error: error instanceof Error ? error.message : 'Unknown error',
        };
      }
    },
    [service, teams, i18n.language]
  );

  /**
   * Type-safe queue action execution for specific functions.
   * Provides better IntelliSense and compile-time validation.
   *
   * @example
   * const { executeTyped } = useQueueAction();
   * await executeTyped('backup_create', {
   *   teamName: 'Production',
   *   machineName: 'server-01',
   *   bridgeName: 'bridge-01',
   *   params: { dest: 'backup.tar', storages: ['s3'] }, // Type-checked!
   *   priority: 1,
   *   addedVia: 'dashboard',
   *   machineVault: '{}',
   * });
   */
  const executeTyped = useCallback(
    async <F extends BridgeFunctionName>(
      functionName: F,
      params: Omit<TypedQueueActionParams<F>, 'functionName'>
    ): Promise<QueueActionResult> => {
      // Cast through unknown: typed params are structurally compatible with dynamic params
      return executeInternal({ ...params, functionName } as unknown as DynamicQueueActionParams);
    },
    [executeInternal]
  );

  /**
   * Execute a queue action with a validated function name but untyped params.
   * Use this for dynamic function names from trusted sources (e.g., database/API).
   *
   * @example
   * await executeDynamic(functionData.function.name as BridgeFunctionName, {
   *   params: functionData.params,
   *   teamName: 'Production',
   *   machineName: 'server-01',
   *   // ...
   * });
   */
  const executeDynamic = useCallback(
    async (
      functionName: BridgeFunctionName,
      params: Omit<DynamicQueueActionParams, 'functionName'>
    ): Promise<QueueActionResult> => {
      return executeInternal({ ...params, functionName });
    },
    [executeInternal]
  );

  return {
    executeTyped,
    executeDynamic,
    isExecuting: createQueueItemMutation.isPending,
  };
}
