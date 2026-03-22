import { DEFAULTS } from '@rediacc/shared/config';
import type { TypedTFunction } from '@rediacc/shared/i18n/types';
import type { BridgeFunctionName } from '@rediacc/shared/queue-vault';
import type { HookAPI } from 'antd/es/modal/useModal';
import { getGrandVaultForOperation, prepareForkDeletion } from '@/platform';
import { type QueueActionResult, type TypedQueueActionParams } from '@/services/queue';
import { showMessage } from '@/utils/messages';
import type { Repository } from '../types';

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
  executeTyped: <F extends BridgeFunctionName>(
    functionName: F,
    params: Omit<TypedQueueActionParams<F>, 'functionName'>
  ) => Promise<QueueActionResult>;
  onQueueItemCreated?: (taskId: string, machineName: string) => void;
  t: TypedTFunction;
}

export const useConfirmForkDeletion = ({
  teamRepositories,
  machine,
  confirm,
  executeTyped,
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
      showMessage(
        'error',
        context.errorCode === 'NOT_FOUND'
          ? t('resources:repositories.notFound')
          : t('resources:repositories.cannotDeleteGrandRepository')
      );
      return;
    }

    const parentName = context.parentName ?? repository.name;

    confirm({
      title: t('resources:repositories.deleteCloneConfirmTitle'),
      content: t('resources:repositories.deleteCloneConfirmMessage', {
        name: repository.name,
        tag: repository.repositoryTag ?? DEFAULTS.REPOSITORY.TAG,
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

          const result = await executeTyped('repository_delete', {
            params: {
              grand: context.grandGuid ?? undefined,
            },
            teamName: machine.teamName,
            machineName: machine.machineName,
            bridgeName: machine.bridgeName,
            priority: 4,
            addedVia: 'machine-Repository-list-delete-clone',
            machineVault: machine.vaultContent ?? '{}',
            repositoryGuid: context.repositoryGuid ?? undefined,
            vaultContent: grandRepoVault,
            repositoryNetworkId: context.repositoryNetworkId ?? undefined,
          });

          if (result.success) {
            if (result.taskId) {
              showMessage(
                'success',
                t('resources:repositories.deleteCloneQueued', {
                  name: repository.name,
                  tag: repository.repositoryTag ?? DEFAULTS.REPOSITORY.TAG,
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
