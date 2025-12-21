import React, { useEffect, useMemo } from 'react';
import { Alert, Card, Col, Empty, Flex, Progress, Row, Space, Tag, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { useMachines } from '@/api/queries/machines';
import {
  DetailPanelBody,
  DetailPanelCollapseButton,
  DetailPanelDivider,
  DetailPanelFieldLabel,
  DetailPanelFieldMonospaceValue,
  DetailPanelFieldRow,
  DetailPanelFieldValue,
  DetailPanelHeader,
  DetailPanelHeaderRow,
  DetailPanelSectionCard,
  DetailPanelSectionHeader,
  DetailPanelSectionTitle,
  DetailPanelSurface,
  DetailPanelTagGroup,
  DetailPanelTitle,
  DetailPanelTitleGroup,
} from '@/components/resources/internal/detailPanelPrimitives';
import type { Machine } from '@/types';
import {
  AppstoreOutlined,
  CheckCircleOutlined,
  CloudServerOutlined,
  CodeOutlined,
  DatabaseOutlined,
  DoubleRightOutlined,
  FieldTimeOutlined,
  FolderOutlined,
  InfoCircleOutlined,
  StopOutlined,
  WarningOutlined,
} from '@/utils/optimizedIcons';
import { abbreviatePath } from '@/utils/pathUtils';
import type { GetTeamRepositories_ResultSet1 as Repository } from '@rediacc/shared/types';
import type { TFunction } from 'i18next';

interface RepositoryDetailPanelProps {
  repository: Repository | null;
  visible: boolean;
  onClose: () => void;
  splitView?: boolean;
}

interface RepositoryVaultData {
  name: string;
  size: number;
  size_human: string;
  modified: number;
  modified_human: string;
  image_path: string;
  mounted: boolean;
  mount_path: string;
  accessible: boolean;
  disk_space?: {
    total: string;
    used: string;
    available: string;
    use_percent: string;
  };
  has_rediaccfile: boolean;
  docker_running: boolean;
  container_count: number;
  has_services: boolean;
  service_count: number;
  total_volumes?: number;
  internal_volumes?: number;
  external_volumes?: number;
  external_volume_names?: string[];
  volume_status?: 'safe' | 'warning' | 'none';
}

interface ServiceData {
  name: string;
  active_state: string;
  memory_human?: string;
  main_pid?: number;
  uptime_human?: string;
  restarts?: number;
  repository?: string;
  service_name?: string;
  unit_file?: string;
}

interface RepositoryPanelData {
  machine: Machine;
  repositoryData: RepositoryVaultData;
  systemData?: Record<string, unknown>;
  services: ServiceData[];
}

const getTagColor = (variant: 'team' | 'machine' | 'version') =>
  variant === 'team' ? 'success' : variant === 'machine' ? 'processing' : 'default';

const getStatusColor = (tone?: 'success' | 'warning' | 'error' | 'info' | 'neutral') =>
  tone === 'neutral' ? 'default' : tone === 'info' ? 'processing' : tone;

export const RepositoryDetailPanel: React.FC<RepositoryDetailPanelProps> = ({
  repository,
  visible,
  onClose,
  splitView = false,
}) => {
  const { t } = useTranslation(['resources', 'common', 'machines']);
  const { data: machines = [] } = useMachines(repository?.teamName);

  const repositoryData = useMemo<RepositoryPanelData | null>(() => {
    if (!repository || !machines.length) return null;

    for (const machine of machines) {
      if (!machine.vaultStatus) continue;

      try {
        const trimmedStatus = machine.vaultStatus.trim();
        if (
          trimmedStatus.startsWith('jq:') ||
          trimmedStatus.startsWith('error:') ||
          !trimmedStatus.startsWith('{')
        ) {
          continue;
        }

        const vaultStatusData = JSON.parse(trimmedStatus);

        if (vaultStatusData.status === 'completed' && vaultStatusData.result) {
          let cleanedResult = vaultStatusData.result;
          const jsonEndMatch = cleanedResult.match(/(\}[\s\n]*$)/);
          if (jsonEndMatch) {
            const lastBraceIndex = cleanedResult.lastIndexOf('}');
            if (lastBraceIndex < cleanedResult.length - 10) {
              cleanedResult = cleanedResult.substring(0, lastBraceIndex + 1);
            }
          }

          const newlineIndex = cleanedResult.indexOf('\njq:');
          if (newlineIndex > 0) {
            cleanedResult = cleanedResult.substring(0, newlineIndex);
          }

          const result = JSON.parse(cleanedResult.trim());

          if (Array.isArray(result.repositories)) {
            const repositoryData = result.repositories.find((r: RepositoryVaultData) => {
              return r.name === repository.repositoryName || r.name === repository.repositoryGuid;
            });

            if (repositoryData) {
              const servicesForRepo: ServiceData[] = [];

              if (Array.isArray(result.services)) {
                result.services.forEach((service: ServiceData) => {
                  if (
                    service.repository === repositoryData.name ||
                    service.repository === repository.repositoryGuid
                  ) {
                    servicesForRepo.push(service);
                    return;
                  }

                  const serviceName = service.service_name || service.unit_file || '';
                  const guidMatch = serviceName.match(/rediacc_([0-9a-f-]{36})_/);
                  if (
                    guidMatch &&
                    (guidMatch[1] === repository.repositoryGuid ||
                      guidMatch[1] === repositoryData.name)
                  ) {
                    servicesForRepo.push(service);
                  }
                });
              }

              return {
                machine,
                repositoryData: repositoryData,
                systemData: result.system,
                services: servicesForRepo,
              };
            }
          }
        }
      } catch (error) {
        console.error('Error parsing vault status:', error);
      }
    }

    return null;
  }, [repository, machines]);

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
      <DetailPanelHeader>
        <DetailPanelHeaderRow>
          <DetailPanelTitleGroup>
            <FolderOutlined style={{ fontSize: 28 }} />
            <DetailPanelTitle
              level={4}
              data-testid={`repo-detail-title-${repository.repositoryName}`}
            >
              {repository.repositoryName}
            </DetailPanelTitle>
          </DetailPanelTitleGroup>
          <DetailPanelCollapseButton
            icon={<DoubleRightOutlined />}
            onClick={onClose}
            data-testid="repository-detail-collapse"
            aria-label="Collapse panel"
          />
        </DetailPanelHeaderRow>

        <DetailPanelTagGroup>
          <Tag
            bordered={false}
            color={getTagColor('team')}
            icon={<AppstoreOutlined />}
            data-testid={`repo-detail-team-tag-${repository.repositoryName}`}
          >
            {t('common:general.team')}: {repository.teamName}
          </Tag>
          {repositoryData && (
            <Tag
              bordered={false}
              color={getTagColor('machine')}
              icon={<CloudServerOutlined />}
              data-testid={`repo-detail-machine-tag-${repository.repositoryName}`}
            >
              {t('machines:machine')}: {repositoryData.machine.machineName}
            </Tag>
          )}
          <Tag
            bordered={false}
            color={getTagColor('version')}
            data-testid={`repo-detail-vault-version-tag-${repository.repositoryName}`}
          >
            {t('resources:repositories.vaultVersion')}: {repository.vaultVersion}
          </Tag>
        </DetailPanelTagGroup>
      </DetailPanelHeader>

      <DetailPanelBody data-testid="repository-detail-content">
        {!repositoryData ? (
          <Flex>
            <Empty
              description={t('resources:repositories.noRepoData')}
              data-testid="repository-detail-empty-state"
            />
          </Flex>
        ) : (
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
        )}
      </DetailPanelBody>
    </DetailPanelSurface>
  );
};

