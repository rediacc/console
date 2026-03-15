import type { TypedTFunction } from '@rediacc/shared/i18n/types';
import type { GetTeamRepositories_ResultSet1 } from '@rediacc/shared/types';
import { Alert, Empty, Flex, Space, Tag } from 'antd';
import React, { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useGetTeamMachines } from '@/api/api-hooks.generated';
import {
  DetailPanelBody,
  DetailPanelDivider,
  DetailPanelFieldLabel,
  DetailPanelFieldMonospaceValue,
  DetailPanelFieldRow,
  DetailPanelFieldValue,
  DetailPanelSectionCard,
  DetailPanelSectionHeader,
  DetailPanelSectionTitle,
  DetailPanelSurface,
} from '@/components/resources/internal/detailPanelPrimitives';
import {
  CheckCircleOutlined,
  FieldTimeOutlined,
  FolderOutlined,
  StopOutlined,
  WarningOutlined,
} from '@/utils/optimizedIcons';
import { abbreviatePath } from '@/utils/pathUtils';
import { useRepositoryVaultData } from './hooks/useRepositoryVaultData';
import { ServicesSection } from './sections/ServicesSection';
import { StorageSection } from './sections/StorageSection';
import type { RepositoryPanelData } from './types';

interface RepositoryDetailPanelProps {
  repository: GetTeamRepositories_ResultSet1 | null;
  visible: boolean;
  onClose: () => void;
  splitView?: boolean;
}

export const RepositoryDetailPanel: React.FC<RepositoryDetailPanelProps> = ({
  repository,
  visible,
  onClose,
  splitView = false,
}) => {
  const { t } = useTranslation(['resources', 'common', 'machines']);
  const { data: machines = [] } = useGetTeamMachines(repository?.teamName ?? undefined);
  const repositoryData = useRepositoryVaultData(repository, machines);

  useEffect(() => {
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && visible) {
        onClose();
      }
    };

    if (visible) {
      document.addEventListener('keydown', handleEscape);
    }

    return () => {
      document.removeEventListener('keydown', handleEscape);
    };
  }, [visible, onClose]);

  if (!repository || !visible) return null;

  return (
    <DetailPanelSurface
      $splitView={splitView}
      $visible={visible}
      data-testid="repository-detail-panel"
    >
      <DetailPanelBody data-testid="repository-detail-content">
        {repositoryData ? (
          <>
            <RepoInfoSection repository={repository} panelData={repositoryData} t={t} />
            <ExternalVolumeWarning repository={repository} panelData={repositoryData} t={t} />
            <StorageSection repository={repository} panelData={repositoryData} t={t} />
            <FilePathsSection repository={repository} panelData={repositoryData} t={t} />
            {repositoryData.repositoryData.mounted && (
              <ActivitySection repository={repository} panelData={repositoryData} t={t} />
            )}
            {repositoryData.services.length > 0 && (
              <ServicesSection repository={repository} panelData={repositoryData} t={t} />
            )}
          </>
        ) : (
          <Flex>
            <Empty
              description={t('resources:repositories.noRepoData')}
              data-testid="repository-detail-empty-state"
            />
          </Flex>
        )}
      </DetailPanelBody>
    </DetailPanelSurface>
  );
};

interface SectionProps {
  repository: GetTeamRepositories_ResultSet1;
  panelData: RepositoryPanelData;
  t: TypedTFunction;
}

