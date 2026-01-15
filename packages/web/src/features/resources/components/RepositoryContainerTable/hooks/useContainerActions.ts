import type { TypedTFunction } from '@rediacc/shared/i18n/types';
import type { BridgeFunctionName } from '@rediacc/shared/queue-vault';
import { useCallback } from 'react';
import type { DynamicQueueActionParams, QueueActionResult } from '@/services/queue';
import { showMessage } from '@/utils/messages';
import type { Container, Repository } from '../types';

interface RepositoryData {
  repositoryGuid: string;
  repositoryName: string;
  repositoryTag?: string;
  repositoryNetworkId?: number;
  repositoryNetworkMode?: string;
}

interface UseContainerActionsProps {
  teamName: string;
  machineName: string;
  bridgeName: string;
  repository: Repository;
  repositoryData?: RepositoryData;
  grandRepoVault: string;
  machineVault: string;
  executeDynamic: (
    functionName: BridgeFunctionName,
    params: Omit<DynamicQueueActionParams, 'functionName'>
  ) => Promise<QueueActionResult>;
  onQueueItemCreated?: (taskId: string, machineName: string) => void;
  t: TypedTFunction;
}

export function useContainerActions({
  teamName,
  machineName,
  bridgeName,
  repository,
  repositoryData,
  grandRepoVault,
  machineVault,
  executeDynamic,
  onQueueItemCreated,
  t,
}: UseContainerActionsProps) {
  const handleContainerAction = useCallback(
    async (container: Container, functionName: string) => {
      const result = await executeDynamic(functionName as BridgeFunctionName, {
        params: {
          repository: repositoryData?.repositoryGuid ?? repository.name,
          repositoryName: repositoryData?.repositoryName ?? repository.name,
          container: container.id,
        },
        teamName,
        machineName,
        bridgeName,
        priority: 4,
        addedVia: 'container-action',
        machineVault,
        repositoryGuid: repositoryData?.repositoryGuid,
        vaultContent: grandRepoVault,
        repositoryNetworkId: repositoryData?.repositoryNetworkId,
        repositoryNetworkMode: repositoryData?.repositoryNetworkMode,
        repositoryTag: repositoryData?.repositoryTag,
      });

      if (result.success) {
        if (result.taskId) {
          showMessage('success', t('machines:queueItemCreated'));
          if (onQueueItemCreated) {
            onQueueItemCreated(result.taskId, machineName);
          }
        } else if (result.isQueued) {
          showMessage('info', t('resources:repositories.highestPriorityQueued'));
        }
      } else {
        showMessage('error', result.error ?? t('common:errors.somethingWentWrong'));
      }
    },
    [
      executeDynamic,
      teamName,
      machineName,
      bridgeName,
      repository.name,
      repositoryData,
      grandRepoVault,
      machineVault,
      t,
      onQueueItemCreated,
    ]
  );

  return { handleContainerAction };
}
