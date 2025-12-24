import { useCallback } from 'react';
import { FUNCTION_DEFINITIONS } from '@/services/functionsService';
import type { QueueActionParams } from '@/services/queue';
import type { Machine } from '@/types';
import { showMessage } from '@/utils/messages';
import type { MachineFunctionData } from '../types';
import type { TFunction } from 'i18next';

interface UseMachineFunctionHandlersProps {
  currentResource: Machine | null;
  teams: Array<{ teamName: string; vaultContent?: string }>;
  machines: Machine[];
  repositories: Array<{ repositoryGuid: string; vaultContent?: string }>;
  storages: Array<{ storageName: string; vaultContent?: string }>;
  executeAction: (params: QueueActionParams) => Promise<{
    success: boolean;
    taskId?: string;
    isQueued?: boolean;
    error?: string;
  }>;
  closeUnifiedModal: () => void;
  openQueueTrace: (taskId: string, machineName: string) => void;
  setRefreshKeys: React.Dispatch<React.SetStateAction<Record<string, number>>>;
  t: TFunction;
}

export function useMachineFunctionHandlers({
  currentResource,
  teams,
  machines,
  repositories,
  storages,
  executeAction,
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

        const queuePayload: QueueActionParams = {
          teamName: currentResource.teamName,
          machineName,
          bridgeName,
          functionName: functionData.function.name,
          params: functionData.params,
          priority: functionData.priority,
          addedVia: 'machine-table',
          teamVault: teamData?.vaultContent || '{}',
          machineVault: currentResource.vaultContent || '{}',
          vaultContent: '{}',
        };

        if (repositoryParam) {
          const repository = repositories.find((item) => item.repositoryGuid === repositoryParam);
          queuePayload.repositoryGuid = repository?.repositoryGuid || repositoryParam;
          queuePayload.vaultContent = repository?.vaultContent || '{}';
        }

        if (functionData.function.name === 'pull') {
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

        const result = await executeAction(queuePayload);
        closeUnifiedModal();

        if (result.success) {
          if (result.taskId) {
            showMessage('success', t('machines:queueItemCreated'));
            openQueueTrace(result.taskId, machineName);
          } else if (result.isQueued) {
            showMessage(
              'info',
              t('resources:messages.highestPriorityQueued', { resourceType: 'machine' })
            );
          }
        } else {
          showMessage('error', result.error || t('resources:errors.failedToCreateQueueItem'));
        }
      } catch {
        showMessage('error', t('resources:errors.failedToCreateQueueItem'));
      }
    },
    [
      closeUnifiedModal,
      currentResource,
      executeAction,
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
      const funcDef = FUNCTION_DEFINITIONS[functionName];
      if (!funcDef) {
        showMessage('error', t('resources:errors.functionNotFound'));
        return;
      }

      // Build default params from function definition
      const defaultParams: Record<string, string> = {};
      if (funcDef.params) {
        Object.entries(funcDef.params).forEach(([paramName, paramInfo]) => {
          if (paramInfo.default) {
            defaultParams[paramName] = paramInfo.default;
          }
        });
      }

      const teamData = teams.find((team) => team.teamName === machine.teamName);

      const queuePayload: QueueActionParams = {
        teamName: machine.teamName,
        machineName: machine.machineName,
        bridgeName: machine.bridgeName,
        functionName,
        params: defaultParams,
        priority: 4, // Normal priority
        addedVia: 'machine-table-quick',
        teamVault: teamData?.vaultContent || '{}',
        machineVault: machine.vaultContent || '{}',
        vaultContent: '{}',
      };

      try {
        const result = await executeAction(queuePayload);

        if (result.success) {
          if (result.taskId) {
            showMessage('success', t('machines:queueItemCreated'));
            openQueueTrace(result.taskId, machine.machineName);
          } else if (result.isQueued) {
            showMessage(
              'info',
              t('resources:messages.highestPriorityQueued', { resourceType: 'machine' })
            );
          }
        } else {
          showMessage('error', result.error || t('resources:errors.failedToCreateQueueItem'));
        }

        setRefreshKeys((prev) => ({
          ...prev,
          [machine.machineName]: Date.now(),
        }));
      } catch {
        showMessage('error', t('resources:errors.failedToCreateQueueItem'));
      }
    },
    [executeAction, openQueueTrace, setRefreshKeys, t, teams]
  );

  return {
    handleMachineFunctionSelected,
    handleDirectFunctionQueue,
  };
}
