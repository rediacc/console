import React, { useEffect, useMemo } from 'react';
import { Row, Col, Progress, Tooltip } from 'antd';
import { useTranslation } from 'react-i18next';
import AuditTraceModal from '@/components/common/AuditTraceModal';
import { CephSection } from '@/components/resources/internal/CephSection';
import { featureFlags } from '@/config/featureFlags';
import { useTraceModal } from '@/hooks/useDialogState';
import { calculateResourcePercent } from '@/platform';
import { getLocalizedRelativeTime, formatTimestampAsIs } from '@/platform';
import type { Machine } from '@/types';
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
} from '@/utils/optimizedIcons';
import { abbreviatePath } from '@/utils/pathUtils';
import { parseVaultStatus } from '@rediacc/shared/services/machine';
import {
  PanelWrapper,
  Header,
  HeaderRow,
  TitleGroup,
  HeaderIcon,
  PanelTitle,
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
  SubduedText,
  IconWrapper,
  SectionBlock,
  InfoCard,
  FullWidthStack,
  FieldRow,
  FieldLabel,
  FieldValue,
  FieldValueMonospace,
  FieldValueStrong,
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
} from './styles';
import type { ListProps } from 'antd';
import type { TFunction } from 'i18next';

interface MachineVaultStatusPanelProps {
  machine: Machine | null;
  visible: boolean;
  onClose: () => void;
  splitView?: boolean;
}

interface SystemInfo {
  hostname: string;
  kernel: string;
  os_name: string;
  uptime: string;
  system_time: number;
  system_time_human: string;
  timezone: string;
  cpu_count: number;
  cpu_model: string;
  memory: {
    total: string;
    used: string;
    available: string;
  };
  disk: {
    total: string;
    used: string;
    available: string;
    use_percent: string;
  };
  datastore: {
    path: string;
    total: string;
    used: string;
    available: string;
    use_percent: string;
  };
}

interface NetworkInterface {
  name: string;
  state: string;
  mac_address: string;
  mtu: number;
  ipv4_addresses: string[];
  ipv6_addresses: string[];
  default_gateway: string | null;
}

interface VaultNetwork {
  default_gateway?: string;
  default_interface?: string;
  interfaces: NetworkInterface[];
}

interface BlockDevicePartition {
  name: string;
  path: string;
  size_bytes: number;
  size_human: string;
  filesystem: string | null;
  mountpoint: string | null;
}

interface BlockDevice {
  name: string;
  path: string;
  size_bytes: number;
  size_human: string;
  model: string;
  serial: string | null;
  type: string;
  discard_granularity: number;
  physical_sector_size: number;
  logical_sector_size: number;
  partitions: BlockDevicePartition[];
}

interface Container {
  id: string;
  name: string;
  image: string;
  command: string;
  created: string;
  status: string;
  state: string;
  ports: string;
  cpu_percent?: string;
  memory_usage?: string;
  memory_percent?: string;
  net_io?: string;
  block_io?: string;
  pids?: string;
}

interface VaultData {
  system?: SystemInfo;
  network?: VaultNetwork;
  block_devices?: BlockDevice[];
  system_containers?: Container[];
}

