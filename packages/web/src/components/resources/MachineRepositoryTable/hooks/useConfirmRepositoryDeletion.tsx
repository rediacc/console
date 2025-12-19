import { useState } from 'react';
import { Typography } from 'antd';
import { Alert } from 'antd';
import { type TFunction } from 'i18next';
import { RediaccText } from '@/components/ui';
import { prepareGrandDeletion } from '@/platform';
import { showMessage } from '@/utils/messages';
import { ConfirmationInput, ModalContent } from '../styledComponents';
import type { Repository } from '../types';
import type { HookAPI } from 'antd/es/modal/useModal';

interface UseConfirmRepositoryDeletionParams {
  teamRepositories: Array<{
    repositoryName: string;
    repositoryTag: string;
    repositoryGuid: string;
    grandGuid?: string;
    vaultContent?: string;
    repositoryNetworkId?: string;
  }>;
  modal: HookAPI;
  t: TFunction;
  onConfirm: (context: ReturnType<typeof prepareGrandDeletion> & { status: 'ready' }) => Promise<void>;
}

export const useConfirmRepositoryDeletion = ({
  teamRepositories,
  modal,
  t,
  onConfirm,
}: UseConfirmRepositoryDeletionParams) => {
  const [isDeleting, setIsDeleting] = useState(false);

  const confirmDeletion = async (repository: Repository): Promise<void> => {
    const context = prepareGrandDeletion(
      repository.name,
      repository.repositoryTag,
      teamRepositories
    );

    if (context.status === 'error') {
      const errorKey =
        context.errorCode === 'NOT_FOUND'
          ? 'resources:repositories.RepoNotFound'
          : 'resources:repositories.notAGrandRepo';
      showMessage('error', t(errorKey));
      return;
    }

    if (context.status === 'blocked') {
      modal.error({
        title: t('resources:repositories.cannotDeleteHasClones'),
        content: (
          <div>
            <Typography.Paragraph>
              {t('resources:repositories.hasActiveClonesMessage', {
                name: repository.name,
                count: context.childClones.length,
              })}
            </Typography.Paragraph>
            <RediaccText as="p" weight="bold">
              {t('resources:repositories.clonesList')}
            </RediaccText>
            <ul>
              {context.childClones.map((clone) => (
                <li key={clone.repositoryGuid}>{clone.repositoryName}</li>
              ))}
            </ul>
            <Typography.Paragraph>
              {t('resources:repositories.deleteOptionsMessage')}
            </Typography.Paragraph>
          </div>
        ),
        okText: t('common:close'),
      });
      return;
    }

    let confirmationInput = '';

    modal.confirm({
      title: t('resources:repositories.deleteGrandConfirmTitle'),
      content: (
        <ModalContent>
          <Alert
            message={t('resources:repositories.deleteGrandWarning')}
            description={t('resources:repositories.deleteGrandWarningDesc', {
              name: repository.name,
            })}
            type="warning"
            showIcon
          />
          <RediaccText weight="bold">
            {t('resources:repositories.deleteGrandConfirmPrompt', { name: repository.name })}
          </RediaccText>
          <ConfirmationInput
            type="text"
            placeholder={repository.name}
            onChange={(e) => {
              confirmationInput = e.target.value;
            }}
          />
        </ModalContent>
      ),
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