const RepoInfoSection: React.FC<SectionProps> = ({ repository, panelData, t }) => {
  const { repositoryData } = panelData;

  return (
    <Flex vertical data-testid="repository-detail-info-section">
      <DetailPanelSectionHeader>
        <FolderOutlined />
        <DetailPanelSectionTitle level={5}>
          {t('resources:repositories.repoInfo')}
        </DetailPanelSectionTitle>
      </DetailPanelSectionHeader>

      <DetailPanelSectionCard size="small" data-testid="repository-detail-info-card">
        <Flex vertical className="w-full">
          <DetailPanelFieldRow>
            <DetailPanelFieldLabel>
              {t('resources:repositories.repositoryGuid')}:
            </DetailPanelFieldLabel>
            <DetailPanelFieldMonospaceValue
              copyable
              data-testid={`repo-detail-guid-${repository.repositoryName}`}
            >
              {repository.repositoryGuid}
            </DetailPanelFieldMonospaceValue>
          </DetailPanelFieldRow>

          <DetailPanelFieldRow>
            <DetailPanelFieldLabel>{t('resources:repositories.status')}:</DetailPanelFieldLabel>
            <Space>
              {repositoryData.mounted ? (
                <Tag
                  bordered={false}
                  icon={<CheckCircleOutlined />}
                  data-testid={`repo-detail-status-mounted-${repository.repositoryName}`}
                >
                  {t('resources:repositories.mounted')}
                </Tag>
              ) : (
                <Tag
                  bordered={false}
                  data-testid={`repo-detail-status-unmounted-${repository.repositoryName}`}
                  icon={<StopOutlined />}
                >
                  {t('resources:repositories.notMounted')}
                </Tag>
              )}
              {repositoryData.accessible && (
                <Tag
                  bordered={false}
                  data-testid={`repo-detail-status-accessible-${repository.repositoryName}`}
                >
                  {t('resources:repositories.accessible')}
                </Tag>
              )}
            </Space>
          </DetailPanelFieldRow>

          {repositoryData.has_rediaccfile && (
            <DetailPanelFieldRow>
              <DetailPanelFieldLabel>
                {t('resources:repositories.rediaccfile')}:
              </DetailPanelFieldLabel>
              <Tag
                bordered={false}
                data-testid={`repo-detail-rediaccfile-${repository.repositoryName}`}
              >
                {t('resources:repositories.hasRediaccfile')}
              </Tag>
            </DetailPanelFieldRow>
          )}

          {repositoryData.docker_running &&
            repositoryData.volume_status &&
            repositoryData.volume_status !== 'none' && (
              <DetailPanelFieldRow>
                <DetailPanelFieldLabel>
                  {t('resources:repositories.dockerVolumes.label')}:
                </DetailPanelFieldLabel>
                {repositoryData.volume_status === 'safe' ? (
                  <Tag
                    bordered={false}
                    icon={<CheckCircleOutlined />}
                    data-testid={`repo-detail-volume-safe-${repository.repositoryName}`}
                  >
                    {repositoryData.internal_volumes === 1
                      ? t('resources:repositories.dockerVolumes.safeVolume', {
                          count: repositoryData.internal_volumes,
                        })
                      : t('resources:repositories.dockerVolumes.safeVolumes', {
                          count: repositoryData.internal_volumes,
                        })}
                  </Tag>
                ) : (
                  <Tag
                    bordered={false}
                    icon={<WarningOutlined />}
                    data-testid={`repo-detail-volume-warning-${repository.repositoryName}`}
                  >
                    {repositoryData.external_volumes}{' '}
                    {t('resources:repositories.dockerVolumes.external')},{' '}
                    {repositoryData.internal_volumes}{' '}
                    {t('resources:repositories.dockerVolumes.internal')}
                  </Tag>
                )}
              </DetailPanelFieldRow>
            )}
        </Flex>
      </DetailPanelSectionCard>
    </Flex>
  );
};

interface WarningProps {
  repository: GetTeamRepositories_ResultSet1;
  panelData: RepositoryPanelData;
  t: TypedTFunction;
}

