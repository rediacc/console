import { getGrandVaultForOperation } from '@/platform';
import { type DynamicQueueActionParams, type QueueActionResult } from '@/services/queue';
import { showMessage } from '@/utils/messages';
import type { TypedTFunction } from '@rediacc/shared/i18n/types';
import type { BridgeFunctionName } from '@rediacc/shared/queue-vault';
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
  executeDynamic: (
    functionName: BridgeFunctionName,
    params: Omit<DynamicQueueActionParams, 'functionName'>
  ) => Promise<QueueActionResult>;
  onQueueItemCreated?: (taskId: string, machineName: string) => void;
  t: TypedTFunction;
}

export const useQuickRepositoryAction = ({
  teamRepositories,
  machine,
  executeDynamic,
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

    const result = await executeDynamic(functionName as BridgeFunctionName, {
      params,
      teamName: machine.teamName,
      machineName: machine.machineName,
      bridgeName: machine.bridgeName,
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
