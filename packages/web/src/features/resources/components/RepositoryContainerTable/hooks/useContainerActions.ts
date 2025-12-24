import { useCallback } from 'react';
import { showMessage } from '@/utils/messages';
import type { Container, Repository } from '../types';
import type { TFunction } from 'i18next';

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
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  executeAction: (params: any) => Promise<{ success: boolean; taskId?: string; isQueued?: boolean; error?: string }>;
  onQueueItemCreated?: (taskId: string, machineName: string) => void;
  t: TFunction;
}

export function useContainerActions({
  teamName,
  machineName,
  bridgeName,
  repository,
  repositoryData,
  grandRepoVault,
  machineVault,
  executeAction,
  onQueueItemCreated,
  t,
}: UseContainerActionsProps) {
  const handleContainerAction = useCallback(
    async (container: Container, functionName: string) => {
      const result = await executeAction({
        teamName,
        machineName,
        bridgeName,
        functionName,
        params: {
          repository: repositoryData?.repositoryGuid || repository.name,
          repositoryName: repositoryData?.repositoryName || repository.name,
          container: container.id,
        },
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
        showMessage('error', result.error || t('common:errors.somethingWentWrong'));
      }
    },
    [
      executeAction,
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
