import { useState } from 'react';
import { Alert, Flex, Input, Typography } from 'antd';
import { type TFunction } from 'i18next';
import { prepareGrandDeletion } from '@/platform';
import { showMessage } from '@/utils/messages';
import type { Repository } from '../types';
import type { HookAPI } from 'antd/es/modal/useModal';

interface UseConfirmRepositoryDeletionParams {
  teamRepositories: Array<{
    repositoryName: string;
    repositoryTag: string;
    repositoryGuid: string;
    grandGuid?: string;
    vaultContent?: string;
    repositoryNetworkId?: number;
  }>;
  modal: HookAPI;
  t: TFunction;
  onConfirm: (context: ReturnType<typeof prepareGrandDeletion>) => Promise<void>;
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
          <Flex vertical>
            <Typography.Paragraph>
              {t('resources:repositories.hasActiveClonesMessage', {
                name: repository.name,
                count: context.childClones.length,
              })}
            </Typography.Paragraph>
            <Typography.Text strong style={{ display: 'block' }}>
              {t('resources:repositories.clonesList')}
            </Typography.Text>
            <ul>
              {context.childClones.map((clone) => (
                <li key={clone.repositoryGuid}>{clone.repositoryName}</li>
              ))}
            </ul>
            <Typography.Paragraph>
              {t('resources:repositories.deleteOptionsMessage')}
            </Typography.Paragraph>
          </Flex>
        ),
        okText: t('common:close'),
      });
      return;
    }

    let confirmationInput = '';

    modal.confirm({
      title: t('resources:repositories.deleteGrandConfirmTitle'),
      content: (
        <Flex vertical>
          <Alert
            message={t('resources:repositories.deleteGrandWarning')}
            description={t('resources:repositories.deleteGrandWarningDesc', {
              name: repository.name,
            })}
            type="warning"
            showIcon
          />
          <Typography.Text strong>
            {t('resources:repositories.deleteGrandConfirmPrompt', { name: repository.name })}
          </Typography.Text>
          <Input
            type="text"
            placeholder={repository.name}
            style={{ width: '100%' }}
            onChange={(e) => {
              confirmationInput = e.target.value;
            }}
          />
        </Flex>
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
