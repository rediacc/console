import React, { useEffect, useMemo } from 'react'
import { Row, Col, Progress, Space } from 'antd'
import type { TFunction } from 'i18next'
import {
  DoubleRightOutlined,
  DatabaseOutlined,
  InfoCircleOutlined,
  AppstoreOutlined,
  FieldTimeOutlined,
  CloudServerOutlined,
  FolderOutlined,
  CheckCircleOutlined,
  StopOutlined,
  CodeOutlined,
  WarningOutlined,
} from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import type { Repository } from '@/api/queries/repositories'
import { useMachines } from '@/api/queries/machines'
import { abbreviatePath } from '@/utils/pathUtils'
import {
  PanelWrapper,
  StickyHeader,
  HeaderRow,
  HeaderTitleGroup,
  HeaderIcon,
  PanelTitle,
  CollapseButton,
  TagRow,
  StyledTag,
  ContentWrapper,
  EmptyState,
  SectionHeader,
  SectionTitle,
  SectionCard,
  InlineField,
  LabelText,
  ValueText,
  MonospaceValue,
  SectionDivider,
  Section,
  StatusTag,
  AlertWrapper,
  VolumeDescription,
  VolumeList,
  Stack,
  ServicesList,
  ServiceCard,
  ServiceHeader,
  ServiceMetaGrid,
  ServiceMetaItem,
  ServiceMetaLabel,
  ServiceMetaValue,
  DiskUsageMeta,
  PathsCard,
  ActivityCard,
  ActivityMetrics,
} from './styles'
import { IconWrapper } from '@/components/ui'

interface RepositoryDetailPanelProps {
  repository: Repository | null
  visible: boolean
  onClose: () => void
  splitView?: boolean
}

interface RepositoryVaultData {
  name: string
  size: number
  size_human: string
  modified: number
  modified_human: string
  image_path: string
  mounted: boolean
  mount_path: string
  accessible: boolean
  disk_space?: {
    total: string
    used: string
    available: string
    use_percent: string
  }
  has_rediaccfile: boolean
  docker_running: boolean
  container_count: number
  has_services: boolean
  service_count: number
  total_volumes?: number
  internal_volumes?: number
  external_volumes?: number
  external_volume_names?: string[]
  volume_status?: 'safe' | 'warning' | 'none'
}

interface ServiceData {
  name: string
  active_state: string
  memory_human?: string
  main_pid?: number
  uptime_human?: string
  restarts?: number
}

interface RepositoryPanelData {
  machine: any
  repositoryData: RepositoryVaultData
  systemData?: any
  services: ServiceData[]
}

