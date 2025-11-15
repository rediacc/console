import React, { useMemo } from 'react'
import { Progress, Tag } from 'antd'
import {
  DoubleRightOutlined,
  ApiOutlined,
  AppstoreOutlined,
  CloudServerOutlined,
  WifiOutlined,
  HddOutlined,
  FolderOutlined,
  PlayCircleOutlined,
  PauseCircleOutlined,
  ContainerOutlined,
} from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import {
  DetailPanel,
  Header,
  HeaderTop,
  TitleGroup,
  PanelTitle,
  IconWrapper,
  CollapseButton,
  TagGroup,
  PanelContent,
  SectionHeader,
  SectionTitle,
  SectionCard,
  FieldList,
  FieldRow,
  FieldLabel,
  FieldValue,
  FieldValueStrong,
  FieldValueMonospace,
  SectionDivider,
  DividerLabel,
  MetricsGrid,
  MetricCard,
  MetricLabel,
  MetricValue,
  SectionStack,
  InlineText,
  SubduedText,
} from './styles'

interface ContainerData {
  id: string
  name: string
  image: string
  command: string
  created: string
  status: string
  state: string
  ports: string
  port_mappings?: Array<{
    host?: string
    host_port?: string
    container_port: string
    protocol: string
  }>
  labels: string
  mounts: string
  networks: string
  size: string
  repository: string
  cpu_percent: string
  memory_usage: string
  memory_percent: string
  net_io: string
  block_io: string
  pids: string
}

interface ContainerDetailPanelProps {
  container: ContainerData | null
  visible: boolean
  onClose: () => void
  splitView?: boolean
}

