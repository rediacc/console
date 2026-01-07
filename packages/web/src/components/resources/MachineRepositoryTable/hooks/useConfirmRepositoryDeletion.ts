import { useState } from 'react';
import { createElement } from 'react';
import { prepareGrandDeletion } from '@/platform';
import { showMessage } from '@/utils/messages';
import type { TypedTFunction } from '@rediacc/shared/i18n/types';
import { BlockedDeletionContent, ConfirmDeletionContent } from './DeletionModalContent';
import type { Repository } from '../types';
import type { HookAPI } from 'antd/es/modal/useModal';

interface UseConfirmRepositoryDeletionParams {
  teamRepositories: {
    repositoryName: string;
    repositoryTag: string;
    repositoryGuid: string;
    grandGuid?: string;
    vaultContent?: string;
    repositoryNetworkId?: number;
  }[];
  modal: HookAPI;
  t: TypedTFunction;
  onConfirm: (context: ReturnType<typeof prepareGrandDeletion>) => Promise<void>;
}

export const useConfirmRepositoryDeletion = ({
  teamRepositories,
  modal,
  t,
  onConfirm,
}: UseConfirmRepositoryDeletionParams) => {
  const [isDeleting, setIsDeleting] = useState(false);

  const confirmDeletion = (repository: Repository): void => {
    const context = prepareGrandDeletion(
      repository.name,
      repository.repositoryTag,
      teamRepositories
    );

    if (context.status === 'error') {
      showMessage(
        'error',
        context.errorCode === 'NOT_FOUND'
          ? t('resources:repositories.notFound')
          : t('resources:repositories.notAGrandRepository')
      );
      return;
    }

    if (context.status === 'blocked') {
      modal.error({
        title: t('resources:repositories.cannotDeleteHasClones'),
        content: createElement(BlockedDeletionContent, {
          repositoryName: repository.name,
          childClones: context.childClones
            .filter((c) => c.repositoryGuid && c.repositoryName)
            .map((c) => ({
              repositoryGuid: c.repositoryGuid!,
              repositoryName: c.repositoryName!,
            })),
          t,
        }),
        okText: t('common:close'),
      });
      return;
    }

    let confirmationInput = '';

    modal.confirm({
      title: t('resources:repositories.deleteGrandConfirmTitle'),
      content: createElement(ConfirmDeletionContent, {
        repositoryName: repository.name,
        t,
        onInputChange: (value: string) => {
          confirmationInput = value;
        },
      }),
      okText: t('common:delete'),
      okType: 'danger',
      cancelText: t('common:cancel'),
      onOk: async () => {
        if (confirmationInput !== repository.name) {
          showMessage('error', t('resources:repositories.deleteGrandConfirmationMismatch'));
          throw new Error(t('resources:repositories.deleteGrandConfirmationMismatch'));
        }

        setIsDeleting(true);
        try {
          await onConfirm(context);
        } finally {
          setIsDeleting(false);
        }
      },
    });
  };

  return { confirmDeletion, isDeleting };
};
