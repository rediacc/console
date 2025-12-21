import React, { useMemo } from 'react';
import { Card, Flex, Progress, Tag, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import {
  ApiOutlined,
  AppstoreOutlined,
  CloudServerOutlined,
  ContainerOutlined,
  DoubleRightOutlined,
  FolderOutlined,
  HddOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  WifiOutlined,
} from '@/utils/optimizedIcons';
import {
  DetailPanelBody,
  DetailPanelCollapseButton,
  DetailPanelDivider,
  DetailPanelFieldLabel,
  DetailPanelFieldList,
  DetailPanelFieldMonospaceValue,
  DetailPanelFieldRow,
  DetailPanelFieldStrongValue,
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

interface ContainerData {
  id: string;
  name: string;
  image: string;
  command: string;
  created: string;
  status: string;
  state: string;
  ports: string;
  port_mappings?: Array<{
    host?: string;
    host_port?: string;
    container_port: string;
    protocol: string;
  }>;
  labels: string;
  mounts: string;
  networks: string;
  size: string;
  repository: string;
  cpu_percent: string;
  memory_usage: string;
  memory_percent: string;
  net_io: string;
  block_io: string;
  pids: string;
}

interface ContainerDetailPanelProps {
  container: ContainerData | null;
  visible: boolean;
  onClose: () => void;
  splitView?: boolean;
}

export const ContainerDetailPanel: React.FC<ContainerDetailPanelProps> = ({
  container,
  visible,
  onClose,
  splitView = false,
}) => {
  const { t } = useTranslation(['resources', 'common']);

  const resourceUsage = useMemo(() => {
    if (!container) return null;

    const cpuValue = parseFloat(container.cpu_percent?.replace('%', '') || '0');
    const memoryParts = container.memory_usage?.split(' / ') || [];
    const memoryUsed = memoryParts[0] || '0';
    const memoryTotal = memoryParts[1] || '0';
    const memoryPercent = parseFloat(container.memory_percent?.replace('%', '') || '0');
    const netParts = container.net_io?.split(' / ') || [];
    const netIn = netParts[0] || '0';
    const netOut = netParts[1] || '0';
    const blockParts = container.block_io?.split(' / ') || [];
    const blockRead = blockParts[0] || '0';
    const blockWrite = blockParts[1] || '0';

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
    };
  }, [container]);

  if (!visible || !container) {
    return null;
  }

  const isPlugin = container.name?.startsWith('plugin-');
  const pluginName = isPlugin ? container.name.replace('plugin-', '') : null;
  const cpuWarning = (resourceUsage?.cpu || 0) > 80;
  const memoryWarning = (resourceUsage?.memoryPercent || 0) > 90;

  const renderPortMappings = () => {
    if (container.port_mappings && container.port_mappings.length > 0) {
      return container.port_mappings.map((mapping, index) => {
        const hostBinding = mapping.host
          ? `${mapping.host}:${mapping.host_port}`
          : mapping.host_port;
        const tagText = hostBinding
          ? `${hostBinding} → ${mapping.container_port}/${mapping.protocol}`
          : `${mapping.container_port}/${mapping.protocol}`;

        return (
          <Tag
            key={`${mapping.container_port}-${mapping.protocol}-${index}`}
            color="default"
          >
            {tagText}
          </Tag>
        );
      });
    }

    if (container.ports) {
      return (
        <Typography.Text data-testid="container-detail-ports-text">
          {container.ports}
        </Typography.Text>
      );
    }

    return null;
  };

  return (
    <DetailPanelSurface
      $splitView={splitView}
      $visible={visible}
      className="container-detail-panel"
      data-testid="container-detail-panel"
    >
      <DetailPanelHeader data-testid="container-detail-header">
        <DetailPanelHeaderRow>
          <DetailPanelTitleGroup>
            {isPlugin ? <ApiOutlined /> : <AppstoreOutlined />}
            <DetailPanelTitle data-testid="container-detail-title">
              {isPlugin ? pluginName : container.name}
            </DetailPanelTitle>
          </DetailPanelTitleGroup>
          <DetailPanelCollapseButton
            icon={<DoubleRightOutlined />}
            onClick={onClose}
            data-testid="container-detail-collapse"
            aria-label="Collapse Panel"
          />
        </DetailPanelHeaderRow>
        <DetailPanelTagGroup>
          <Tag
            color={container.state === 'running' ? 'success' : 'default'}
            icon={container.state === 'running' ? <PlayCircleOutlined /> : <PauseCircleOutlined />}
            data-testid="container-detail-state-tag"
          >
            {container.state}
          </Tag>
          <Tag
            color="processing"
            icon={<FolderOutlined />}
            data-testid="container-detail-repo-tag"
          >
            {t('resources:containers.repositoryLabel', 'Repository')}: {container.repository}
          </Tag>
        </DetailPanelTagGroup>
      </DetailPanelHeader>

      <DetailPanelBody data-testid="container-detail-content">
        <div>
          <DetailPanelSectionHeader data-testid="container-detail-info-section">
            {isPlugin ? <ApiOutlined /> : <ContainerOutlined />}
            <DetailPanelSectionTitle>{t('resources:containers.containerInfo')}</DetailPanelSectionTitle>
          </DetailPanelSectionHeader>

          <DetailPanelSectionCard data-testid="container-detail-basic-info">
            <DetailPanelFieldList>
              <DetailPanelFieldRow>
                <DetailPanelFieldLabel>{t('resources:containers.containerID')}:</DetailPanelFieldLabel>
                <DetailPanelFieldMonospaceValue copyable data-testid="container-detail-id">
                  {container.id}
                </DetailPanelFieldMonospaceValue>
              </DetailPanelFieldRow>
              <DetailPanelFieldRow>
                <DetailPanelFieldLabel>{t('resources:containers.image')}:</DetailPanelFieldLabel>
                <DetailPanelFieldValue data-testid="container-detail-image">{container.image}</DetailPanelFieldValue>
              </DetailPanelFieldRow>
              <DetailPanelFieldRow>
                <DetailPanelFieldLabel>{t('resources:containers.status')}:</DetailPanelFieldLabel>
                <DetailPanelFieldValue data-testid="container-detail-status">{container.status}</DetailPanelFieldValue>
              </DetailPanelFieldRow>
              <DetailPanelFieldRow>
                <DetailPanelFieldLabel>{t('resources:containers.created')}:</DetailPanelFieldLabel>
                <DetailPanelFieldValue data-testid="container-detail-created">{container.created}</DetailPanelFieldValue>
              </DetailPanelFieldRow>
            </DetailPanelFieldList>
          </DetailPanelSectionCard>
        </div>

        <DetailPanelDivider>
          <Flex component="span" align="center" style={{ fontWeight: 600 }}>
            <CloudServerOutlined />
            {t('resources:containers.resourceUsage')}
          </Flex>
        </DetailPanelDivider>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))' }}>
          <Card size="small" data-testid="container-detail-cpu-card">
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {t('resources:containers.cpuUsage')}
            </Typography.Text>
            <Typography.Text
              strong
              style={{
                fontSize: 18,
                color: cpuWarning ? 'var(--ant-color-error)' : 'var(--ant-color-primary)',
              }}
            >
              {resourceUsage?.cpu?.toFixed(2) ?? '0'}%
            </Typography.Text>
            <Progress
              percent={resourceUsage?.cpu || 0}
              showInfo={false}
              status={cpuWarning ? 'exception' : 'normal'}
            />
          </Card>
          <Card size="small" data-testid="container-detail-memory-card">
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {t('resources:containers.memoryUsage')}
            </Typography.Text>
            <Typography.Text
              strong
              style={{
                fontSize: 18,
                color: memoryWarning ? 'var(--ant-color-error)' : 'var(--ant-color-primary)',
              }}
            >
              {resourceUsage ? `${resourceUsage.memoryUsed} / ${resourceUsage.memoryTotal}` : '-'}
            </Typography.Text>
            <Progress
              percent={resourceUsage?.memoryPercent || 0}
              status={memoryWarning ? 'exception' : 'normal'}
            />
          </Card>
          <Card size="small" data-testid="container-detail-network-card">
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {t('resources:containers.networkIO')}
            </Typography.Text>
            <Typography.Text>
              <WifiOutlined /> {resourceUsage?.netIn} / {resourceUsage?.netOut}
            </Typography.Text>
          </Card>
          <Card size="small" data-testid="container-detail-block-io-card">
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {t('resources:containers.blockIO')}
            </Typography.Text>
            <Typography.Text>
              <HddOutlined /> {resourceUsage?.blockRead} / {resourceUsage?.blockWrite}
            </Typography.Text>
          </Card>
        </div>

        <DetailPanelSectionCard data-testid="container-detail-runtime">
          <DetailPanelFieldList>
            {container.port_mappings || container.ports ? (
              <DetailPanelFieldRow>
                <DetailPanelFieldLabel>{t('resources:containers.ports')}:</DetailPanelFieldLabel>
                <DetailPanelFieldStrongValue>{renderPortMappings()}</DetailPanelFieldStrongValue>
              </DetailPanelFieldRow>
            ) : null}
            <DetailPanelFieldRow>
              <DetailPanelFieldLabel>{t('resources:containers.networks')}:</DetailPanelFieldLabel>
              <DetailPanelFieldValue>
                <Tag data-testid="container-detail-network-tag" color="default">
                  {container.networks}
                </Tag>
              </DetailPanelFieldValue>
            </DetailPanelFieldRow>
            <DetailPanelFieldRow>
              <DetailPanelFieldLabel>{t('resources:containers.size')}:</DetailPanelFieldLabel>
              <DetailPanelFieldValue data-testid="container-detail-size">{container.size}</DetailPanelFieldValue>
            </DetailPanelFieldRow>
            <DetailPanelFieldRow>
              <DetailPanelFieldLabel>{t('resources:containers.processes')}:</DetailPanelFieldLabel>
              <DetailPanelFieldValue>
                <Tag data-testid="container-detail-pids" color="default">
                  {resourceUsage?.pids || 0} {t('resources:containers.pids')}
                </Tag>
              </DetailPanelFieldValue>
            </DetailPanelFieldRow>
          </DetailPanelFieldList>
        </DetailPanelSectionCard>

        <DetailPanelDivider>
          <Flex component="span" align="center" style={{ fontWeight: 600 }}>
            <FolderOutlined />
            {t('resources:containers.environment')}
          </Flex>
        </DetailPanelDivider>

        <DetailPanelSectionCard data-testid="container-detail-environment">
          <div>
            <div>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {t('resources:containers.mounts')}:
              </Typography.Text>
              <DetailPanelFieldMonospaceValue data-testid="container-detail-mounts">
                {container.mounts}
              </DetailPanelFieldMonospaceValue>
            </div>
            {container.labels && (
              <div>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  {t('resources:containers.labels')}:
                </Typography.Text>
                <DetailPanelFieldMonospaceValue data-testid="container-detail-labels">
                  {container.labels}
                </DetailPanelFieldMonospaceValue>
              </div>
            )}
          </div>
        </DetailPanelSectionCard>
      </DetailPanelBody>
    </DetailPanelSurface>
  );
};
