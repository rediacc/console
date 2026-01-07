import { useCallback } from 'react';
import { FUNCTION_DEFINITIONS } from '@/services/functionsService';
import type { DynamicQueueActionParams, QueueActionResult } from '@/services/queue';
import type { Machine } from '@/types';
import { showMessage } from '@/utils/messages';
import type { TypedTFunction } from '@rediacc/shared/i18n/types';
import { isBridgeFunction, type BridgeFunctionName } from '@rediacc/shared/queue-vault';
import type { MachineFunctionData } from '../types';

interface UseMachineFunctionHandlersProps {
  currentResource: Machine | null;
  teams: { teamName: string; vaultContent?: string | null }[];
  machines: Machine[];
  repositories: { repositoryGuid: string; vaultContent?: string | null }[];
  storages: { storageName: string; vaultContent?: string | null }[];
  executeDynamic: (
    functionName: BridgeFunctionName,
    params: Omit<DynamicQueueActionParams, 'functionName'>
  ) => Promise<QueueActionResult>;
  closeUnifiedModal: () => void;
  openQueueTrace: (taskId: string, machineName: string) => void;
  setRefreshKeys: React.Dispatch<React.SetStateAction<Record<string, number>>>;
  t: TypedTFunction;
}

export function useMachineFunctionHandlers({
  currentResource,
  teams,
  machines,
  repositories,
  storages,
  executeDynamic,
  closeUnifiedModal,
  openQueueTrace,
  setRefreshKeys,
  t,
}: UseMachineFunctionHandlersProps) {
  const handleMachineFunctionSelected = useCallback(
    async (functionData: MachineFunctionData) => {
      if (!currentResource) return;

      try {
        const machineName = currentResource.machineName;
        const bridgeName = currentResource.bridgeName;
        const teamData = teams.find((team) => team.teamName === currentResource.teamName);
        const repositoryParam =
          typeof functionData.params.repository === 'string'
            ? functionData.params.repository
            : undefined;

        const queuePayload: Omit<DynamicQueueActionParams, 'functionName'> = {
          params: functionData.params,
          teamName: currentResource.teamName ?? '',
          machineName: machineName ?? '',
          bridgeName: bridgeName ?? '',
          priority: functionData.priority,
          addedVia: 'machine-table',
          teamVault: teamData?.vaultContent ?? '{}',
          machineVault: currentResource.vaultContent ?? '{}',
          vaultContent: '{}',
        };

        if (repositoryParam) {
          const repository = repositories.find((item) => item.repositoryGuid === repositoryParam);
          queuePayload.repositoryGuid = repository?.repositoryGuid ?? repositoryParam;
          queuePayload.vaultContent = repository?.vaultContent ?? '{}';
        }

        if (functionData.function.name === 'backup_pull') {
          const sourceType =
            typeof functionData.params.sourceType === 'string'
              ? functionData.params.sourceType
              : undefined;
          const sourceIdentifier =
            typeof functionData.params.from === 'string' ? functionData.params.from : undefined;

          if (sourceType === 'machine' && sourceIdentifier) {
            const sourceMachine = machines.find(
              (machine) => machine.machineName === sourceIdentifier
            );
            if (sourceMachine?.vaultContent) {
              queuePayload.sourceMachineVault = sourceMachine.vaultContent;
            }
          }

          if (sourceType === 'storage' && sourceIdentifier) {
            const sourceStorage = storages.find(
              (storage) => storage.storageName === sourceIdentifier
            );
            if (sourceStorage?.vaultContent) {
              queuePayload.sourceStorageVault = sourceStorage.vaultContent;
            }
          }
        }

        const result = await executeDynamic(
          functionData.function.name as BridgeFunctionName,
          queuePayload
        );
        closeUnifiedModal();

        if (result.success) {
          if (result.taskId) {
            showMessage('success', t('machines:queueItemCreated'));
            openQueueTrace(result.taskId, machineName ?? '');
          } else if (result.isQueued) {
            showMessage(
              'info',
              t('resources:messages.highestPriorityQueued', { resourceType: 'machine' })
            );
          }
        } else {
          showMessage('error', result.error ?? t('resources:errors.failedToCreateQueueItem'));
        }
      } catch {
        showMessage('error', t('resources:errors.failedToCreateQueueItem'));
      }
    },
    [
      closeUnifiedModal,
      currentResource,
      executeDynamic,
      machines,
      openQueueTrace,
      repositories,
      storages,
      t,
      teams,
    ]
  );

  const handleDirectFunctionQueue = useCallback(
    async (machine: Machine, functionName: string) => {
      if (!isBridgeFunction(functionName)) {
        showMessage('error', t('resources:errors.functionNotFound'));
        return;
      }
      const funcDef = FUNCTION_DEFINITIONS[functionName];

      // Build default params from function definition
      const defaultParams: Record<string, string> = {};
      Object.entries(funcDef.params).forEach(([paramName, paramInfo]) => {
        if (paramInfo.default) {
          defaultParams[paramName] = paramInfo.default;
        }
      });

      const teamData = teams.find((team) => team.teamName === machine.teamName);

      const queuePayload: Omit<DynamicQueueActionParams, 'functionName'> = {
        params: defaultParams,
        teamName: machine.teamName ?? '',
        machineName: machine.machineName ?? '',
        bridgeName: machine.bridgeName ?? '',
        priority: 4, // Normal priority
        addedVia: 'machine-table-quick',
        teamVault: teamData?.vaultContent ?? '{}',
        machineVault: machine.vaultContent ?? '{}',
        vaultContent: '{}',
      };

      try {
        const result = await executeDynamic(functionName, queuePayload);

        if (result.success) {
          if (result.taskId) {
            showMessage('success', t('machines:queueItemCreated'));
            openQueueTrace(result.taskId, machine.machineName ?? '');
          } else if (result.isQueued) {
            showMessage(
              'info',
              t('resources:messages.highestPriorityQueued', { resourceType: 'machine' })
            );
          }
        } else {
          showMessage('error', result.error ?? t('resources:errors.failedToCreateQueueItem'));
        }

        setRefreshKeys((prev) => ({
          ...prev,
          [machine.machineName ?? '']: Date.now(),
        }));
      } catch {
        showMessage('error', t('resources:errors.failedToCreateQueueItem'));
      }
    },
    [executeDynamic, openQueueTrace, setRefreshKeys, t, teams]
  );

  return {
    handleMachineFunctionSelected,
    handleDirectFunctionQueue,
  };
}