export const MachineVaultStatusPanel: React.FC<MachineVaultStatusPanelProps> = ({
  machine,
  visible,
  onClose,
  splitView = false,
}) => {
  const { t } = useTranslation(['machines', 'resources', 'common', 'ceph']);
  const auditTrace = useTraceModal();

  const vaultData = useMemo<VaultData | null>(() => {
    if (!machine?.vaultStatus) return null;

    const parsed = parseVaultStatus(machine.vaultStatus);

    if (parsed.status !== 'completed' || !parsed.rawResult) {
      return null;
    }

    try {
      return JSON.parse(parsed.rawResult);
    } catch (err) {
      console.error('Error parsing vault status result:', err);
      return null;
    }
  }, [machine]);

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

  if (!machine || !visible) {
    return null;
  }

  const handleClose = () => {
    auditTrace.close();
    onClose();
  };

  return (
    <>
      <PanelWrapper $splitView={splitView} $visible={visible}>
        <Header data-testid="vault-status-header">
          <HeaderRow>
            <TitleGroup>
              <HeaderIcon />
              <PanelTitle level={4} data-testid="vault-status-machine-name">
                {machine.machineName}
              </PanelTitle>
            </TitleGroup>
            <CollapseButton
              variant="text"
              icon={<DoubleRightOutlined />}
              onClick={handleClose}
              data-testid="vault-status-collapse"
              aria-label="Collapse panel"
            />
          </HeaderRow>

          <TagRow>
            <StyledTag
              $variant="team"
              icon={<AppstoreOutlined />}
              data-testid="vault-status-team-tag"
            >
              {t('common:general.team')}: {machine.teamName}
            </StyledTag>
            <StyledTag
              $variant="bridge"
              icon={<ApiOutlined />}
              data-testid="vault-status-bridge-tag"
            >
              {t('machines:bridge')}: {machine.bridgeName}
            </StyledTag>
            {machine.regionName && (
              <StyledTag
                $variant="region"
                icon={<GlobalOutlined />}
                data-testid="vault-status-region-tag"
              >
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
              <Tooltip title={formatTimestampAsIs(machine.vaultStatusTime, 'datetime')}>
                <Timestamp data-testid="vault-status-last-updated">
                  {t('machines:lastUpdated')}:{' '}
                  {getLocalizedRelativeTime(machine.vaultStatusTime, t)}
                </Timestamp>
              </Tooltip>
            </TimestampWrapper>
          )}
        </Header>

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

              {vaultData.network && (
                <NetworkSection network={vaultData.network as VaultNetwork} t={t} />
              )}

              {vaultData.block_devices && vaultData.block_devices.length > 0 && (
                <BlockDevicesSection devices={vaultData.block_devices as BlockDevice[]} t={t} />
              )}

              {vaultData.system_containers && vaultData.system_containers.length > 0 && (
                <SystemContainersSection containers={vaultData.system_containers} t={t} />
              )}

              {featureFlags.isEnabled('ceph') && machine && (
                <SectionBlock data-testid="vault-status-ceph">
                  <CephSection
                    machine={machine}
                    onViewDetails={() =>
                      auditTrace.open({
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
        open={auditTrace.isOpen}
        onCancel={auditTrace.close}
        entityType={auditTrace.entityType}
        entityIdentifier={auditTrace.entityIdentifier}
        entityName={auditTrace.entityName}
      />
    </>
  );
};

interface SectionProps {
  t: TFunction;
}

interface SystemInfoSectionProps extends SectionProps {
  system: SystemInfo;
}

const SystemInfoSection: React.FC<SystemInfoSectionProps> = ({ system, t }) => (
  <SectionBlock>
    <SectionHeader>
      <IconWrapper $color="var(--color-primary)">
        <DesktopOutlined />
      </IconWrapper>
      <SectionTitle level={5} data-testid="vault-status-system-info-title">
        {t('resources:repos.systemInfo')}
      </SectionTitle>
    </SectionHeader>

    <InfoCard size="sm" data-testid="vault-status-system-info-card">
      <FullWidthStack>
        <FieldRow>
          <FieldLabel>{t('resources:repos.hostname')}:</FieldLabel>
          <FieldValue data-testid="vault-status-hostname">{system.hostname}</FieldValue>
        </FieldRow>
        <FieldRow>
          <FieldLabel>{t('resources:repos.uptime')}:</FieldLabel>
          <FieldValue data-testid="vault-status-uptime">{system.uptime}</FieldValue>
        </FieldRow>
        <FieldRow>
          <FieldLabel>{t('resources:repos.osName')}:</FieldLabel>
          <FieldValue data-testid="vault-status-os-name">{system.os_name}</FieldValue>
        </FieldRow>
        <FieldRow>
          <FieldLabel>{t('resources:repos.kernel')}:</FieldLabel>
          <FieldValue data-testid="vault-status-kernel">{system.kernel}</FieldValue>
        </FieldRow>
        <FieldRow>
          <FieldLabel>{t('resources:repos.cpu')}:</FieldLabel>
          <FieldValue data-testid="vault-status-cpu">
            {system.cpu_count} × {system.cpu_model}
          </FieldValue>
        </FieldRow>
        <FieldRow>
          <FieldLabel>{t('resources:repos.systemTime')}:</FieldLabel>
          <FieldValue data-testid="vault-status-system-time">
            {system.system_time_human} ({system.timezone})
          </FieldValue>
        </FieldRow>
      </FullWidthStack>
    </InfoCard>
  </SectionBlock>
);

interface ResourceUsageSectionProps extends SectionProps {
  system: SystemInfo;
}

const ResourceUsageSection: React.FC<ResourceUsageSectionProps> = ({ system, t }) => {
  const memoryPercent = calculateResourcePercent(system.memory.used, system.memory.total) || 0;
  const diskPercent = parseInt(system.disk.use_percent, 10) || 0;
  const datastorePercent = parseInt(system.datastore.use_percent, 10) || 0;

  const diskStroke = diskPercent > 90 ? 'var(--color-error)' : 'var(--color-warning)';
  const datastoreStroke = datastorePercent > 90 ? 'var(--color-error)' : 'var(--color-success)';

  return (
    <SectionBlock>
      <SectionDivider orientationMargin="left">
        <IconWrapper $color="var(--color-info)">
          <InfoCircleOutlined />
        </IconWrapper>
        {t('resources:repos.resourceUsage')}
      </SectionDivider>

      <Row gutter={[16, 16]}>
        <Col span={24} lg={8}>
          <MetricCard size="sm" data-testid="vault-status-memory-card">
            <CardHeader>
              <IconWrapper $color="var(--color-info)">
                <DatabaseOutlined />
              </IconWrapper>
              <CardTitle level={5}>{t('resources:repos.memory')}</CardTitle>
            </CardHeader>
            <Progress percent={Math.round(memoryPercent)} strokeColor="var(--color-info)" />
            <SubduedText>
              {t('resources:repos.used')}: {system.memory.used} / {system.memory.total}
            </SubduedText>
            <SubduedText>
              {t('resources:repos.available')}: {system.memory.available}
            </SubduedText>
          </MetricCard>
        </Col>

        <Col span={24} lg={8}>
          <MetricCard size="sm" data-testid="vault-status-disk-card">
            <CardHeader>
              <IconWrapper $color="var(--color-warning)">
                <HddOutlined />
              </IconWrapper>
              <CardTitle level={5}>{t('resources:repos.disk')}</CardTitle>
            </CardHeader>
            <Progress percent={diskPercent} strokeColor={diskStroke} />
            <SubduedText>
              {t('resources:repos.used')}: {system.disk.used} / {system.disk.total}
            </SubduedText>
            <SubduedText>
              {t('resources:repos.available')}: {system.disk.available}
            </SubduedText>
          </MetricCard>
        </Col>

        <Col span={24} lg={8}>
          <MetricCard size="sm" data-testid="vault-status-datastore-card">
            <CardHeader>
              <IconWrapper $color="var(--color-success)">
                <DatabaseOutlined />
              </IconWrapper>
              <CardTitle level={5}>{t('resources:repos.datastore')}</CardTitle>
            </CardHeader>
            {system.datastore.path && (
              <FieldRow>
                <FieldLabel>{t('common:general.path')}:</FieldLabel>
                <FieldValueMonospace copyable={{ text: system.datastore.path }}>
                  {abbreviatePath(system.datastore.path, 40)}
                </FieldValueMonospace>
              </FieldRow>
            )}
            <Progress percent={datastorePercent} strokeColor={datastoreStroke} />
            <SubduedText>
              {t('resources:repos.used')}: {system.datastore.used} / {system.datastore.total}
            </SubduedText>
            <SubduedText>
              {t('resources:repos.available')}: {system.datastore.available}
            </SubduedText>
          </MetricCard>
        </Col>
      </Row>
    </SectionBlock>
  );
};

interface NetworkSectionProps extends SectionProps {
  network: VaultNetwork;
}

const NetworkSection: React.FC<NetworkSectionProps> = ({ network, t }) => {
  const interfaces = network.interfaces.filter(
    (iface) => iface.state !== 'unknown' && iface.name !== 'lo'
  );

  return (
    <SectionBlock>
      <SectionDivider orientationMargin="left">
        <IconWrapper $color="var(--color-info)">
          <WifiOutlined />
        </IconWrapper>
        {t('resources:repos.networkInfo')}
      </SectionDivider>

      {network.default_gateway && (
        <InfoCard size="sm" data-testid="vault-status-gateway-card">
          <FullWidthStack>
            <FieldRow>
              <FieldLabel>{t('resources:repos.defaultGateway')}:</FieldLabel>
              <FieldValue data-testid="vault-status-gateway">{network.default_gateway}</FieldValue>
            </FieldRow>
            {network.default_interface && (
              <FieldRow>
                <FieldLabel>{t('resources:repos.defaultInterface')}:</FieldLabel>
                <FieldValue data-testid="vault-status-interface">
                  {network.default_interface}
                </FieldValue>
              </FieldRow>
            )}
          </FullWidthStack>
        </InfoCard>
      )}

      <StyledList
        dataSource={interfaces}
        data-testid="vault-status-network-list"
        renderItem={
          ((iface: NetworkInterface) => (
            <ListCard size="sm" data-testid={`vault-status-network-${iface.name}`}>
              <CardHeader>
                <TitleGroup>
                  <IconWrapper $color="var(--color-info)">
                    <CompassOutlined />
                  </IconWrapper>
                  <FieldValueStrong data-testid={`vault-status-network-name-${iface.name}`}>
                    {iface.name}
                  </FieldValueStrong>
                </TitleGroup>
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
                    <FieldLabel>{t('resources:repos.ipAddresses')}:</FieldLabel>
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
                    <FieldLabel>{t('resources:repos.macAddress')}:</FieldLabel>
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
          )) as ListProps<unknown>['renderItem']
        }
      />
    </SectionBlock>
  );
};

interface BlockDevicesSectionProps extends SectionProps {
  devices: BlockDevice[];
}

const BlockDevicesSection: React.FC<BlockDevicesSectionProps> = ({ devices, t }) => (
  <SectionBlock>
    <SectionDivider orientationMargin="left">
      <IconWrapper $color="var(--color-warning)">
        <HddOutlined />
      </IconWrapper>
      {t('resources:repos.blockDevices')}
    </SectionDivider>

    <StyledList
      dataSource={devices}
      data-testid="vault-status-block-devices-list"
      renderItem={
        ((device: BlockDevice) => (
          <ListCard size="sm" data-testid={`vault-status-block-device-${device.name}`}>
            <CardHeader>
              <TitleGroup>
                <IconWrapper $color="var(--color-warning)">
                  <HddOutlined />
                </IconWrapper>
                <FieldValueStrong data-testid={`vault-status-device-path-${device.name}`}>
                  {device.path}
                </FieldValueStrong>
              </TitleGroup>
              <CardTagGroup>
                <StatusTag data-testid={`vault-status-device-type-${device.name}`}>
                  {device.type}
                </StatusTag>
                <StatusTag $tone="info" data-testid={`vault-status-device-size-${device.name}`}>
                  {device.size_human}
                </StatusTag>
              </CardTagGroup>
            </CardHeader>

            <CardBodyStack>
              {device.model && device.model !== 'Unknown' && (
                <KeyValueRow>
                  <FieldLabel>{t('resources:repos.model')}:</FieldLabel>
                  <FieldValue>{device.model}</FieldValue>
                </KeyValueRow>
              )}

              {device.partitions.length > 0 && (
                <div>
                  <FieldLabel>{t('resources:repos.partitions')}:</FieldLabel>
                  <IndentedBlock>
                    {device.partitions.map((part: BlockDevicePartition) => (
                      <PartitionRow key={`${device.name}-${part.name}`}>
                        <CodeOutlined />
                        <SubduedText as="span">
                          {part.name}: {part.size_human}
                          {part.filesystem && ` (${part.filesystem})`}
                          {part.mountpoint && ` • ${part.mountpoint}`}
                        </SubduedText>
                      </PartitionRow>
                    ))}
                  </IndentedBlock>
                </div>
              )}
            </CardBodyStack>
          </ListCard>
        )) as ListProps<unknown>['renderItem']
      }
    />
  </SectionBlock>
);

interface SystemContainersSectionProps extends SectionProps {
  containers: Container[];
}

const SystemContainersSection: React.FC<SystemContainersSectionProps> = ({ containers, t }) => (
  <SectionBlock>
    <SectionDivider orientationMargin="left">
      <IconWrapper $color="var(--color-secondary)">
        <ContainerOutlined />
      </IconWrapper>
      {t('resources:repos.systemContainers')}
    </SectionDivider>

    <StyledList
      dataSource={containers}
      data-testid="vault-status-containers-list"
      renderItem={
        ((container: Container) => (
          <ListCard size="sm" data-testid={`vault-status-container-${container.id}`}>
            <CardHeader>
              <TitleGroup>
                <IconWrapper $color="var(--color-secondary)">
                  <ContainerOutlined />
                </IconWrapper>
                <FieldValueStrong data-testid={`vault-status-container-name-${container.id}`}>
                  {container.name}
                </FieldValueStrong>
              </TitleGroup>
              <StatusTag
                $tone={container.state === 'running' ? 'success' : 'default'}
                data-testid={`vault-status-container-state-${container.id}`}
              >
                {container.state}
              </StatusTag>
            </CardHeader>

            <CardBodyStack>
              {container.image && <SubduedText ellipsis>{container.image}</SubduedText>}
              {container.cpu_percent && (
                <KeyValueRow>
                  <FieldLabel>CPU:</FieldLabel>
                  <FieldValue>{container.cpu_percent}</FieldValue>
                </KeyValueRow>
              )}
              {container.memory_usage && (
                <KeyValueRow>
                  <FieldLabel>{t('resources:repos.memory')}:</FieldLabel>
                  <FieldValue>{container.memory_usage}</FieldValue>
                </KeyValueRow>
              )}
            </CardBodyStack>
          </ListCard>
        )) as ListProps<unknown>['renderItem']
      }
    />
  </SectionBlock>
);
