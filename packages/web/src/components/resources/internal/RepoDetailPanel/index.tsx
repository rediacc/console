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
import type { Repo } from '@/api/queries/repos'
import type { Machine } from '@/types'
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

interface RepoDetailPanelProps {
  repo: Repo | null
  visible: boolean
  onClose: () => void
  splitView?: boolean
}

interface RepoVaultData {
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
  repo?: string
  service_name?: string
  unit_file?: string
}

interface RepoPanelData {
  machine: Machine
  repoData: RepoVaultData
  systemData?: Record<string, unknown>
  services: ServiceData[]
}

export const RepoDetailPanel: React.FC<RepoDetailPanelProps> = ({
  repo,
  visible,
  onClose,
  splitView = false,
}) => {
  const { t } = useTranslation(['resources', 'common', 'machines'])
  const { data: machines = [] } = useMachines(repo?.teamName)

  const repoData = useMemo<RepoPanelData | null>(() => {
    if (!repo || !machines.length) return null

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

          if (Array.isArray(result.repos)) {
            const repoData = result.repos.find((r: RepoVaultData) => {
              return r.name === repo.repoName || r.name === repo.repoGuid
            })

            if (repoData) {
              const servicesForRepo: ServiceData[] = []

              if (Array.isArray(result.services)) {
                result.services.forEach((service: ServiceData) => {
                  if (service.repo === repoData.name || service.repo === repo.repoGuid) {
                    servicesForRepo.push(service)
                    return
                  }

                  const serviceName = service.service_name || service.unit_file || ''
                  const guidMatch = serviceName.match(/rediacc_([0-9a-f-]{36})_/)
                  if (guidMatch && (guidMatch[1] === repo.repoGuid || guidMatch[1] === repoData.name)) {
                    servicesForRepo.push(service)
                  }
                })
              }

              return {
                machine,
                repoData: repoData,
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
  }, [repo, machines])

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

  if (!repo || !visible) return null

  return (
    <PanelWrapper $splitView={splitView} $visible={visible} data-testid="repo-detail-panel">
      <StickyHeader>
        <HeaderRow>
          <HeaderTitleGroup>
            <HeaderIcon />
            <PanelTitle level={4} data-testid={`repo-detail-title-${repo.repoName}`}>
              {repo.repoName}
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
          <StyledTag $variant="team" icon={<AppstoreOutlined />} data-testid={`repo-detail-team-tag-${repo.repoName}`}>
            {t('common:general.team')}: {repo.teamName}
          </StyledTag>
          {repoData && (
            <StyledTag
              $variant="machine"
              icon={<CloudServerOutlined />}
              data-testid={`repo-detail-machine-tag-${repo.repoName}`}
            >
              {t('machines:machine')}: {repoData.machine.machineName}
            </StyledTag>
          )}
          <StyledTag $variant="version" data-testid={`repo-detail-vault-version-tag-${repo.repoName}`}>
            {t('resources:repos.vaultVersion')}: {repo.vaultVersion}
          </StyledTag>
        </TagRow>
      </StickyHeader>

      <ContentWrapper data-testid="repo-detail-content">
        {!repoData ? (
          <EmptyState
            description={t('resources:repos.noRepoData')}
            data-testid="repo-detail-empty-state"
          />
        ) : (
          <>
            <RepoInfoSection repo={repo} panelData={repoData} t={t} />
            <ExternalVolumeWarning repo={repo} panelData={repoData} t={t} />
            <StorageSection repo={repo} panelData={repoData} t={t} />
            <FilePathsSection repo={repo} panelData={repoData} t={t} />
            {repoData.repoData.mounted && (
              <ActivitySection repo={repo} panelData={repoData} t={t} />
            )}
            {repoData.services.length > 0 && (
              <ServicesSection repo={repo} panelData={repoData} t={t} />
            )}
          </>
        )}
      </ContentWrapper>
    </PanelWrapper>
  )
}

interface SectionProps {
  repo: Repo
  panelData: RepoPanelData
  t: TFunction<'resources' | 'common' | 'machines'>
}

const RepoInfoSection: React.FC<SectionProps> = ({ repo, panelData, t }) => {
  const { repoData } = panelData

  return (
    <Section data-testid="repo-detail-info-section">
      <SectionHeader>
        <IconWrapper $color="var(--color-success)" $size="lg">
          <FolderOutlined />
        </IconWrapper>
        <SectionTitle level={5}>{t('resources:repos.repoInfo')}</SectionTitle>
      </SectionHeader>

      <SectionCard size="small" data-testid="repo-detail-info-card">
        <Stack>
          <InlineField>
            <LabelText>{t('resources:repos.repoGuid')}:</LabelText>
            <MonospaceValue copyable data-testid={`repo-detail-guid-${repo.repoName}`}>
              {repo.repoGuid}
            </MonospaceValue>
          </InlineField>

          <InlineField>
            <LabelText>{t('resources:repos.status')}:</LabelText>
            <Space>
              {repoData.mounted ? (
                <StatusTag
                  $tone="success"
                  icon={<CheckCircleOutlined />}
                  data-testid={`repo-detail-status-mounted-${repo.repoName}`}
                >
                  {t('resources:repos.mounted')}
                </StatusTag>
              ) : (
                <StatusTag
                  data-testid={`repo-detail-status-unmounted-${repo.repoName}`}
                  icon={<StopOutlined />}
                >
                  {t('resources:repos.notMounted')}
                </StatusTag>
              )}
              {repoData.accessible && (
                <StatusTag
                  $tone="success"
                  data-testid={`repo-detail-status-accessible-${repo.repoName}`}
                >
                  {t('resources:repos.accessible')}
                </StatusTag>
              )}
            </Space>
          </InlineField>

          {repoData.has_rediaccfile && (
            <InlineField>
              <LabelText>{t('resources:repos.rediaccfile')}:</LabelText>
              <StatusTag $tone="info" data-testid={`repo-detail-rediaccfile-${repo.repoName}`}>
                {t('resources:repos.hasRediaccfile')}
              </StatusTag>
            </InlineField>
          )}

          {repoData.docker_running &&
            repoData.volume_status &&
            repoData.volume_status !== 'none' && (
              <InlineField>
                <LabelText>Docker Volumes:</LabelText>
                {repoData.volume_status === 'safe' ? (
                  <StatusTag
                    $tone="success"
                    icon={<CheckCircleOutlined />}
                    data-testid={`repo-detail-volume-safe-${repo.repoName}`}
                  >
                    {repoData.internal_volumes} Safe Volume
                    {repoData.internal_volumes !== 1 ? 's' : ''}
                  </StatusTag>
                ) : (
                  <StatusTag
                    $tone="warning"
                    icon={<WarningOutlined />}
                    data-testid={`repo-detail-volume-warning-${repo.repoName}`}
                  >
                    {repoData.external_volumes} External, {repoData.internal_volumes} Internal
                  </StatusTag>
                )}
              </InlineField>
            )}
        </Stack>
      </SectionCard>
    </Section>
  )
}

const ExternalVolumeWarning: React.FC<SectionProps> = ({ repo, panelData }) => {
  const { repoData } = panelData

  if (
    repoData.volume_status !== 'warning' ||
    !repoData.external_volume_names ||
    repoData.external_volume_names.length === 0
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
          <ValueText>The following volumes are stored outside the repo:</ValueText>
          <VolumeList>
            {repoData.external_volume_names.map((vol) => (
              <li key={vol}>
                <ValueText code>{vol}</ValueText>
              </li>
            ))}
          </VolumeList>
          <ValueText type="secondary">
            <strong>Warning:</strong> If this repo is cloned, these volumes will be orphaned. Use bind mounts to{' '}
            <ValueText code>$REPO_PATH</ValueText> instead.
          </ValueText>
        </VolumeDescription>
      }
      data-testid={`repo-detail-volume-warning-alert-${repo.repoName}`}
    />
  )
}

const StorageSection: React.FC<SectionProps> = ({ repo, panelData, t }) => {
  const { repoData } = panelData
  const diskPercent = repoData.disk_space
    ? parseInt(repoData.disk_space.use_percent, 10)
    : 0

  return (
    <Section>
      <SectionDivider data-testid="repo-detail-storage-divider">
        <IconWrapper $color="var(--color-info)">
          <InfoCircleOutlined />
        </IconWrapper>
        {t('resources:repos.storageInfo')}
      </SectionDivider>

      <Row gutter={[16, 16]}>
        <Col span={24}>
          <SectionCard size="small" data-testid={`repo-detail-storage-info-card-${repo.repoName}`}>
            <Stack>
              <InlineField>
                <LabelText>{t('resources:repos.imageSize')}:</LabelText>
                <ValueText>{repoData.size_human}</ValueText>
              </InlineField>
              <InlineField>
                <LabelText>{t('resources:repos.lastModified')}:</LabelText>
                <ValueText>{repoData.modified_human}</ValueText>
              </InlineField>
            </Stack>
          </SectionCard>
        </Col>

        {repoData.mounted && repoData.disk_space && (
          <Col span={24}>
            <SectionCard size="small" data-testid={`repo-detail-disk-usage-card-${repo.repoName}`}>
              <Stack>
                <InlineField>
                  <Space>
                    <IconWrapper $color="var(--color-success)">
                      <DatabaseOutlined />
                    </IconWrapper>
                    <ValueText strong>{t('resources:repos.diskUsage')}</ValueText>
                  </Space>
                </InlineField>
                <ValueText>
                  {repoData.disk_space.used} / {repoData.disk_space.total}
                </ValueText>
                <Progress
                  percent={diskPercent}
                  status={diskPercent > 90 ? 'exception' : 'normal'}
                  strokeColor={diskPercent > 90 ? 'var(--color-error)' : 'var(--color-success)'}
                  data-testid={`repo-detail-disk-usage-progress-${repo.repoName}`}
                />
                <DiskUsageMeta>
                  {t('resources:repos.available')}: {repoData.disk_space.available}
                </DiskUsageMeta>
              </Stack>
            </SectionCard>
          </Col>
        )}
      </Row>
    </Section>
  )
}

const FilePathsSection: React.FC<SectionProps> = ({ repo, panelData, t }) => {
  const { repoData } = panelData

  return (
    <Section>
      <SectionDivider data-testid="repo-detail-file-paths-divider">
        <IconWrapper $color="var(--color-primary)">
          <FolderOutlined />
        </IconWrapper>
        {t('resources:repos.filePaths')}
      </SectionDivider>

      <PathsCard size="small" data-testid={`repo-detail-file-paths-card-${repo.repoName}`}>
        <Stack>
          <InlineField>
            <LabelText>{t('resources:repos.imagePath')}:</LabelText>
            <MonospaceValue
              copyable={{ text: repoData.image_path }}
              data-testid={`repo-detail-image-path-${repo.repoName}`}
            >
              {abbreviatePath(repoData.image_path, 45)}
            </MonospaceValue>
          </InlineField>
          {repoData.mount_path && (
            <InlineField>
              <LabelText>{t('resources:repos.mountPath')}:</LabelText>
              <MonospaceValue
                copyable={{ text: repoData.mount_path }}
                data-testid={`repo-detail-mount-path-${repo.repoName}`}
              >
                {abbreviatePath(repoData.mount_path, 45)}
              </MonospaceValue>
            </InlineField>
          )}
        </Stack>
      </PathsCard>
    </Section>
  )
}

const ActivitySection: React.FC<SectionProps> = ({ repo, panelData, t }) => {
  const { repoData } = panelData

  return (
    <Section>
      <SectionDivider data-testid="repo-detail-activity-divider">
        <IconWrapper $color="var(--color-info)">
          <FieldTimeOutlined />
        </IconWrapper>
        {t('resources:repos.activity')}
      </SectionDivider>

      <ActivityCard size="small" data-testid={`repo-detail-activity-card-${repo.repoName}`}>
        <ActivityMetrics>
          {repoData.docker_running && (
            <InlineField>
              <LabelText>{t('resources:repos.containers')}:</LabelText>
              <ValueText>{repoData.container_count}</ValueText>
            </InlineField>
          )}
          {repoData.has_services && (
            <InlineField>
              <LabelText>{t('resources:repos.services')}:</LabelText>
              <ValueText>{repoData.service_count}</ValueText>
            </InlineField>
          )}
        </ActivityMetrics>
      </ActivityCard>
    </Section>
  )
}

const ServicesSection: React.FC<SectionProps> = ({ repo, panelData, t }) => (
  <Section>
    <SectionDivider data-testid="repo-detail-services-divider">
      <IconWrapper $color="var(--color-primary)">
        <CodeOutlined />
      </IconWrapper>
      {t('resources:repos.servicesSection')}
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
            data-testid={`repo-detail-service-card-${repo.repoName}-${service.name}`}
          >
            <Row gutter={[16, 8]}>
              <Col span={24}>
                <ServiceHeader>
                  <ValueText strong data-testid={`repo-detail-service-name-${repo.repoName}-${service.name}`}>
                    {service.name}
                  </ValueText>
                  <StatusTag
                    $tone={state === 'active' ? 'success' : state === 'failed' ? 'error' : 'neutral'}
                    data-testid={`repo-detail-service-status-${repo.repoName}-${service.name}`}
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

