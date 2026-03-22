import type { TypedTFunction } from '@rediacc/shared/i18n/types';
import type { GetTeamRepositories_ResultSet1 } from '@rediacc/shared/types';
import { Alert, Flex, Modal, Typography } from 'antd';
import { showMessage } from '@/utils/messages';
import { WarningOutlined } from '@/utils/optimizedIcons';

interface AffectedResources {
  isCredential: boolean;
  forks: {
    repositoryGuid: string | null;
    repositoryName: string | null;
    repositoryTag?: string | null;
  }[];
  affectedMachines: { machineName: string | null; repositoryNames: string[] }[];
}

interface DeleteConfirmationModalParams {
  t: TypedTFunction;
  getAffectedResources: (repository: GetTeamRepositories_ResultSet1) => AffectedResources;
  onDelete: (repository: GetTeamRepositories_ResultSet1) => Promise<unknown>;
  onDeleted: () => void;
}

export const useDeleteConfirmationModal = ({
  t,
  getAffectedResources,
  onDelete,
  onDeleted,
}: DeleteConfirmationModalParams) => {
  const [modal, contextHolder] = Modal.useModal();

  const handleDeleteRepository = (repository: GetTeamRepositories_ResultSet1) => {
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
                <ul className="pl-6">
                  {forks.map((fork) => (
                    <li key={fork.repositoryGuid ?? ''}>
                      {fork.repositoryName ?? ''}
                      {fork.repositoryTag ? `:${fork.repositoryTag}` : ''}
                    </li>
                  ))}
                </ul>
              </Flex>
            )}

            <Flex vertical>
              <Typography.Text strong>{t('repositories.affectedMachines')}</Typography.Text>
              <ul className="pl-6">
                {affectedMachines.map((machine) => (
                  <li key={machine.machineName ?? ''}>
                    <Typography.Text strong>{machine.machineName ?? ''}</Typography.Text>
                    <Typography.Text> ({machine.repositoryNames.join(', ')})</Typography.Text>
                  </li>
                ))}
              </ul>
            </Flex>

            <Alert
              type="warning"
              message={t('repositories.removeDeploymentsFirst')}
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
                <ul className="pl-6">
                  {affectedMachines.map((machine) => (
                    <li key={machine.machineName ?? ''}>
                      <Typography.Text strong>{machine.machineName ?? ''}</Typography.Text>
                    </li>
                  ))}
                </ul>
              }
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