const ExternalVolumeWarning: React.FC<WarningProps> = ({ repository, panelData, t }) => {
  const { repositoryData } = panelData;

  if (
    repositoryData.volume_status !== 'warning' ||
    repositoryData.external_volume_names.length === 0
  ) {
    return null;
  }

  return (
    <Alert
      type="warning"
      icon={<WarningOutlined />}
      message={t('resources:repositories.dockerVolumes.warningTitle')}
      description={
        <Flex vertical>
          <DetailPanelFieldValue>
            {t('resources:repositories.dockerVolumes.warningDescription')}
          </DetailPanelFieldValue>
          <ul>
            {repositoryData.external_volume_names.map((vol) => (
              <li key={vol}>
                <DetailPanelFieldValue code>{vol}</DetailPanelFieldValue>
              </li>
            ))}
          </ul>
          <DetailPanelFieldValue>
            <strong>{t('common:important')}:</strong>{' '}
            {t('resources:repositories.dockerVolumes.orphanWarning', { path: '$REPOSITORY_PATH' })}
          </DetailPanelFieldValue>
        </Flex>
      }
      data-testid={`repo-detail-volume-warning-alert-${repository.repositoryName}`}
    />
  );
};

const FilePathsSection: React.FC<SectionProps> = ({ repository, panelData, t }) => {
  const { repositoryData } = panelData;

  return (
    <Flex vertical>
      <DetailPanelDivider data-testid="repository-detail-file-paths-divider">
        <FolderOutlined />
        {t('resources:repositories.filePaths')}
      </DetailPanelDivider>

      <DetailPanelSectionCard
        size="small"
        data-testid={`repo-detail-file-paths-card-${repository.repositoryName}`}
      >
        <Flex vertical className="w-full">
          <DetailPanelFieldRow>
            <DetailPanelFieldLabel>{t('resources:repositories.imagePath')}:</DetailPanelFieldLabel>
            <DetailPanelFieldMonospaceValue
              copyable={{ text: repositoryData.image_path }}
              data-testid={`repo-detail-image-path-${repository.repositoryName}`}
            >
              {abbreviatePath(repositoryData.image_path, 45)}
            </DetailPanelFieldMonospaceValue>
          </DetailPanelFieldRow>
          {repositoryData.mount_path && (
            <DetailPanelFieldRow>
              <DetailPanelFieldLabel>
                {t('resources:repositories.mountPath')}:
              </DetailPanelFieldLabel>
              <DetailPanelFieldMonospaceValue
                copyable={{ text: repositoryData.mount_path }}
                data-testid={`repo-detail-mount-path-${repository.repositoryName}`}
              >
                {abbreviatePath(repositoryData.mount_path, 45)}
              </DetailPanelFieldMonospaceValue>
            </DetailPanelFieldRow>
          )}
        </Flex>
      </DetailPanelSectionCard>
    </Flex>
  );
};

const ActivitySection: React.FC<SectionProps> = ({ repository, panelData, t }) => {
  const { repositoryData } = panelData;

  return (
    <Flex vertical>
      <DetailPanelDivider data-testid="repository-detail-activity-divider">
        <FieldTimeOutlined />
        {t('resources:repositories.activity')}
      </DetailPanelDivider>

      <DetailPanelSectionCard
        size="small"
        data-testid={`repo-detail-activity-card-${repository.repositoryName}`}
      >
        <Flex vertical>
          {repositoryData.docker_running && (
            <DetailPanelFieldRow>
              <DetailPanelFieldLabel>
                {t('resources:repositories.containers')}:
              </DetailPanelFieldLabel>
              <DetailPanelFieldValue>{repositoryData.container_count}</DetailPanelFieldValue>
            </DetailPanelFieldRow>
          )}
          {repositoryData.has_services && (
            <DetailPanelFieldRow>
              <DetailPanelFieldLabel>{t('resources:repositories.services')}:</DetailPanelFieldLabel>
              <DetailPanelFieldValue>{repositoryData.service_count}</DetailPanelFieldValue>
            </DetailPanelFieldRow>
          )}
        </Flex>
      </DetailPanelSectionCard>
    </Flex>
  );
};
