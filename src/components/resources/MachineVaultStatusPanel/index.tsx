import React, { useEffect, useMemo, useState } from 'react'
import { Row, Col, Progress } from 'antd'
import type { ListProps } from 'antd'
import {
  DoubleRightOutlined,
  DesktopOutlined,
  DatabaseOutlined,
  GlobalOutlined,
  HddOutlined,
  WifiOutlined,
  ApiOutlined,
  ContainerOutlined,
  InfoCircleOutlined,
  AppstoreOutlined,
  CodeOutlined,
  CompassOutlined,
} from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import type { Machine } from '@/types'
import { getLocalizedRelativeTime, formatTimestampAsIs } from '@/utils/timeUtils'
import { calculateResourcePercent } from '@/utils/sizeUtils'
import { abbreviatePath } from '@/utils/pathUtils'
import AuditTraceModal from '@/components/common/AuditTraceModal'
import { DistributedStorageSection } from '../DistributedStorageSection'
import { featureFlags } from '@/config/featureFlags'
import {
  PanelWrapper,
  StickyHeader,
  HeaderRow,
  HeaderTitleGroup,
  HeaderIcon,
  MachineName,
  CollapseButton,
  TagRow,
  StyledTag,
  QueueBadge,
  TimestampWrapper,
  Timestamp,
  ContentWrapper,
  EmptyState,
  SectionDivider,
  SectionHeader,
  SectionTitle,
  IconWrapper,
  SectionBlock,
  InfoCard,
  FullWidthStack,
  InlineField,
  FieldLabel,
  FieldValue,
  FieldValueMonospace,
  FieldValueStrong,
  SecondaryText,
  MetricCard,
  CardHeader,
  CardTitle,
  CardTagGroup,
  StyledList,
  ListCard,
  CardBodyStack,
  KeyValueRow,
  IndentedBlock,
  PartitionRow,
  StatusTag,
  AddressTag,
} from './styles'

interface MachineVaultStatusPanelProps {
  machine: Machine | null
  visible: boolean
  onClose: () => void
  splitView?: boolean
}

interface SystemInfo {
  hostname: string
  kernel: string
  os_name: string
  uptime: string
  system_time: number
  system_time_human: string
  timezone: string
  cpu_count: number
  cpu_model: string
  memory: {
    total: string
    used: string
    available: string
  }
  disk: {
    total: string
    used: string
    available: string
    use_percent: string
  }
  datastore: {
    path: string
    total: string
    used: string
    available: string
    use_percent: string
  }
}

interface NetworkInterface {
  name: string
  state: string
  mac_address: string
  mtu: number
  ipv4_addresses: string[]
  ipv6_addresses: string[]
  default_gateway: string | null
}

interface VaultNetwork {
  default_gateway?: string
  default_interface?: string
  interfaces: NetworkInterface[]
}

interface BlockDevicePartition {
  name: string
  path: string
  size_bytes: number
  size_human: string
  filesystem: string | null
  mountpoint: string | null
}

interface BlockDevice {
  name: string
  path: string
  size_bytes: number
  size_human: string
  model: string
  serial: string | null
  type: string
  discard_granularity: number
  physical_sector_size: number
  logical_sector_size: number
  partitions: BlockDevicePartition[]
}

interface Container {
  id: string
  name: string
  image: string
  command: string
  created: string
  status: string
  state: string
  ports: string
  cpu_percent?: string
  memory_usage?: string
  memory_percent?: string
  net_io?: string
  block_io?: string
  pids?: string
}

interface VaultData {
  system?: SystemInfo
  network?: VaultNetwork
  block_devices?: BlockDevice[]
  system_containers?: Container[]
}

interface AuditTraceState {
  open: boolean
  entityType: string | null
  entityIdentifier: string | null
  entityName?: string
}