interface SectionProps {
  repository: Repository;
  panelData: RepositoryPanelData;
  t: TFunction<'resources' | 'common' | 'machines'>;
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
        <Flex vertical style={{ width: '100%' }}>
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
                  color={getStatusColor('success')}
                  icon={<CheckCircleOutlined />}
                  data-testid={`repo-detail-status-mounted-${repository.repositoryName}`}
                >
                  {t('resources:repositories.mounted')}
                </Tag>
              ) : (
                <Tag
                  bordered={false}
                  color={getStatusColor('neutral')}
                  data-testid={`repo-detail-status-unmounted-${repository.repositoryName}`}
                  icon={<StopOutlined />}
                >
                  {t('resources:repositories.notMounted')}
                </Tag>
              )}
              {repositoryData.accessible && (
                <Tag
                  bordered={false}
                  color={getStatusColor('success')}
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
                color={getStatusColor('info')}
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
                <DetailPanelFieldLabel>Docker Volumes:</DetailPanelFieldLabel>
                {repositoryData.volume_status === 'safe' ? (
                  <Tag
                    bordered={false}
                    color={getStatusColor('success')}
                    icon={<CheckCircleOutlined />}
                    data-testid={`repo-detail-volume-safe-${repository.repositoryName}`}
                  >
                    {repositoryData.internal_volumes} Safe Volume
                    {repositoryData.internal_volumes !== 1 ? 's' : ''}
                  </Tag>
                ) : (
                  <Tag
                    bordered={false}
                    color={getStatusColor('warning')}
                    icon={<WarningOutlined />}
                    data-testid={`repo-detail-volume-warning-${repository.repositoryName}`}
                  >
                    {repositoryData.external_volumes} External, {repositoryData.internal_volumes}{' '}
                    Internal
                  </Tag>
                )}
              </DetailPanelFieldRow>
            )}
        </Flex>
      </DetailPanelSectionCard>
    </Flex>
  );
};