export const RepositoryDetailPanel: React.FC<RepositoryDetailPanelProps> = ({
  repository,
  visible,
  onClose,
  splitView = false,
}) => {
  const { t } = useTranslation(['resources', 'common', 'machines'])
  const { data: machines = [] } = useMachines(repository?.teamName)

  const repositoryData = useMemo<RepositoryPanelData | null>(() => {
    if (!repository || !machines.length) return null

    for (const machine of machines) {
      if (!machine.vaultStatus) continue

      try {
        const trimmedStatus = machine.vaultStatus.trim()
        if (trimmedStatus.startsWith('jq:') || trimmedStatus.startsWith('error:') || !trimmedStatus.startsWith('{')) {
          continue
        }

        const vaultStatusData = JSON.parse(trimmedStatus)

        if (vaultStatusData.status === 'completed' && vaultStatusData.result) {
          let cleanedResult = vaultStatusData.result
          const jsonEndMatch = cleanedResult.match(/(\}[\s\n]*$)/)
          if (jsonEndMatch) {
            const lastBraceIndex = cleanedResult.lastIndexOf('}')
            if (lastBraceIndex < cleanedResult.length - 10) {
              cleanedResult = cleanedResult.substring(0, lastBraceIndex + 1)
            }
          }

          const newlineIndex = cleanedResult.indexOf('\njq:')
          if (newlineIndex > 0) {
            cleanedResult = cleanedResult.substring(0, newlineIndex)
          }

          const result = JSON.parse(cleanedResult.trim())

          if (Array.isArray(result.repositories)) {
            const repoData = result.repositories.find((r: RepositoryVaultData) => {
              return r.name === repository.repositoryName || r.name === repository.repositoryGuid
            })

            if (repoData) {
              const servicesForRepo: ServiceData[] = []

              if (Array.isArray(result.services)) {
                result.services.forEach((service: any) => {
                  if (service.repository === repoData.name || service.repository === repository.repositoryGuid) {
                    servicesForRepo.push(service)
                    return
                  }

                  const serviceName = service.service_name || service.unit_file || ''
                  const guidMatch = serviceName.match(/rediacc_([0-9a-f-]{36})_/)
                  if (guidMatch && (guidMatch[1] === repository.repositoryGuid || guidMatch[1] === repoData.name)) {
                    servicesForRepo.push(service)
                  }
                })
              }

              return {
                machine,
                repositoryData: repoData,
                systemData: result.system,
                services: servicesForRepo,
              }
            }
          }
        }
      } catch (error) {
        console.error('Error parsing vault status:', error)
      }
    }

    return null
  }, [repository, machines])

  useEffect(() => {
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && visible) {
        onClose()
      }
    }

    if (visible) {
      document.addEventListener('keydown', handleEscape)
    }

    return () => {
      document.removeEventListener('keydown', handleEscape)
    }
  }, [visible, onClose])

  if (!repository || !visible) return null

  return (
    <PanelWrapper $splitView={splitView} $visible={visible} data-testid="repo-detail-panel">
      <StickyHeader>
        <HeaderRow>
          <HeaderTitleGroup>
            <HeaderIcon />
            <PanelTitle level={4} data-testid={`repo-detail-title-${repository.repositoryName}`}>
              {repository.repositoryName}
            </PanelTitle>
          </HeaderTitleGroup>
          <CollapseButton
            type="text"
            icon={<DoubleRightOutlined />}
            onClick={onClose}
            data-testid="repo-detail-collapse"
            aria-label="Collapse panel"
          />
        </HeaderRow>

        <TagRow>
          <StyledTag $variant="team" icon={<AppstoreOutlined />} data-testid={`repo-detail-team-tag-${repository.repositoryName}`}>
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
          <StyledTag $variant="version" data-testid={`repo-detail-vault-version-tag-${repository.repositoryName}`}>
            {t('resources:repositories.vaultVersion')}: {repository.vaultVersion}
          </StyledTag>
        </TagRow>
      </StickyHeader>

      <ContentWrapper data-testid="repo-detail-content">
        {!repositoryData ? (
          <EmptyState
            description={t('resources:repositories.noRepositoryData')}
            data-testid="repo-detail-empty-state"
          />
        ) : (
          <>
            <RepositoryInfoSection repository={repository} panelData={repositoryData} t={t} />
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
  )
}

interface SectionProps {
  repository: Repository
  panelData: RepositoryPanelData
  t: TFunction<'resources' | 'common' | 'machines'>
}

const RepositoryInfoSection: React.FC<SectionProps> = ({ repository, panelData, t }) => {
  const { repositoryData } = panelData

  return (
    <Section data-testid="repo-detail-info-section">
      <SectionHeader>
        <IconWrapper $color="var(--color-success)" $size="lg">
          <FolderOutlined />
        </IconWrapper>
        <SectionTitle level={5}>{t('resources:repositories.repositoryInfo')}</SectionTitle>
      </SectionHeader>

      <SectionCard size="small" data-testid="repo-detail-info-card">
        <Stack>
          <InlineField>
            <LabelText>{t('resources:repositories.repositoryGuid')}:</LabelText>
            <MonospaceValue copyable data-testid={`repo-detail-guid-${repository.repositoryName}`}>
              {repository.repositoryGuid}
            </MonospaceValue>
          </InlineField>

          <InlineField>
            <LabelText>{t('resources:repositories.status')}:</LabelText>
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
          </InlineField>

          {repositoryData.has_rediaccfile && (
            <InlineField>
              <LabelText>{t('resources:repositories.rediaccfile')}:</LabelText>
              <StatusTag $tone="info" data-testid={`repo-detail-rediaccfile-${repository.repositoryName}`}>
                {t('resources:repositories.hasRediaccfile')}
              </StatusTag>
            </InlineField>
          )}

          {repositoryData.docker_running &&
            repositoryData.volume_status &&
            repositoryData.volume_status !== 'none' && (
              <InlineField>
                <LabelText>Docker Volumes:</LabelText>
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
                    {repositoryData.external_volumes} External, {repositoryData.internal_volumes} Internal
                  </StatusTag>
                )}
              </InlineField>
            )}
        </Stack>
      </SectionCard>
    </Section>
  )
}