export const ContainerDetailPanel: React.FC<ContainerDetailPanelProps> = ({
  container,
  visible,
  onClose,
  splitView = false,
}) => {
  const { t } = useTranslation(['resources', 'common'])

  const resourceUsage = useMemo(() => {
    if (!container) return null

    const cpuValue = parseFloat(container.cpu_percent?.replace('%', '') || '0')
    const memoryParts = container.memory_usage?.split(' / ') || []
    const memoryUsed = memoryParts[0] || '0'
    const memoryTotal = memoryParts[1] || '0'
    const memoryPercent = parseFloat(container.memory_percent?.replace('%', '') || '0')
    const netParts = container.net_io?.split(' / ') || []
    const netIn = netParts[0] || '0'
    const netOut = netParts[1] || '0'
    const blockParts = container.block_io?.split(' / ') || []
    const blockRead = blockParts[0] || '0'
    const blockWrite = blockParts[1] || '0'

    return {
      cpu: cpuValue,
      memoryUsed,
      memoryTotal,
      memoryPercent,
      netIn,
      netOut,
      blockRead,
      blockWrite,
      pids: parseInt(container.pids || '0', 10),
    }
  }, [container])

  if (!visible || !container) {
    return null
  }

  const isPlugin = container.name?.startsWith('plugin-')
  const pluginName = isPlugin ? container.name.replace('plugin-', '') : null
  const cpuWarning = (resourceUsage?.cpu || 0) > 80
  const memoryWarning = (resourceUsage?.memoryPercent || 0) > 90

  const renderPortMappings = () => {
    if (container.port_mappings && container.port_mappings.length > 0) {
      return container.port_mappings.map((mapping, index) => {
        const hostBinding = mapping.host ? `${mapping.host}:${mapping.host_port}` : mapping.host_port
        const tagText = hostBinding
          ? `${hostBinding} → ${mapping.container_port}/${mapping.protocol}`
          : `${mapping.container_port}/${mapping.protocol}`

        return (
          <Tag key={`${mapping.container_port}-${mapping.protocol}-${index}`}>
            {tagText}
          </Tag>
        )
      })
    }

    if (container.ports) {
      return (
        <InlineText data-testid="container-detail-ports-text">
          {container.ports}
        </InlineText>
      )
    }

    return null
  }

  return (
    <DetailPanel
      $splitView={splitView}
      $visible={visible}
      className="container-detail-panel"
      data-testid="container-detail-panel"
    >
      <Header data-testid="container-detail-header">
        <HeaderTop>
          <TitleGroup>
            <IconWrapper $variant={isPlugin ? 'plugin' : 'primary'}>
              {isPlugin ? <ApiOutlined /> : <AppstoreOutlined />}
            </IconWrapper>
            <PanelTitle data-testid="container-detail-title">
              {isPlugin ? pluginName : container.name}
            </PanelTitle>
          </TitleGroup>
          <CollapseButton
            type="text"
            icon={<DoubleRightOutlined />}
            onClick={onClose}
            data-testid="container-detail-collapse"
            aria-label="Collapse Panel"
          />
        </HeaderTop>
        <TagGroup>
          <Tag
            color={container.state === 'running' ? 'success' : 'default'}
            icon={container.state === 'running' ? <PlayCircleOutlined /> : <PauseCircleOutlined />}
            data-testid="container-detail-state-tag"
          >
            {container.state}
          </Tag>
          <Tag color="blue" icon={<FolderOutlined />} data-testid="container-detail-repo-tag">
            {t('resources:containers.repositoryLabel', 'Repository')}: {container.repository}
          </Tag>
        </TagGroup>
      </Header>

      <PanelContent data-testid="container-detail-content">
        <SectionStack>
          <SectionHeader data-testid="container-detail-info-section">
            <IconWrapper $variant="primary" $size="md">
              {isPlugin ? <ApiOutlined /> : <ContainerOutlined />}
            </IconWrapper>
            <SectionTitle>{t('resources:containers.containerInfo')}</SectionTitle>
          </SectionHeader>

          <SectionCard data-testid="container-detail-basic-info">
            <FieldList>
              <FieldRow>
                <FieldLabel>{t('resources:containers.containerID')}:</FieldLabel>
                <FieldValueMonospace copyable data-testid="container-detail-id">
                  {container.id}
                </FieldValueMonospace>
              </FieldRow>
              <FieldRow>
                <FieldLabel>{t('resources:containers.image')}:</FieldLabel>
                <FieldValue data-testid="container-detail-image">{container.image}</FieldValue>
              </FieldRow>
              <FieldRow>
                <FieldLabel>{t('resources:containers.status')}:</FieldLabel>
                <FieldValue data-testid="container-detail-status">{container.status}</FieldValue>
              </FieldRow>
              <FieldRow>
                <FieldLabel>{t('resources:containers.created')}:</FieldLabel>
                <FieldValue data-testid="container-detail-created">{container.created}</FieldValue>
              </FieldRow>
            </FieldList>
          </SectionCard>
        </SectionStack>

        <SectionDivider>
          <DividerLabel>
            <CloudServerOutlined />
            {t('resources:containers.resourceUsage')}
          </DividerLabel>
        </SectionDivider>

        <MetricsGrid>
          <MetricCard data-testid="container-detail-cpu-card">
            <MetricLabel>{t('resources:containers.cpuUsage')}</MetricLabel>
            <MetricValue $isWarning={cpuWarning}>
              {resourceUsage?.cpu?.toFixed(2) ?? '0'}%
            </MetricValue>
            <Progress
              percent={resourceUsage?.cpu || 0}
              showInfo={false}
              status={cpuWarning ? 'exception' : 'normal'}
            />
          </MetricCard>
          <MetricCard data-testid="container-detail-memory-card">
            <MetricLabel>{t('resources:containers.memoryUsage')}</MetricLabel>
            <MetricValue $isWarning={memoryWarning}>
              {resourceUsage ? `${resourceUsage.memoryUsed} / ${resourceUsage.memoryTotal}` : '-'}
            </MetricValue>
            <Progress
              percent={resourceUsage?.memoryPercent || 0}
              status={memoryWarning ? 'exception' : 'normal'}
            />
          </MetricCard>
          <MetricCard data-testid="container-detail-network-card">
            <MetricLabel>{t('resources:containers.networkIO')}</MetricLabel>
            <InlineText>
              <WifiOutlined /> {resourceUsage?.netIn} / {resourceUsage?.netOut}
            </InlineText>
          </MetricCard>
          <MetricCard data-testid="container-detail-block-io-card">
            <MetricLabel>{t('resources:containers.blockIO')}</MetricLabel>
            <InlineText>
              <HddOutlined /> {resourceUsage?.blockRead} / {resourceUsage?.blockWrite}
            </InlineText>
          </MetricCard>
        </MetricsGrid>

        <SectionCard data-testid="container-detail-runtime">
          <FieldList>
            {container.port_mappings || container.ports ? (
              <FieldRow>
                <FieldLabel>{t('resources:containers.ports')}:</FieldLabel>
                <FieldValueStrong>{renderPortMappings()}</FieldValueStrong>
              </FieldRow>
            ) : null}
            <FieldRow>
              <FieldLabel>{t('resources:containers.networks')}:</FieldLabel>
              <FieldValue>
                <Tag color="purple" data-testid="container-detail-network-tag">
                  {container.networks}
                </Tag>
              </FieldValue>
            </FieldRow>
            <FieldRow>
              <FieldLabel>{t('resources:containers.size')}:</FieldLabel>
              <FieldValue data-testid="container-detail-size">{container.size}</FieldValue>
            </FieldRow>
            <FieldRow>
              <FieldLabel>{t('resources:containers.processes')}:</FieldLabel>
              <FieldValue>
                <Tag data-testid="container-detail-pids">
                  {resourceUsage?.pids || 0} {t('resources:containers.pids')}
                </Tag>
              </FieldValue>
            </FieldRow>
          </FieldList>
        </SectionCard>

        <SectionDivider>
          <DividerLabel>
            <FolderOutlined />
            {t('resources:containers.environment')}
          </DividerLabel>
        </SectionDivider>

        <SectionCard data-testid="container-detail-environment">
          <SectionStack>
            <div>
              <SubduedText>{t('resources:containers.mounts')}:</SubduedText>
              <FieldValueMonospace data-testid="container-detail-mounts">
                {container.mounts}
              </FieldValueMonospace>
            </div>
            {container.labels && (
              <div>
                <SubduedText>{t('resources:containers.labels')}:</SubduedText>
                <FieldValueMonospace data-testid="container-detail-labels">
                  {container.labels}
                </FieldValueMonospace>
              </div>
            )}
          </SectionStack>
        </SectionCard>
      </PanelContent>
    </DetailPanel>
  )
}