const ExternalVolumeWarning: React.FC<SectionProps> = ({ repository, panelData }) => {
  const { repositoryData } = panelData;

  if (
    repositoryData.volume_status !== 'warning' ||
    !repositoryData.external_volume_names ||
    repositoryData.external_volume_names.length === 0
  ) {
    return null;
  }

  return (
    <Alert
      type="warning"
      showIcon
      icon={<WarningOutlined />}
      message="External Docker Volumes Detected"
      description={
        <Flex vertical>
          <DetailPanelFieldValue>
            The following volumes are stored outside the repository:
          </DetailPanelFieldValue>
          <ul>
            {repositoryData.external_volume_names.map((vol) => (
              <li key={vol}>
                <DetailPanelFieldValue code>{vol}</DetailPanelFieldValue>
              </li>
            ))}
          </ul>
          <DetailPanelFieldValue color="secondary">
            <strong>Warning:</strong> If this repository is cloned, these volumes will be orphaned.
            Use bind mounts to <DetailPanelFieldValue code>$REPOSITORY_PATH</DetailPanelFieldValue>{' '}
            instead.
          </DetailPanelFieldValue>
        </Flex>
      }
      data-testid={`repo-detail-volume-warning-alert-${repository.repositoryName}`}
    />
  );
};

const StorageSection: React.FC<SectionProps> = ({ repository, panelData, t }) => {
  const { repositoryData } = panelData;
  const diskPercent = repositoryData.disk_space
    ? parseInt(repositoryData.disk_space.use_percent, 10)
    : 0;

  return (
    <Flex vertical>
      <DetailPanelDivider data-testid="repository-detail-storage-divider">
        <InfoCircleOutlined />
        {t('resources:repositories.storageInfo')}
      </DetailPanelDivider>

      <Row gutter={[16, 16]}>
        <Col span={24}>
          <DetailPanelSectionCard
            size="small"
            data-testid={`repo-detail-storage-info-card-${repository.repositoryName}`}
          >
            <Flex vertical style={{ width: '100%' }}>
              <DetailPanelFieldRow>
                <DetailPanelFieldLabel>
                  {t('resources:repositories.imageSize')}:
                </DetailPanelFieldLabel>
                <DetailPanelFieldValue>{repositoryData.size_human}</DetailPanelFieldValue>
              </DetailPanelFieldRow>
              <DetailPanelFieldRow>
                <DetailPanelFieldLabel>
                  {t('resources:repositories.lastModified')}:
                </DetailPanelFieldLabel>
                <DetailPanelFieldValue>{repositoryData.modified_human}</DetailPanelFieldValue>
              </DetailPanelFieldRow>
            </Flex>
          </DetailPanelSectionCard>
        </Col>

        {repositoryData.mounted && repositoryData.disk_space && (
          <Col span={24}>
            <DetailPanelSectionCard
              size="small"
              data-testid={`repo-detail-disk-usage-card-${repository.repositoryName}`}
            >
              <Flex vertical style={{ width: '100%' }}>
                <DetailPanelFieldRow>
                  <Space>
                    <DatabaseOutlined />
                    <DetailPanelFieldValue strong>
                      {t('resources:repositories.diskUsage')}
                    </DetailPanelFieldValue>
                  </Space>
                </DetailPanelFieldRow>
                <DetailPanelFieldValue>
                  {repositoryData.disk_space.used} / {repositoryData.disk_space.total}
                </DetailPanelFieldValue>
                <Progress
                  percent={diskPercent}
                  status={diskPercent > 90 ? 'exception' : 'normal'}
                  data-testid={`repo-detail-disk-usage-progress-${repository.repositoryName}`}
                />
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  {t('resources:repositories.available')}: {repositoryData.disk_space.available}
                </Typography.Text>
              </Flex>
            </DetailPanelSectionCard>
          </Col>
        )}
      </Row>
    </Flex>
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
        <Flex vertical style={{ width: '100%' }}>
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

const ServicesSection: React.FC<SectionProps> = ({ repository, panelData, t }) => (
  <Flex vertical>
    <DetailPanelDivider data-testid="repository-detail-services-divider">
      <CodeOutlined />
      {t('resources:repositories.servicesSection')}
    </DetailPanelDivider>

    <Flex vertical data-testid="repository-detail-services-list">
      {panelData.services.map((service, index) => {
        const state: 'active' | 'failed' | 'other' =
          service.active_state === 'active'
            ? 'active'
            : service.active_state === 'failed'
              ? 'failed'
              : 'other';

        return (
          <Card
            key={`${service.name}-${index}`}
            size="small"
            data-testid={`repo-detail-service-card-${repository.repositoryName}-${service.name}`}
          >
            <Row gutter={[16, 8]}>
              <Col span={24}>
                <Flex justify="space-between" align="center">
                  <DetailPanelFieldValue
                    strong
                    data-testid={`repo-detail-service-name-${repository.repositoryName}-${service.name}`}
                  >
                    {service.name}
                  </DetailPanelFieldValue>
                  <Tag
                    bordered={false}
                    color={getStatusColor(
                      state === 'active' ? 'success' : state === 'failed' ? 'error' : 'neutral'
                    )}
                    data-testid={`repo-detail-service-status-${repository.repositoryName}-${service.name}`}
                  >
                    {service.active_state}
                  </Tag>
                </Flex>
              </Col>
              {(service.memory_human ||
                service.main_pid ||
                service.uptime_human ||
                service.restarts !== undefined) && (
                <Col span={24}>
                  <Flex wrap>
                    {service.memory_human && (
                      <Flex vertical>
                        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                          Memory
                        </Typography.Text>
                        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                          {service.memory_human}
                        </Typography.Text>
                      </Flex>
                    )}
                    {service.main_pid && (
                      <Flex vertical>
                        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                          PID
                        </Typography.Text>
                        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                          {service.main_pid}
                        </Typography.Text>
                      </Flex>
                    )}
                    {service.uptime_human && (
                      <Flex vertical>
                        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                          Uptime
                        </Typography.Text>
                        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                          {service.uptime_human}
                        </Typography.Text>
                      </Flex>
                    )}
                    {service.restarts !== undefined && (
                      <Flex vertical>
                        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                          Restarts
                        </Typography.Text>
                        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                          {service.restarts}
                        </Typography.Text>
                      </Flex>
                    )}
                  </Flex>
                </Col>
              )}
            </Row>
          </Card>
        );
      })}
    </Flex>
  </Flex>
);
