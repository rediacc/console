import { type TFunction } from 'i18next';
import { getGrandVaultForOperation, prepareForkDeletion } from '@/platform';
import { showMessage } from '@/utils/messages';
import type { Repository } from '../types';
import type { HookAPI } from 'antd/es/modal/useModal';

interface UseConfirmForkDeletionParams {
  teamRepositories: {
    repositoryName: string;
    repositoryTag: string;
    repositoryGuid: string;
    grandGuid?: string;
    vaultContent?: string;
    repositoryNetworkId?: number;
    parentGuid?: string;
  }[];
  machine: {
    teamName: string;
    machineName: string;
    bridgeName: string;
    vaultContent?: string;
  };
  confirm: HookAPI['confirm'];
  executeAction: (params: unknown) => Promise<{
    success: boolean;
    taskId?: string;
    isQueued?: boolean;
    error?: string;
  }>;
  onQueueItemCreated?: (taskId: string, machineName: string) => void;
  t: TFunction;
}

export const useConfirmForkDeletion = ({
  teamRepositories,
  machine,
  confirm,
  executeAction,
  onQueueItemCreated,
  t,
}: UseConfirmForkDeletionParams) => {
  const confirmForkDeletion = (repository: Repository): void => {
    const context = prepareForkDeletion(
      repository.name,
      repository.repositoryTag,
      teamRepositories
    );

    if (context.status === 'error') {
      const errorKey =
        context.errorCode === 'NOT_FOUND'
          ? 'resources:repositories.RepoNotFound'
          : 'resources:repositories.cannotDeleteGrandRepo';
      showMessage('error', t(errorKey));
      return;
    }

    const parentName = context.parentName ?? repository.name;

    confirm({
      title: t('resources:repositories.deleteCloneConfirmTitle'),
      content: t('resources:repositories.deleteCloneConfirmMessage', {
        name: repository.name,
        tag: repository.repositoryTag ?? 'latest',
        parentName,
      }),
      okText: t('common:delete'),
      okType: 'danger',
      cancelText: t('common:cancel'),
      onOk: async () => {
        try {
          const grandRepoVault =
            getGrandVaultForOperation(
              context.repositoryGuid!,
              context.grandGuid,
              teamRepositories
            ) ?? '{}';

          const params: Record<string, unknown> = {
            repository: context.repositoryGuid,
            repositoryName: context.repositoryTag,
            grand: context.grandGuid,
          };

          const result = await executeAction({
            teamName: machine.teamName,
            machineName: machine.machineName,
            bridgeName: machine.bridgeName,
            functionName: 'rm',
            params,
            priority: 4,
            addedVia: 'machine-Repository-list-delete-clone',
            machineVault: machine.vaultContent ?? '{}',
            repositoryGuid: context.repositoryGuid,
            vaultContent: grandRepoVault,
            repositoryNetworkId: context.repositoryNetworkId,
          });

          if (result.success) {
            if (result.taskId) {
              showMessage(
                'success',
                t('resources:repositories.deleteCloneQueued', {
                  name: repository.name,
                  tag: repository.repositoryTag ?? 'latest',
                })
              );
              if (onQueueItemCreated) {
                onQueueItemCreated(result.taskId, machine.machineName);
              }
              showMessage('success', t('resources:repositories.deleteForkSuccess'));
              return;
            }
            if (result.isQueued) {
              showMessage('info', t('resources:repositories.highestPriorityQueued'));
              return;
            }
          }

          showMessage('error', result.error ?? t('resources:repositories.deleteCloneFailed'));
        } catch {
          showMessage('error', t('resources:repositories.deleteCloneFailed'));
        }
      },
    });
  };

  return { confirmForkDeletion };
};
