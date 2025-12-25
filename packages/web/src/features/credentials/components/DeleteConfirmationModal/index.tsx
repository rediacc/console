import { Alert, Flex, Modal, Typography } from 'antd';
import type { Repository } from '@/api/queries/repositories';
import { showMessage } from '@/utils/messages';
import { WarningOutlined } from '@/utils/optimizedIcons';
import type { TFunction } from 'i18next';

interface AffectedResources {
  isCredential: boolean;
  forks: {
    repositoryGuid: string;
    repositoryName: string;
    repositoryTag?: string | null;
  }[];
  affectedMachines: { machineName: string; repositoryNames: string[] }[];
}

interface DeleteConfirmationModalParams {
  t: TFunction<'resources' | 'machines' | 'common'>;
  getAffectedResources: (repository: Repository) => AffectedResources;
  onDelete: (repository: Repository) => Promise<unknown>;
  onDeleted: () => void;
}

export const useDeleteConfirmationModal = ({
  t,
  getAffectedResources,
  onDelete,
  onDeleted,
}: DeleteConfirmationModalParams) => {
  const [modal, contextHolder] = Modal.useModal();

  const handleDeleteRepository = (repository: Repository) => {
    const { isCredential, forks, affectedMachines } = getAffectedResources(repository);

    if (isCredential && affectedMachines.length > 0) {
      modal.error({
        title: t('repositories.cannotDeleteCredential'),
        content: (
          <Flex vertical>
            <Typography.Text>
              {forks.length > 0
                ? t('repositories.credentialHasDeploymentsWithForks', {
                    count: affectedMachines.length,
                    forkCount: forks.length,
                  })
                : t('repositories.credentialHasDeployments', {
                    count: affectedMachines.length,
                  })}
            </Typography.Text>

            {forks.length > 0 && (
              <Flex vertical>
                <Typography.Text strong>{t('repositories.affectedForks')}</Typography.Text>
                {/* eslint-disable-next-line no-restricted-syntax */}
                <ul style={{ paddingLeft: 24 }}>
                  {forks.map((fork) => (
                    <li key={fork.repositoryGuid}>
                      {fork.repositoryName}
                      {fork.repositoryTag ? `:${fork.repositoryTag}` : ''}
                    </li>
                  ))}
                </ul>
              </Flex>
            )}

            <Flex vertical>
              <Typography.Text strong>{t('repositories.affectedMachines')}</Typography.Text>
              {/* eslint-disable-next-line no-restricted-syntax */}
              <ul style={{ paddingLeft: 24 }}>
                {affectedMachines.map((machine) => (
                  <li key={machine.machineName}>
                    <Typography.Text strong>{machine.machineName}</Typography.Text>
                    <Typography.Text> ({machine.repositoryNames.join(', ')})</Typography.Text>
                  </li>
                ))}
              </ul>
            </Flex>

            <Alert
              type="warning"
              message={t('repositories.removeDeploymentsFirst')}
              showIcon
              icon={<WarningOutlined />}
            />
          </Flex>
        ),
        okText: t('common:actions.close'),
      });
      return;
    }

    const confirmDelete = async () => {
      try {
        await onDelete(repository);
        showMessage('success', t('repositories.deleteSuccess'));
        onDeleted();
      } catch {
        showMessage('error', t('repositories.deleteError'));
      }
    };

    if (!isCredential && affectedMachines.length > 0) {
      modal.confirm({
        title: t('repositories.deleteRepository'),
        content: (
          <Flex vertical>
            <Typography.Text>
              {t('repositories.confirmDelete', { repositoryName: repository.repositoryName })}
            </Typography.Text>

            <Alert
              type="warning"
              message={t('repositories.machinesWillLoseAccess')}
              description={
                // eslint-disable-next-line no-restricted-syntax
                <ul style={{ paddingLeft: 24 }}>
                  {affectedMachines.map((machine) => (
                    <li key={machine.machineName}>
                      <Typography.Text strong>{machine.machineName}</Typography.Text>
                    </li>
                  ))}
                </ul>
              }
              showIcon
              icon={<WarningOutlined />}
            />
          </Flex>
        ),
        okText: t('common:actions.delete'),
        okType: 'danger',
        cancelText: t('common:actions.cancel'),
        onOk: confirmDelete,
      });
      return;
    }

    modal.confirm({
      title: isCredential ? t('repositories.deleteCredential') : t('repositories.deleteRepository'),
      content: isCredential
        ? t('repositories.confirmDeleteCredential', { repositoryName: repository.repositoryName })
        : t('repositories.confirmDelete', { repositoryName: repository.repositoryName }),
      okText: t('common:actions.delete'),
      okType: 'danger',
      cancelText: t('common:actions.cancel'),
      onOk: confirmDelete,
    });
  };

  return { handleDeleteRepository, contextHolder };
};