export const MachineVaultStatusPanel: React.FC<MachineVaultStatusPanelProps> = ({
  machine,
  visible,
  onClose,
  splitView = false,
}) => {
  const { t } = useTranslation(['machines', 'resources', 'common', 'distributedStorage'])
  const [auditTraceModal, setAuditTraceModal] = useState<AuditTraceState>({
    open: false,
    entityType: null,
    entityIdentifier: null,
  })

  const vaultData = useMemo<VaultData | null>(() => {
    if (!machine?.vaultStatus) return null

    try {
      const trimmed = machine.vaultStatus.trim()
      if (trimmed.startsWith('jq:') || trimmed.startsWith('error:') || !trimmed.startsWith('{')) {
        return null
      }

      const vaultStatusData = JSON.parse(trimmed)
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

        cleanedResult = cleanedResult.trim()
        return JSON.parse(cleanedResult)
      }
    } catch (err) {
      console.error('Error parsing vault status:', err)
    }

    return null
  }, [machine])

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

  if (!machine || !visible) {
    return null
  }

  const handleClose = () => {
    setAuditTraceModal({ open: false, entityType: null, entityIdentifier: null })
    onClose()
  }

  return (
    <>
      <PanelWrapper $splitView={splitView} $visible={visible}>
        <StickyHeader data-testid="vault-status-header">
          <HeaderRow>
            <HeaderTitleGroup>
              <HeaderIcon />
              <MachineName level={4} data-testid="vault-status-machine-name">
                {machine.machineName}
              </MachineName>
            </HeaderTitleGroup>
            <CollapseButton
              type="text"
              icon={<DoubleRightOutlined />}
              onClick={handleClose}
              data-testid="vault-status-collapse"
              aria-label="Collapse panel"
            />
          </HeaderRow>

          <TagRow>
            <StyledTag $variant="team" icon={<AppstoreOutlined />} data-testid="vault-status-team-tag">
              {t('common:general.team')}: {machine.teamName}
            </StyledTag>
            <StyledTag $variant="bridge" icon={<ApiOutlined />} data-testid="vault-status-bridge-tag">
              {t('machines:bridge')}: {machine.bridgeName}
            </StyledTag>
            {machine.regionName && (
              <StyledTag $variant="region" icon={<GlobalOutlined />} data-testid="vault-status-region-tag">
                {t('machines:region')}: {machine.regionName}
              </StyledTag>
            )}
            <QueueBadge count={machine.queueCount} data-testid="vault-status-queue-badge">
              <StyledTag $variant="queue">{t('machines:queueItems')}</StyledTag>
            </QueueBadge>
            <StyledTag $variant="version" data-testid="vault-status-version-tag">
              {t('machines:vaultVersion')}: {machine.vaultVersion}
            </StyledTag>
          </TagRow>

          {machine.vaultStatusTime && (
            <TimestampWrapper>
              <Timestamp
                title={formatTimestampAsIs(machine.vaultStatusTime, 'datetime')}
                data-testid="vault-status-last-updated"
              >
                {t('machines:lastUpdated')}: {getLocalizedRelativeTime(machine.vaultStatusTime, t)}
              </Timestamp>
            </TimestampWrapper>
          )}
        </StickyHeader>

        <ContentWrapper data-testid="vault-status-content">
          {!vaultData ? (
            <EmptyState description={t('machines:noVaultData')} data-testid="vault-status-empty" />
          ) : (
            <>
              {vaultData.system && (
                <>
                  <SystemInfoSection system={vaultData.system} t={t} />
                  <ResourceUsageSection system={vaultData.system} t={t} />
                </>
              )}

              {vaultData.network && (<NetworkSection network={vaultData.network as VaultNetwork} t={t} />)}

              {vaultData.block_devices && vaultData.block_devices.length > 0 && (
                <BlockDevicesSection devices={vaultData.block_devices as BlockDevice[]} t={t} />
              )}

              {vaultData.system_containers && vaultData.system_containers.length > 0 && (
                <SystemContainersSection containers={vaultData.system_containers} t={t} />
              )}

              {featureFlags.isEnabled('distributedStorage') && machine && (
                <SectionBlock data-testid="vault-status-distributed-storage">
                  <DistributedStorageSection
                    machine={machine}
                    onViewDetails={() =>
                      setAuditTraceModal({
                        open: true,
                        entityType: 'Machine',
                        entityIdentifier: machine.machineName,
                        entityName: machine.machineName,
                      })
                    }
                  />
                </SectionBlock>
              )}
            </>
          )}
        </ContentWrapper>
      </PanelWrapper>

      <AuditTraceModal
        open={auditTraceModal.open}
        onCancel={() => setAuditTraceModal({ open: false, entityType: null, entityIdentifier: null })}
        entityType={auditTraceModal.entityType}
        entityIdentifier={auditTraceModal.entityIdentifier}
        entityName={auditTraceModal.entityName}
      />
    </>
  )
}

