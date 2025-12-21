import React, { useEffect, useMemo } from 'react';
import {
  Badge,
  Card,
  Col,
  Empty,
  Flex,
  List,
  Progress,
  Row,
  Tag,
  Tooltip,
  Typography,
  type ListProps,
} from 'antd';
import { useTranslation } from 'react-i18next';
import AuditTraceModal from '@/components/common/AuditTraceModal';
import { CephSection } from '@/components/resources/internal/CephSection';
import {
  DetailPanelBody,
  DetailPanelCollapseButton,
  DetailPanelDivider,
  DetailPanelFieldLabel,
  DetailPanelFieldMonospaceValue,
  DetailPanelFieldRow,
  DetailPanelFieldStrongValue,
  DetailPanelFieldValue,
  DetailPanelHeader,
  DetailPanelHeaderRow,
  DetailPanelSectionHeader,
  DetailPanelSectionTitle,
  DetailPanelSurface,
  DetailPanelTagGroup,
  DetailPanelTitle,
  DetailPanelTitleGroup,
} from '@/components/resources/internal/detailPanelPrimitives';
import { featureFlags } from '@/config/featureFlags';
import { useTraceModal } from '@/hooks/useDialogState';
import {
  calculateResourcePercent,
  formatTimestampAsIs,
  getLocalizedRelativeTime,
} from '@/platform';
import type { Machine } from '@/types';
import {
  ApiOutlined,
  AppstoreOutlined,
  CloudServerOutlined,
  CodeOutlined,
  CompassOutlined,
  ContainerOutlined,
  DatabaseOutlined,
  DesktopOutlined,
  DoubleRightOutlined,
  GlobalOutlined,
  HddOutlined,
  InfoCircleOutlined,
  WifiOutlined,
} from '@/utils/optimizedIcons';
import { abbreviatePath } from '@/utils/pathUtils';
import { parseVaultStatus } from '@rediacc/shared/services/machine';
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

  const getTagColor = (variant: 'team' | 'bridge' | 'region' | 'queue' | 'version') =>
    variant === 'team'
      ? 'success'
      : variant === 'bridge'
        ? 'processing'
        : variant === 'region'
          ? 'default'
          : variant === 'queue'
            ? 'success'
            : 'default';

  const handleClose = () => {
    auditTrace.close();
    onClose();
  };

  return (
    <>
      <DetailPanelSurface $splitView={splitView} $visible={visible}>
        <DetailPanelHeader data-testid="vault-status-header">
          <DetailPanelHeaderRow>
            <DetailPanelTitleGroup>
              <CloudServerOutlined style={{ fontSize: 24 }} />
              <DetailPanelTitle level={4} data-testid="vault-status-machine-name">
                {machine.machineName}
              </DetailPanelTitle>
            </DetailPanelTitleGroup>
            <DetailPanelCollapseButton
              icon={<DoubleRightOutlined />}
              onClick={handleClose}
              data-testid="vault-status-collapse"
              aria-label="Collapse panel"
            />
          </DetailPanelHeaderRow>

          <DetailPanelTagGroup>
            <Tag
              bordered={false}
              color={getTagColor('team')}
              icon={<AppstoreOutlined />}
              data-testid="vault-status-team-tag"
            >
              {t('common:general.team')}: {machine.teamName}
            </Tag>
            <Tag
              bordered={false}
              color={getTagColor('bridge')}
              icon={<ApiOutlined />}
              data-testid="vault-status-bridge-tag"
            >
              {t('machines:bridge')}: {machine.bridgeName}
            </Tag>
            {machine.regionName && (
              <Tag
                bordered={false}
                color={getTagColor('region')}
                icon={<GlobalOutlined />}
                data-testid="vault-status-region-tag"
              >
                {t('machines:region')}: {machine.regionName}
              </Tag>
            )}
            <Badge count={machine.queueCount ?? undefined} data-testid="vault-status-queue-badge">
              <Tag bordered={false} color={getTagColor('queue')}>
                {t('machines:queueItems')}
              </Tag>
            </Badge>
            <Tag
              bordered={false}
              color={getTagColor('version')}
              data-testid="vault-status-version-tag"
            >
              {t('machines:vaultVersion')}: {machine.vaultVersion}
            </Tag>
          </DetailPanelTagGroup>

          {machine.vaultStatusTime && (
            <Flex>
              <Tooltip title={formatTimestampAsIs(machine.vaultStatusTime, 'datetime')}>
                <Typography.Text
                  data-testid="vault-status-last-updated"
                  style={{ fontSize: 12 }}
                >
                  {t('machines:lastUpdated')}:{' '}
                  {getLocalizedRelativeTime(machine.vaultStatusTime, t)}
                </Typography.Text>
              </Tooltip>
            </Flex>
          )}
        </DetailPanelHeader>

        <DetailPanelBody data-testid="vault-status-content">
          {!vaultData ? (
            <Flex>
              <Empty description={t('machines:noVaultData')} data-testid="vault-status-empty" />
            </Flex>
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
                <Flex data-testid="vault-status-ceph">
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
                </Flex>
              )}
            </>
          )}
        </DetailPanelBody>
      </DetailPanelSurface>

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
  <Flex vertical>
    <DetailPanelSectionHeader>
      <DesktopOutlined />
      <DetailPanelSectionTitle level={5} data-testid="vault-status-system-info-title">
        {t('resources:repositories.systemInfo')}
      </DetailPanelSectionTitle>
    </DetailPanelSectionHeader>

    <Card size="small" data-testid="vault-status-system-info-card">
      <Flex vertical gap={8} style={{ width: '100%' }}>
        <DetailPanelFieldRow>
          <DetailPanelFieldLabel>{t('resources:repositories.hostname')}:</DetailPanelFieldLabel>
          <DetailPanelFieldValue data-testid="vault-status-hostname">
            {system.hostname}
          </DetailPanelFieldValue>
        </DetailPanelFieldRow>
        <DetailPanelFieldRow>
          <DetailPanelFieldLabel>{t('resources:repositories.uptime')}:</DetailPanelFieldLabel>
          <DetailPanelFieldValue data-testid="vault-status-uptime">
            {system.uptime}
          </DetailPanelFieldValue>
        </DetailPanelFieldRow>
        <DetailPanelFieldRow>
          <DetailPanelFieldLabel>{t('resources:repositories.osName')}:</DetailPanelFieldLabel>
          <DetailPanelFieldValue data-testid="vault-status-os-name">
            {system.os_name}
          </DetailPanelFieldValue>
        </DetailPanelFieldRow>
        <DetailPanelFieldRow>
          <DetailPanelFieldLabel>{t('resources:repositories.kernel')}:</DetailPanelFieldLabel>
          <DetailPanelFieldValue data-testid="vault-status-kernel">
            {system.kernel}
          </DetailPanelFieldValue>
        </DetailPanelFieldRow>
        <DetailPanelFieldRow>
          <DetailPanelFieldLabel>{t('resources:repositories.cpu')}:</DetailPanelFieldLabel>
          <DetailPanelFieldValue data-testid="vault-status-cpu">
            {system.cpu_count} × {system.cpu_model}
          </DetailPanelFieldValue>
        </DetailPanelFieldRow>
        <DetailPanelFieldRow>
          <DetailPanelFieldLabel>{t('resources:repositories.systemTime')}:</DetailPanelFieldLabel>
          <DetailPanelFieldValue data-testid="vault-status-system-time">
            {system.system_time_human} ({system.timezone})
          </DetailPanelFieldValue>
        </DetailPanelFieldRow>
      </Flex>
    </Card>
  </Flex>
);