const ExternalVolumeWarning: React.FC<SectionProps> = ({ repository, panelData }) => {
  const { repositoryData } = panelData

  if (
    repositoryData.volume_status !== 'warning' ||
    !repositoryData.external_volume_names ||
    repositoryData.external_volume_names.length === 0
  ) {
    return null
  }

  return (
    <AlertWrapper
      type="warning"
      showIcon
      icon={<WarningOutlined />}
      message="External Docker Volumes Detected"
      description={
        <VolumeDescription>
          <ValueText>The following volumes are stored outside the repository:</ValueText>
          <VolumeList>
            {repositoryData.external_volume_names.map((vol) => (
              <li key={vol}>
                <ValueText code>{vol}</ValueText>
              </li>
            ))}
          </VolumeList>
          <ValueText type="secondary">
            <strong>Warning:</strong> If this repository is cloned, these volumes will be orphaned. Use bind mounts to{' '}
            <ValueText code>$REPO_PATH</ValueText> instead.
          </ValueText>
        </VolumeDescription>
      }
      data-testid={`repo-detail-volume-warning-alert-${repository.repositoryName}`}
    />
  )
}

const StorageSection: React.FC<SectionProps> = ({ repository, panelData, t }) => {
  const { repositoryData } = panelData
  const diskPercent = repositoryData.disk_space
    ? parseInt(repositoryData.disk_space.use_percent, 10)
    : 0

  return (
    <Section>
      <SectionDivider data-testid="repo-detail-storage-divider">
        <IconWrapper $color="var(--color-info)">
          <InfoCircleOutlined />
        </IconWrapper>
        {t('resources:repositories.storageInfo')}
      </SectionDivider>

      <Row gutter={[16, 16]}>
        <Col span={24}>
          <SectionCard size="small" data-testid={`repo-detail-storage-info-card-${repository.repositoryName}`}>
            <Stack>
              <InlineField>
                <LabelText>{t('resources:repositories.imageSize')}:</LabelText>
                <ValueText>{repositoryData.size_human}</ValueText>
              </InlineField>
              <InlineField>
                <LabelText>{t('resources:repositories.lastModified')}:</LabelText>
                <ValueText>{repositoryData.modified_human}</ValueText>
              </InlineField>
            </Stack>
          </SectionCard>
        </Col>

        {repositoryData.mounted && repositoryData.disk_space && (
          <Col span={24}>
            <SectionCard size="small" data-testid={`repo-detail-disk-usage-card-${repository.repositoryName}`}>
              <Stack>
                <InlineField>
                  <Space>
                    <IconWrapper $color="var(--color-success)">
                      <DatabaseOutlined />
                    </IconWrapper>
                    <ValueText strong>{t('resources:repositories.diskUsage')}</ValueText>
                  </Space>
                </InlineField>
                <ValueText>
                  {repositoryData.disk_space.used} / {repositoryData.disk_space.total}
                </ValueText>
                <Progress
                  percent={diskPercent}
                  status={diskPercent > 90 ? 'exception' : 'normal'}
                  strokeColor={diskPercent > 90 ? 'var(--color-error)' : 'var(--color-success)'}
                  data-testid={`repo-detail-disk-usage-progress-${repository.repositoryName}`}
                />
                <DiskUsageMeta>
                  {t('resources:repositories.available')}: {repositoryData.disk_space.available}
                </DiskUsageMeta>
              </Stack>
            </SectionCard>
          </Col>
        )}
      </Row>
    </Section>
  )
}

const FilePathsSection: React.FC<SectionProps> = ({ repository, panelData, t }) => {
  const { repositoryData } = panelData

  return (
    <Section>
      <SectionDivider data-testid="repo-detail-file-paths-divider">
        <IconWrapper $color="var(--color-primary)">
          <FolderOutlined />
        </IconWrapper>
        {t('resources:repositories.filePaths')}
      </SectionDivider>

      <PathsCard size="small" data-testid={`repo-detail-file-paths-card-${repository.repositoryName}`}>
        <Stack>
          <InlineField>
            <LabelText>{t('resources:repositories.imagePath')}:</LabelText>
            <MonospaceValue
              copyable={{ text: repositoryData.image_path }}
              data-testid={`repo-detail-image-path-${repository.repositoryName}`}
            >
              {abbreviatePath(repositoryData.image_path, 45)}
            </MonospaceValue>
          </InlineField>
          {repositoryData.mount_path && (
            <InlineField>
              <LabelText>{t('resources:repositories.mountPath')}:</LabelText>
              <MonospaceValue
                copyable={{ text: repositoryData.mount_path }}
                data-testid={`repo-detail-mount-path-${repository.repositoryName}`}
              >
                {abbreviatePath(repositoryData.mount_path, 45)}
              </MonospaceValue>
            </InlineField>
          )}
        </Stack>
      </PathsCard>
    </Section>
  )
}