interface SectionProps {
  t: TFunction
}

interface SystemInfoSectionProps extends SectionProps {
  system: SystemInfo
}

const SystemInfoSection: React.FC<SystemInfoSectionProps> = ({ system, t }) => (
  <SectionBlock>
    <SectionHeader>
      <IconWrapper $color="var(--color-primary)">
        <DesktopOutlined />
      </IconWrapper>
      <SectionTitle level={5} data-testid="vault-status-system-info-title">
        {t('resources:repositories.systemInfo')}
      </SectionTitle>
    </SectionHeader>

    <InfoCard size="small" data-testid="vault-status-system-info-card">
      <FullWidthStack>
        <InlineField>
          <FieldLabel>{t('resources:repositories.hostname')}:</FieldLabel>
          <FieldValue data-testid="vault-status-hostname">{system.hostname}</FieldValue>
        </InlineField>
        <InlineField>
          <FieldLabel>{t('resources:repositories.uptime')}:</FieldLabel>
          <FieldValue data-testid="vault-status-uptime">{system.uptime}</FieldValue>
        </InlineField>
        <InlineField>
          <FieldLabel>{t('resources:repositories.osName')}:</FieldLabel>
          <FieldValue data-testid="vault-status-os-name">{system.os_name}</FieldValue>
        </InlineField>
        <InlineField>
          <FieldLabel>{t('resources:repositories.kernel')}:</FieldLabel>
          <FieldValue data-testid="vault-status-kernel">{system.kernel}</FieldValue>
        </InlineField>
        <InlineField>
          <FieldLabel>{t('resources:repositories.cpu')}:</FieldLabel>
          <FieldValue data-testid="vault-status-cpu">
            {system.cpu_count} × {system.cpu_model}
          </FieldValue>
        </InlineField>
        <InlineField>
          <FieldLabel>{t('resources:repositories.systemTime')}:</FieldLabel>
          <FieldValue data-testid="vault-status-system-time">
            {system.system_time_human} ({system.timezone})
          </FieldValue>
        </InlineField>
      </FullWidthStack>
    </InfoCard>
  </SectionBlock>
)

interface ResourceUsageSectionProps extends SectionProps {
  system: SystemInfo
}

const ResourceUsageSection: React.FC<ResourceUsageSectionProps> = ({ system, t }) => {
  const memoryPercent = calculateResourcePercent(system.memory.used, system.memory.total) || 0
  const diskPercent = parseInt(system.disk.use_percent, 10) || 0
  const datastorePercent = parseInt(system.datastore.use_percent, 10) || 0

  const diskStroke = diskPercent > 90 ? 'var(--color-error)' : 'var(--color-warning)'
  const datastoreStroke = datastorePercent > 90 ? 'var(--color-error)' : 'var(--color-success)'

  return (
    <SectionBlock>
      <SectionDivider orientation="left">
        <IconWrapper $color="var(--color-info)">
          <InfoCircleOutlined />
        </IconWrapper>
        {t('resources:repositories.resourceUsage')}
      </SectionDivider>

      <Row gutter={[16, 16]}>
        <Col span={24} lg={8}>
          <MetricCard size="small" data-testid="vault-status-memory-card">
            <CardHeader>
              <IconWrapper $color="var(--color-info)">
                <DatabaseOutlined />
              </IconWrapper>
              <CardTitle level={5}>{t('resources:repositories.memory')}</CardTitle>
            </CardHeader>
            <Progress percent={Math.round(memoryPercent)} strokeColor="var(--color-info)" />
            <SecondaryText>
              {t('resources:repositories.used')}: {system.memory.used} / {system.memory.total}
            </SecondaryText>
            <SecondaryText>
              {t('resources:repositories.available')}: {system.memory.available}
            </SecondaryText>
          </MetricCard>
        </Col>

        <Col span={24} lg={8}>
          <MetricCard size="small" data-testid="vault-status-disk-card">
            <CardHeader>
              <IconWrapper $color="var(--color-warning)">
                <HddOutlined />
              </IconWrapper>
              <CardTitle level={5}>{t('resources:repositories.disk')}</CardTitle>
            </CardHeader>
            <Progress percent={diskPercent} strokeColor={diskStroke} />
            <SecondaryText>
              {t('resources:repositories.used')}: {system.disk.used} / {system.disk.total}
            </SecondaryText>
            <SecondaryText>
              {t('resources:repositories.available')}: {system.disk.available}
            </SecondaryText>
          </MetricCard>
        </Col>

        <Col span={24} lg={8}>
          <MetricCard size="small" data-testid="vault-status-datastore-card">
            <CardHeader>
              <IconWrapper $color="var(--color-success)">
                <DatabaseOutlined />
              </IconWrapper>
              <CardTitle level={5}>{t('resources:repositories.datastore')}</CardTitle>
            </CardHeader>
            {system.datastore.path && (
              <InlineField>
                <FieldLabel>{t('common:general.path')}:</FieldLabel>
                <FieldValueMonospace copyable={{ text: system.datastore.path }}>
                  {abbreviatePath(system.datastore.path, 40)}
                </FieldValueMonospace>
              </InlineField>
            )}
            <Progress percent={datastorePercent} strokeColor={datastoreStroke} />
            <SecondaryText>
              {t('resources:repositories.used')}: {system.datastore.used} / {system.datastore.total}
            </SecondaryText>
            <SecondaryText>
              {t('resources:repositories.available')}: {system.datastore.available}
            </SecondaryText>
          </MetricCard>
        </Col>
      </Row>
    </SectionBlock>
  )
}