interface ResourceUsageSectionProps extends SectionProps {
  system: SystemInfo;
}

const ResourceUsageSection: React.FC<ResourceUsageSectionProps> = ({ system, t }) => {
  const memoryPercent = calculateResourcePercent(system.memory.used, system.memory.total) || 0;
  const diskPercent = parseInt(system.disk.use_percent, 10) || 0;
  const datastorePercent = parseInt(system.datastore.use_percent, 10) || 0;

  return (
    <Flex vertical>
      <DetailPanelDivider orientationMargin="left">
        <InfoCircleOutlined />
        {t('resources:repositories.resourceUsage')}
      </DetailPanelDivider>

      <Row gutter={[16, 16]}>
        <Col span={24} lg={8}>
          <Card size="small" data-testid="vault-status-memory-card">
            <Flex justify="space-between" align="center">
              <DatabaseOutlined />
              <Typography.Title level={5} style={{ fontSize: 16 }}>
                {t('resources:repositories.memory')}
              </Typography.Title>
            </Flex>
            <Progress percent={Math.round(memoryPercent)} />
            <Typography.Text style={{ fontSize: 12 }}>
              {t('resources:repositories.used')}: {system.memory.used} / {system.memory.total}
            </Typography.Text>
            <Typography.Text style={{ fontSize: 12 }}>
              {t('resources:repositories.available')}: {system.memory.available}
            </Typography.Text>
          </Card>
        </Col>

        <Col span={24} lg={8}>
          <Card size="small" data-testid="vault-status-disk-card">
            <Flex justify="space-between" align="center">
              <HddOutlined />
              <Typography.Title level={5} style={{ fontSize: 16 }}>
                {t('resources:repositories.disk')}
              </Typography.Title>
            </Flex>
            <Progress percent={diskPercent} />
            <Typography.Text style={{ fontSize: 12 }}>
              {t('resources:repositories.used')}: {system.disk.used} / {system.disk.total}
            </Typography.Text>
            <Typography.Text style={{ fontSize: 12 }}>
              {t('resources:repositories.available')}: {system.disk.available}
            </Typography.Text>
          </Card>
        </Col>

        <Col span={24} lg={8}>
          <Card size="small" data-testid="vault-status-datastore-card">
            <Flex justify="space-between" align="center">
              <DatabaseOutlined />
              <Typography.Title level={5} style={{ fontSize: 16 }}>
                {t('resources:repositories.datastore')}
              </Typography.Title>
            </Flex>
            {system.datastore.path && (
              <DetailPanelFieldRow>
                <DetailPanelFieldLabel>{t('common:general.path')}:</DetailPanelFieldLabel>
                <DetailPanelFieldMonospaceValue copyable={{ text: system.datastore.path }}>
                  {abbreviatePath(system.datastore.path, 40)}
                </DetailPanelFieldMonospaceValue>
              </DetailPanelFieldRow>
            )}
            <Progress percent={datastorePercent} />
            <Typography.Text style={{ fontSize: 12 }}>
              {t('resources:repositories.used')}: {system.datastore.used} / {system.datastore.total}
            </Typography.Text>
            <Typography.Text style={{ fontSize: 12 }}>
              {t('resources:repositories.available')}: {system.datastore.available}
            </Typography.Text>
          </Card>
        </Col>
      </Row>
    </Flex>
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
    <Flex vertical>
      <DetailPanelDivider orientationMargin="left">
        <WifiOutlined />
        {t('resources:repositories.networkInfo')}
      </DetailPanelDivider>

      {network.default_gateway && (
        <Card size="small" data-testid="vault-status-gateway-card">
          <Flex vertical gap={8} style={{ width: '100%' }}>
            <DetailPanelFieldRow>
              <DetailPanelFieldLabel>
                {t('resources:repositories.defaultGateway')}:
              </DetailPanelFieldLabel>
              <DetailPanelFieldValue data-testid="vault-status-gateway">
                {network.default_gateway}
              </DetailPanelFieldValue>
            </DetailPanelFieldRow>
            {network.default_interface && (
              <DetailPanelFieldRow>
                <DetailPanelFieldLabel>
                  {t('resources:repositories.defaultInterface')}:
                </DetailPanelFieldLabel>
                <DetailPanelFieldValue data-testid="vault-status-interface">
                  {network.default_interface}
                </DetailPanelFieldValue>
              </DetailPanelFieldRow>
            )}
          </Flex>
        </Card>
      )}

      <List
        dataSource={interfaces}
        data-testid="vault-status-network-list"
        renderItem={
          ((iface: NetworkInterface) => (
            <Card size="small" data-testid={`vault-status-network-${iface.name}`}>
              <Flex justify="space-between" align="center">
                <DetailPanelTitleGroup>
                  <CompassOutlined />
                  <DetailPanelFieldStrongValue
                    data-testid={`vault-status-network-name-${iface.name}`}
                  >
                    {iface.name}
                  </DetailPanelFieldStrongValue>
                </DetailPanelTitleGroup>
                <Tag
                  bordered={false}
                  color={iface.state === 'UP' ? 'success' : 'default'}
                  data-testid={`vault-status-network-state-${iface.name}`}
                >
                  {iface.state}
                </Tag>
              </Flex>
              <Flex vertical>
                {iface.ipv4_addresses.length > 0 && (
                  <Flex vertical>
                    <DetailPanelFieldLabel>
                      {t('resources:repositories.ipAddresses')}:
                    </DetailPanelFieldLabel>
                    <Flex>
                      {iface.ipv4_addresses.map((ip: string) => (
                        <Tag
                          key={ip}
                          color="processing"
                          bordered={false}
                          data-testid={`vault-status-ip-${ip}`}
                        >
                          {ip}
                        </Tag>
                      ))}
                    </Flex>
                  </Flex>
                )}
                {iface.mac_address && iface.mac_address !== 'unknown' && (
                  <Flex justify="space-between" align="center">
                    <DetailPanelFieldLabel>
                      {t('resources:repositories.macAddress')}:
                    </DetailPanelFieldLabel>
                    <DetailPanelFieldValue>{iface.mac_address}</DetailPanelFieldValue>
                  </Flex>
                )}
                {iface.mtu > 0 && (
                  <Flex justify="space-between" align="center">
                    <DetailPanelFieldLabel>MTU:</DetailPanelFieldLabel>
                    <DetailPanelFieldValue>{iface.mtu}</DetailPanelFieldValue>
                  </Flex>
                )}
              </Flex>
            </Card>
          )) as ListProps<unknown>['renderItem']
        }
      />
    </Flex>
  );
};