const ActivitySection: React.FC<SectionProps> = ({ repository, panelData, t }) => {
  const { repositoryData } = panelData

  return (
    <Section>
      <SectionDivider data-testid="repo-detail-activity-divider">
        <IconWrapper $color="var(--color-info)">
          <FieldTimeOutlined />
        </IconWrapper>
        {t('resources:repositories.activity')}
      </SectionDivider>

      <ActivityCard size="small" data-testid={`repo-detail-activity-card-${repository.repositoryName}`}>
        <ActivityMetrics>
          {repositoryData.docker_running && (
            <InlineField>
              <LabelText>{t('resources:repositories.containers')}:</LabelText>
              <ValueText>{repositoryData.container_count}</ValueText>
            </InlineField>
          )}
          {repositoryData.has_services && (
            <InlineField>
              <LabelText>{t('resources:repositories.services')}:</LabelText>
              <ValueText>{repositoryData.service_count}</ValueText>
            </InlineField>
          )}
        </ActivityMetrics>
      </ActivityCard>
    </Section>
  )
}

const ServicesSection: React.FC<SectionProps> = ({ repository, panelData, t }) => (
  <Section>
    <SectionDivider data-testid="repo-detail-services-divider">
      <IconWrapper $color="var(--color-primary)">
        <CodeOutlined />
      </IconWrapper>
      {t('resources:repositories.servicesSection')}
    </SectionDivider>

    <ServicesList data-testid="repo-detail-services-list">
      {panelData.services.map((service, index) => {
        const state: 'active' | 'failed' | 'other' =
          service.active_state === 'active'
            ? 'active'
            : service.active_state === 'failed'
              ? 'failed'
              : 'other'

        return (
          <ServiceCard
            key={`${service.name}-${index}`}
            size="small"
            $state={state}
            data-testid={`repo-detail-service-card-${repository.repositoryName}-${service.name}`}
          >
            <Row gutter={[16, 8]}>
              <Col span={24}>
                <ServiceHeader>
                  <ValueText strong data-testid={`repo-detail-service-name-${repository.repositoryName}-${service.name}`}>
                    {service.name}
                  </ValueText>
                  <StatusTag
                    $tone={state === 'active' ? 'success' : state === 'failed' ? 'error' : 'neutral'}
                    data-testid={`repo-detail-service-status-${repository.repositoryName}-${service.name}`}
                  >
                    {service.active_state}
                  </StatusTag>
                </ServiceHeader>
              </Col>
              {(service.memory_human || service.main_pid || service.uptime_human || service.restarts !== undefined) && (
                <Col span={24}>
                  <ServiceMetaGrid>
                    {service.memory_human && (
                      <ServiceMetaItem>
                        <ServiceMetaLabel>Memory</ServiceMetaLabel>
                        <ServiceMetaValue>{service.memory_human}</ServiceMetaValue>
                      </ServiceMetaItem>
                    )}
                    {service.main_pid && (
                      <ServiceMetaItem>
                        <ServiceMetaLabel>PID</ServiceMetaLabel>
                        <ServiceMetaValue>{service.main_pid}</ServiceMetaValue>
                      </ServiceMetaItem>
                    )}
                    {service.uptime_human && (
                      <ServiceMetaItem>
                        <ServiceMetaLabel>Uptime</ServiceMetaLabel>
                        <ServiceMetaValue>{service.uptime_human}</ServiceMetaValue>
                      </ServiceMetaItem>
                    )}
                    {service.restarts !== undefined && (
                      <ServiceMetaItem>
                        <ServiceMetaLabel>Restarts</ServiceMetaLabel>
                        <ServiceMetaValue>{service.restarts}</ServiceMetaValue>
                      </ServiceMetaItem>
                    )}
                  </ServiceMetaGrid>
                </Col>
              )}
            </Row>
          </ServiceCard>
        )
      })}
    </ServicesList>
  </Section>
)