interface NetworkSectionProps extends SectionProps {
  network: VaultNetwork
}

const NetworkSection: React.FC<NetworkSectionProps> = ({ network, t }) => {
  const interfaces = network.interfaces.filter(
    (iface) => iface.state !== 'unknown' && iface.name !== 'lo'
  )

  return (
    <SectionBlock>
      <SectionDivider orientation="left">
        <IconWrapper $color="var(--color-info)">
          <WifiOutlined />
        </IconWrapper>
        {t('resources:repositories.networkInfo')}
      </SectionDivider>

      {network.default_gateway && (
        <InfoCard size="small" data-testid="vault-status-gateway-card">
          <FullWidthStack>
            <InlineField>
              <FieldLabel>{t('resources:repositories.defaultGateway')}:</FieldLabel>
              <FieldValue data-testid="vault-status-gateway">{network.default_gateway}</FieldValue>
            </InlineField>
            {network.default_interface && (
              <InlineField>
                <FieldLabel>{t('resources:repositories.defaultInterface')}:</FieldLabel>
                <FieldValue data-testid="vault-status-interface">
                  {network.default_interface}
                </FieldValue>
              </InlineField>
            )}
          </FullWidthStack>
        </InfoCard>
      )}

      <StyledList
        dataSource={interfaces}
        data-testid="vault-status-network-list"
        renderItem={((
          iface: NetworkInterface,
        ) => (
          <ListCard size="small" data-testid={`vault-status-network-${iface.name}`}>
            <CardHeader>
              <HeaderTitleGroup>
                <IconWrapper $color="var(--color-info)">
                  <CompassOutlined />
                </IconWrapper>
                <FieldValueStrong data-testid={`vault-status-network-name-${iface.name}`}>
                  {iface.name}
                </FieldValueStrong>
              </HeaderTitleGroup>
              <StatusTag
                $tone={iface.state === 'UP' ? 'success' : 'default'}
                data-testid={`vault-status-network-state-${iface.name}`}
              >
                {iface.state}
              </StatusTag>
            </CardHeader>
            <CardBodyStack>
              {iface.ipv4_addresses.length > 0 && (
                <div>
                  <FieldLabel>{t('resources:repositories.ipAddresses')}:</FieldLabel>
                  <CardTagGroup>
                    {iface.ipv4_addresses.map((ip: string) => (
                      <AddressTag key={ip} data-testid={`vault-status-ip-${ip}`}>
                        {ip}
                      </AddressTag>
                    ))}
                  </CardTagGroup>
                </div>
              )}
              {iface.mac_address && iface.mac_address !== 'unknown' && (
                <KeyValueRow>
                  <FieldLabel>{t('resources:repositories.macAddress')}:</FieldLabel>
                  <FieldValue>{iface.mac_address}</FieldValue>
                </KeyValueRow>
              )}
              {iface.mtu > 0 && (
                <KeyValueRow>
                  <FieldLabel>MTU:</FieldLabel>
                  <FieldValue>{iface.mtu}</FieldValue>
                </KeyValueRow>
              )}
            </CardBodyStack>
          </ListCard>
        )) as ListProps<unknown>['renderItem']}
      />
    </SectionBlock>
  )
}