interface BlockDevicesSectionProps extends SectionProps {
  devices: BlockDevice[];
}

const BlockDevicesSection: React.FC<BlockDevicesSectionProps> = ({ devices, t }) => (
  <Flex vertical>
    <DetailPanelDivider orientationMargin="left">
      <HddOutlined />
      {t('resources:repositories.blockDevices')}
    </DetailPanelDivider>

    <List
      dataSource={devices}
      data-testid="vault-status-block-devices-list"
      renderItem={
        ((device: BlockDevice) => (
          <Card size="small" data-testid={`vault-status-block-device-${device.name}`}>
            <Flex justify="space-between" align="center">
              <DetailPanelTitleGroup>
                <HddOutlined />
                <DetailPanelFieldStrongValue
                  data-testid={`vault-status-device-path-${device.name}`}
                >
                  {device.path}
                </DetailPanelFieldStrongValue>
              </DetailPanelTitleGroup>
              <Flex>
                <Tag
                  bordered={false}
                  color="default"
                  data-testid={`vault-status-device-type-${device.name}`}
                >
                  {device.type}
                </Tag>
                <Tag
                  bordered={false}
                  color="processing"
                  data-testid={`vault-status-device-size-${device.name}`}
                >
                  {device.size_human}
                </Tag>
              </Flex>
            </Flex>

            <Flex vertical>
              {device.model && device.model !== 'Unknown' && (
                <Flex justify="space-between" align="center">
                  <DetailPanelFieldLabel>
                    {t('resources:repositories.model')}:
                  </DetailPanelFieldLabel>
                  <DetailPanelFieldValue>{device.model}</DetailPanelFieldValue>
                </Flex>
              )}

              {device.partitions.length > 0 && (
                <Flex vertical>
                  <DetailPanelFieldLabel>
                    {t('resources:repositories.partitions')}:
                  </DetailPanelFieldLabel>
                  <Flex vertical>
                    {device.partitions.map((part: BlockDevicePartition) => (
                      <Flex
                        key={`${device.name}-${part.name}`}
                        align="center"
                        style={{ fontSize: 12 }}
                      >
                        <CodeOutlined />
                        <Typography.Text style={{ fontSize: 12 }}>
                          {part.name}: {part.size_human}
                          {part.filesystem && ` (${part.filesystem})`}
                          {part.mountpoint && ` • ${part.mountpoint}`}
                        </Typography.Text>
                      </Flex>
                    ))}
                  </Flex>
                </Flex>
              )}
            </Flex>
          </Card>
        )) as ListProps<unknown>['renderItem']
      }
    />
  </Flex>
);

