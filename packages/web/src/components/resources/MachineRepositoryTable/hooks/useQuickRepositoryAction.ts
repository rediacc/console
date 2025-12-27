import { type TFunction } from 'i18next';
import { getGrandVaultForOperation } from '@/platform';
import { showMessage } from '@/utils/messages';
import type { Repository } from '../types';

interface UseQuickRepositoryActionParams {
  teamRepositories: {
    repositoryName: string;
    repositoryTag: string;
    repositoryGuid: string;
    vaultContent?: string;
    grandGuid?: string;
    repositoryNetworkId?: number;
    repositoryNetworkMode?: string;
  }[];
  machine: {
    teamName: string;
    machineName: string;
    bridgeName: string;
    vaultContent?: string;
  };
  executeAction: (params: unknown) => Promise<{
    success: boolean;
    taskId?: string;
    isQueued?: boolean;
    error?: string;
  }>;
  onQueueItemCreated?: (taskId: string, machineName: string) => void;
  t: TFunction;
}

export const useQuickRepositoryAction = ({
  teamRepositories,
  machine,
  executeAction,
  onQueueItemCreated,
  t,
}: UseQuickRepositoryActionParams) => {
  const executeQuickAction = async (
    repository: Repository,
    functionName: string,
    priority = 4,
    option?: string
  ): Promise<void> => {
    const repoData = teamRepositories.find(
      (r) => r.repositoryName === repository.name && r.repositoryTag === repository.repositoryTag
    );

    if (!repoData?.vaultContent) {
      showMessage(
        'error',
        t('resources:repositories.noCredentialsFound', { name: repository.name })
      );
      return;
    }

    const grandRepoVault =
      getGrandVaultForOperation(repoData.repositoryGuid, repoData.grandGuid, teamRepositories) ??
      repoData.vaultContent;

    const params: Record<string, unknown> = {
      repository: repoData.repositoryGuid,
      repositoryName: repoData.repositoryName,
      grand: repoData.grandGuid ?? '',
    };

    if (option) {
      params.option = option;
    }

    const result = await executeAction({
      teamName: machine.teamName,
      machineName: machine.machineName,
      bridgeName: machine.bridgeName,
      functionName,
      params,
      priority,
      addedVia: 'machine-Repository-list-quick',
      machineVault: machine.vaultContent ?? '{}',
      repositoryGuid: repoData.repositoryGuid,
      vaultContent: grandRepoVault,
      repositoryNetworkId: repoData.repositoryNetworkId,
      repositoryNetworkMode: repoData.repositoryNetworkMode,
      repositoryTag: repoData.repositoryTag,
    });

    if (result.success) {
      if (result.taskId) {
        showMessage('success', t('resources:repositories.queueItemCreated'));
        if (onQueueItemCreated) {
          onQueueItemCreated(result.taskId, machine.machineName);
        }
        return;
      }
      if (result.isQueued) {
        showMessage('info', t('resources:repositories.highestPriorityQueued'));
        return;
      }
    }

    showMessage('error', result.error ?? t('resources:repositories.failedToCreateQueueItem'));
  };

  return { executeQuickAction };
};
