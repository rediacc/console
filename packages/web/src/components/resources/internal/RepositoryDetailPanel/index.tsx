import React, { useEffect, useMemo } from 'react';
import { Col, Progress, Row, Space } from 'antd';
import { useTranslation } from 'react-i18next';
import { useMachines } from '@/api/queries/machines';
import { IconWrapper, RediaccAlert, RediaccEmpty, RediaccText } from '@/components/ui';
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
import {
  ActivityCard,
  ActivityMetrics,
  CollapseButton,
  ContentWrapper,
  FieldLabel,
  FieldRow,
  FieldValue,
  FieldValueMonospace,
  Header,
  HeaderIcon,
  HeaderRow,
  PanelTitle,
  PanelWrapper,
  PathsCard,
  Section,
  SectionCard,
  SectionDivider,
  SectionHeader,
  SectionTitle,
  ServiceCard,
  ServiceHeader,
  ServiceMetaGrid,
  ServiceMetaItem,
  ServicesList,
  Stack,
  StyledRediaccEmpty,
  StatusTag,
  StyledTag,
  TagGroup,
  TitleGroup,
  VolumeDescription,
  VolumeList,
} from './styles';
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
    <PanelWrapper $splitView={splitView} $visible={visible} data-testid="repository-detail-panel">
      <Header>
        <HeaderRow>
          <TitleGroup>
            <HeaderIcon />
            <PanelTitle level={4} data-testid={`repo-detail-title-${repository.repositoryName}`}>
              {repository.repositoryName}
            </PanelTitle>
          </TitleGroup>
          <CollapseButton
            variant="text"
            icon={<DoubleRightOutlined />}
            onClick={onClose}
            data-testid="repository-detail-collapse"
            aria-label="Collapse panel"
          />
        </HeaderRow>

        <TagGroup>
          <StyledTag
            $variant="team"
            icon={<AppstoreOutlined />}
            data-testid={`repo-detail-team-tag-${repository.repositoryName}`}
          >
            {t('common:general.team')}: {repository.teamName}
          </StyledTag>
          {repositoryData && (
            <StyledTag
              $variant="machine"
              icon={<CloudServerOutlined />}
              data-testid={`repo-detail-machine-tag-${repository.repositoryName}`}
            >
              {t('machines:machine')}: {repositoryData.machine.machineName}
            </StyledTag>
          )}
          <StyledTag
            $variant="version"
            data-testid={`repo-detail-vault-version-tag-${repository.repositoryName}`}
          >
            {t('resources:repositories.vaultVersion')}: {repository.vaultVersion}
          </StyledTag>
        </TagGroup>
      </Header>

      <ContentWrapper data-testid="repository-detail-content">
        {!repositoryData ? (
          <StyledRediaccEmpty>
            <RediaccEmpty
              description={t('resources:repositories.noRepoData')}
              data-testid="repository-detail-empty-state"
            />
          </StyledRediaccEmpty>
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
      </ContentWrapper>
    </PanelWrapper>
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
    <Section data-testid="repository-detail-info-section">
      <SectionHeader>
        <IconWrapper $color="var(--color-success)" $size="lg">
          <FolderOutlined />
        </IconWrapper>
        <SectionTitle level={5}>{t('resources:repositories.repoInfo')}</SectionTitle>
      </SectionHeader>

      <SectionCard size="sm" data-testid="repository-detail-info-card">
        <Stack>
          <FieldRow>
            <FieldLabel>{t('resources:repositories.repositoryGuid')}:</FieldLabel>
            <FieldValueMonospace
              copyable
              data-testid={`repo-detail-guid-${repository.repositoryName}`}
            >
              {repository.repositoryGuid}
            </FieldValueMonospace>
          </FieldRow>

          <FieldRow>
            <FieldLabel>{t('resources:repositories.status')}:</FieldLabel>
            <Space>
              {repositoryData.mounted ? (
                <StatusTag
                  $tone="success"
                  icon={<CheckCircleOutlined />}
                  data-testid={`repo-detail-status-mounted-${repository.repositoryName}`}
                >
                  {t('resources:repositories.mounted')}
                </StatusTag>
              ) : (
                <StatusTag
                  data-testid={`repo-detail-status-unmounted-${repository.repositoryName}`}
                  icon={<StopOutlined />}
                >
                  {t('resources:repositories.notMounted')}
                </StatusTag>
              )}
              {repositoryData.accessible && (
                <StatusTag
                  $tone="success"
                  data-testid={`repo-detail-status-accessible-${repository.repositoryName}`}
                >
                  {t('resources:repositories.accessible')}
                </StatusTag>
              )}
            </Space>
          </FieldRow>

          {repositoryData.has_rediaccfile && (
            <FieldRow>
              <FieldLabel>{t('resources:repositories.rediaccfile')}:</FieldLabel>
              <StatusTag
                $tone="info"
                data-testid={`repo-detail-rediaccfile-${repository.repositoryName}`}
              >
                {t('resources:repositories.hasRediaccfile')}
              </StatusTag>
            </FieldRow>
          )}

          {repositoryData.docker_running &&
            repositoryData.volume_status &&
            repositoryData.volume_status !== 'none' && (
              <FieldRow>
                <FieldLabel>Docker Volumes:</FieldLabel>
                {repositoryData.volume_status === 'safe' ? (
                  <StatusTag
                    $tone="success"
                    icon={<CheckCircleOutlined />}
                    data-testid={`repo-detail-volume-safe-${repository.repositoryName}`}
                  >
                    {repositoryData.internal_volumes} Safe Volume
                    {repositoryData.internal_volumes !== 1 ? 's' : ''}
                  </StatusTag>
                ) : (
                  <StatusTag
                    $tone="warning"
                    icon={<WarningOutlined />}
                    data-testid={`repo-detail-volume-warning-${repository.repositoryName}`}
                  >
                    {repositoryData.external_volumes} External, {repositoryData.internal_volumes}{' '}
                    Internal
                  </StatusTag>
                )}
              </FieldRow>
            )}
        </Stack>
      </SectionCard>
    </Section>
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
    <RediaccAlert
      spacing="default"
      variant="warning"
      showIcon
      icon={<WarningOutlined />}
      message="External Docker Volumes Detected"
      description={
        <VolumeDescription>
          <FieldValue>The following volumes are stored outside the repository:</FieldValue>
          <VolumeList>
            {repositoryData.external_volume_names.map((vol) => (
              <li key={vol}>
                <FieldValue code>{vol}</FieldValue>
              </li>
            ))}
          </VolumeList>
          <FieldValue color="secondary">
            <strong>Warning:</strong> If this repository is cloned, these volumes will be orphaned.
            Use bind mounts to <FieldValue code>$REPOSITORY_PATH</FieldValue> instead.
          </FieldValue>
        </VolumeDescription>
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
    <Section>
      <SectionDivider data-testid="repository-detail-storage-divider">
        <IconWrapper $color="var(--color-info)">
          <InfoCircleOutlined />
        </IconWrapper>
        {t('resources:repositories.storageInfo')}
      </SectionDivider>

      <Row gutter={[16, 16]}>
        <Col span={24}>
          <SectionCard
            size="sm"
            data-testid={`repo-detail-storage-info-card-${repository.repositoryName}`}
          >
            <Stack>
              <FieldRow>
                <FieldLabel>{t('resources:repositories.imageSize')}:</FieldLabel>
                <FieldValue>{repositoryData.size_human}</FieldValue>
              </FieldRow>
              <FieldRow>
                <FieldLabel>{t('resources:repositories.lastModified')}:</FieldLabel>
                <FieldValue>{repositoryData.modified_human}</FieldValue>
              </FieldRow>
            </Stack>
          </SectionCard>
        </Col>

        {repositoryData.mounted && repositoryData.disk_space && (
          <Col span={24}>
            <SectionCard
              size="sm"
              data-testid={`repo-detail-disk-usage-card-${repository.repositoryName}`}
            >
              <Stack>
                <FieldRow>
                  <Space>
                    <IconWrapper $color="var(--color-success)">
                      <DatabaseOutlined />
                    </IconWrapper>
                    <FieldValue weight="semibold">
                      {t('resources:repositories.diskUsage')}
                    </FieldValue>
                  </Space>
                </FieldRow>
                <FieldValue>
                  {repositoryData.disk_space.used} / {repositoryData.disk_space.total}
                </FieldValue>
                <Progress
                  percent={diskPercent}
                  status={diskPercent > 90 ? 'exception' : 'normal'}
                  strokeColor={diskPercent > 90 ? 'var(--color-error)' : 'var(--color-success)'}
                  data-testid={`repo-detail-disk-usage-progress-${repository.repositoryName}`}
                />
                <RediaccText variant="caption">
                  {t('resources:repositories.available')}: {repositoryData.disk_space.available}
                </RediaccText>
              </Stack>
            </SectionCard>
          </Col>
        )}
      </Row>
    </Section>
  );
};

const FilePathsSection: React.FC<SectionProps> = ({ repository, panelData, t }) => {
  const { repositoryData } = panelData;

  return (
    <Section>
      <SectionDivider data-testid="repository-detail-file-paths-divider">
        <IconWrapper $color="var(--color-primary)">
          <FolderOutlined />
        </IconWrapper>
        {t('resources:repositories.filePaths')}
      </SectionDivider>

      <PathsCard size="sm" data-testid={`repo-detail-file-paths-card-${repository.repositoryName}`}>
        <Stack>
          <FieldRow>
            <FieldLabel>{t('resources:repositories.imagePath')}:</FieldLabel>
            <FieldValueMonospace
              copyable={{ text: repositoryData.image_path }}
              data-testid={`repo-detail-image-path-${repository.repositoryName}`}
            >
              {abbreviatePath(repositoryData.image_path, 45)}
            </FieldValueMonospace>
          </FieldRow>
          {repositoryData.mount_path && (
            <FieldRow>
              <FieldLabel>{t('resources:repositories.mountPath')}:</FieldLabel>
              <FieldValueMonospace
                copyable={{ text: repositoryData.mount_path }}
                data-testid={`repo-detail-mount-path-${repository.repositoryName}`}
              >
                {abbreviatePath(repositoryData.mount_path, 45)}
              </FieldValueMonospace>
            </FieldRow>
          )}
        </Stack>
      </PathsCard>
    </Section>
  );
};

const ActivitySection: React.FC<SectionProps> = ({ repository, panelData, t }) => {
  const { repositoryData } = panelData;

  return (
    <Section>
      <SectionDivider data-testid="repository-detail-activity-divider">
        <IconWrapper $color="var(--color-info)">
          <FieldTimeOutlined />
        </IconWrapper>
        {t('resources:repositories.activity')}
      </SectionDivider>

      <ActivityCard
        size="sm"
        data-testid={`repo-detail-activity-card-${repository.repositoryName}`}
      >
        <ActivityMetrics>
          {repositoryData.docker_running && (
            <FieldRow>
              <FieldLabel>{t('resources:repositories.containers')}:</FieldLabel>
              <FieldValue>{repositoryData.container_count}</FieldValue>
            </FieldRow>
          )}
          {repositoryData.has_services && (
            <FieldRow>
              <FieldLabel>{t('resources:repositories.services')}:</FieldLabel>
              <FieldValue>{repositoryData.service_count}</FieldValue>
            </FieldRow>
          )}
        </ActivityMetrics>
      </ActivityCard>
    </Section>
  );
};

const ServicesSection: React.FC<SectionProps> = ({ repository, panelData, t }) => (
  <Section>
    <SectionDivider data-testid="repository-detail-services-divider">
      <IconWrapper $color="var(--color-primary)">
        <CodeOutlined />
      </IconWrapper>
      {t('resources:repositories.servicesSection')}
    </SectionDivider>

    <ServicesList data-testid="repository-detail-services-list">
      {panelData.services.map((service, index) => {
        const state: 'active' | 'failed' | 'other' =
          service.active_state === 'active'
            ? 'active'
            : service.active_state === 'failed'
              ? 'failed'
              : 'other';

        return (
          <ServiceCard
            key={`${service.name}-${index}`}
            size="sm"
            $state={state}
            data-testid={`repo-detail-service-card-${repository.repositoryName}-${service.name}`}
          >
            <Row gutter={[16, 8]}>
              <Col span={24}>
                <ServiceHeader>
                  <FieldValue
                    weight="semibold"
                    data-testid={`repo-detail-service-name-${repository.repositoryName}-${service.name}`}
                  >
                    {service.name}
                  </FieldValue>
                  <StatusTag
                    $tone={(() => {
                      if (state === 'active') return 'success';
                      if (state === 'failed') return 'error';
                      return 'neutral';
                    })()}
                    data-testid={`repo-detail-service-status-${repository.repositoryName}-${service.name}`}
                  >
                    {service.active_state}
                  </StatusTag>
                </ServiceHeader>
              </Col>
              {(service.memory_human ||
                service.main_pid ||
                service.uptime_human ||
                service.restarts !== undefined) && (
                <Col span={24}>
                  <ServiceMetaGrid>
                    {service.memory_human && (
                      <ServiceMetaItem>
                        <RediaccText variant="caption">Memory</RediaccText>
                        <RediaccText variant="caption">{service.memory_human}</RediaccText>
                      </ServiceMetaItem>
                    )}
                    {service.main_pid && (
                      <ServiceMetaItem>
                        <RediaccText variant="caption">PID</RediaccText>
                        <RediaccText variant="caption">{service.main_pid}</RediaccText>
                      </ServiceMetaItem>
                    )}
                    {service.uptime_human && (
                      <ServiceMetaItem>
                        <RediaccText variant="caption">Uptime</RediaccText>
                        <RediaccText variant="caption">{service.uptime_human}</RediaccText>
                      </ServiceMetaItem>
                    )}
                    {service.restarts !== undefined && (
                      <ServiceMetaItem>
                        <RediaccText variant="caption">Restarts</RediaccText>
                        <RediaccText variant="caption">{service.restarts}</RediaccText>
                      </ServiceMetaItem>
                    )}
                  </ServiceMetaGrid>
                </Col>
              )}
            </Row>
          </ServiceCard>
        );
      })}
    </ServicesList>
  </Section>
);