interface SystemContainersSectionProps extends SectionProps {
  containers: Container[];
}

const SystemContainersSection: React.FC<SystemContainersSectionProps> = ({ containers, t }) => (
  <Flex vertical>
    <DetailPanelDivider orientationMargin="left">
      <ContainerOutlined />
      {t('resources:repositories.systemContainers')}
    </DetailPanelDivider>

    <List
      dataSource={containers}
      data-testid="vault-status-containers-list"
      renderItem={
        ((container: Container) => (
          <Card size="small" data-testid={`vault-status-container-${container.id}`}>
            <Flex justify="space-between" align="center">
              <DetailPanelTitleGroup>
                <ContainerOutlined />
                <DetailPanelFieldStrongValue
                  data-testid={`vault-status-container-name-${container.id}`}
                >
                  {container.name}
                </DetailPanelFieldStrongValue>
              </DetailPanelTitleGroup>
              <Tag
                bordered={false}
                color={container.state === 'running' ? 'success' : 'default'}
                data-testid={`vault-status-container-state-${container.id}`}
              >
                {container.state}
              </Tag>
            </Flex>

            <Flex vertical>
              {container.image && (
                <Typography.Text ellipsis style={{ fontSize: 12 }}>
                  {container.image}
                </Typography.Text>
              )}
              {container.cpu_percent && (
                <Flex justify="space-between" align="center">
                  <DetailPanelFieldLabel>CPU:</DetailPanelFieldLabel>
                  <DetailPanelFieldValue>{container.cpu_percent}</DetailPanelFieldValue>
                </Flex>
              )}
              {container.memory_usage && (
                <Flex justify="space-between" align="center">
                  <DetailPanelFieldLabel>
                    {t('resources:repositories.memory')}:
                  </DetailPanelFieldLabel>
                  <DetailPanelFieldValue>{container.memory_usage}</DetailPanelFieldValue>
                </Flex>
              )}
            </Flex>
          </Card>
        )) as ListProps<unknown>['renderItem']
      }
    />
  </Flex>
);