interface BlockDevicesSectionProps extends SectionProps {
  devices: BlockDevice[]
}

const BlockDevicesSection: React.FC<BlockDevicesSectionProps> = ({ devices, t }) => (
  <SectionBlock>
    <SectionDivider orientation="left">
      <IconWrapper $color="var(--color-warning)">
        <HddOutlined />
      </IconWrapper>
      {t('resources:repositories.blockDevices')}
    </SectionDivider>

    <StyledList
      dataSource={devices}
      data-testid="vault-status-block-devices-list"
      renderItem={((device: BlockDevice) => (
        <ListCard size="small" data-testid={`vault-status-block-device-${device.name}`}>
          <CardHeader>
            <HeaderTitleGroup>
              <IconWrapper $color="var(--color-warning)">
                <HddOutlined />
              </IconWrapper>
              <FieldValueStrong data-testid={`vault-status-device-path-${device.name}`}>
                {device.path}
              </FieldValueStrong>
            </HeaderTitleGroup>
            <CardTagGroup>
              <StatusTag data-testid={`vault-status-device-type-${device.name}`}>{device.type}</StatusTag>
              <StatusTag $tone="info" data-testid={`vault-status-device-size-${device.name}`}>
                {device.size_human}
              </StatusTag>
            </CardTagGroup>
          </CardHeader>

          <CardBodyStack>
            {device.model && device.model !== 'Unknown' && (
              <KeyValueRow>
                <FieldLabel>{t('resources:repositories.model')}:</FieldLabel>
                <FieldValue>{device.model}</FieldValue>
              </KeyValueRow>
            )}

            {device.partitions.length > 0 && (
              <div>
                <FieldLabel>{t('resources:repositories.partitions')}:</FieldLabel>
                <IndentedBlock>
                  {device.partitions.map((part: BlockDevicePartition) => (
                    <PartitionRow key={`${device.name}-${part.name}`}>
                      <CodeOutlined />
                      <SecondaryText as="span">
                        {part.name}: {part.size_human}
                        {part.filesystem && ` (${part.filesystem})`}
                        {part.mountpoint && ` • ${part.mountpoint}`}
                      </SecondaryText>
                    </PartitionRow>
                  ))}
                </IndentedBlock>
              </div>
            )}
          </CardBodyStack>
        </ListCard>
      )) as ListProps<unknown>['renderItem']}
    />
  </SectionBlock>
)

interface SystemContainersSectionProps extends SectionProps {
  containers: Container[]
}

const SystemContainersSection: React.FC<SystemContainersSectionProps> = ({ containers, t }) => (
  <SectionBlock>
    <SectionDivider orientation="left">
      <IconWrapper $color="var(--color-secondary)">
        <ContainerOutlined />
      </IconWrapper>
      {t('resources:repositories.systemContainers')}
    </SectionDivider>

    <StyledList
      dataSource={containers}
      data-testid="vault-status-containers-list"
      renderItem={((container: Container) => (
        <ListCard size="small" data-testid={`vault-status-container-${container.id}`}>
          <CardHeader>
            <HeaderTitleGroup>
              <IconWrapper $color="var(--color-secondary)">
                <ContainerOutlined />
              </IconWrapper>
              <FieldValueStrong data-testid={`vault-status-container-name-${container.id}`}>
                {container.name}
              </FieldValueStrong>
            </HeaderTitleGroup>
            <StatusTag
              $tone={container.state === 'running' ? 'success' : 'default'}
              data-testid={`vault-status-container-state-${container.id}`}
            >
              {container.state}
            </StatusTag>
          </CardHeader>

          <CardBodyStack>
            {container.image && (
              <SecondaryText ellipsis>{container.image}</SecondaryText>
            )}
            {container.cpu_percent && (
              <KeyValueRow>
                <FieldLabel>CPU:</FieldLabel>
                <FieldValue>{container.cpu_percent}</FieldValue>
              </KeyValueRow>
            )}
            {container.memory_usage && (
              <KeyValueRow>
                <FieldLabel>{t('resources:repositories.memory')}:</FieldLabel>
                <FieldValue>{container.memory_usage}</FieldValue>
              </KeyValueRow>
            )}
          </CardBodyStack>
        </ListCard>
      )) as ListProps<unknown>['renderItem']}
    />
  </SectionBlock>
)
