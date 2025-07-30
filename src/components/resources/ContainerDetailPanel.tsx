import React, { useEffect, useMemo } from 'react'
import { 
  Typography, 
  Card, 
  Row, 
  Col, 
  Progress, 
  Tag, 
  Space, 
  Button, 
  Empty,
  Divider,
  Statistic
} from 'antd'
import { 
  CloseOutlined,
  ClockCircleOutlined,
  InfoCircleOutlined,
  AppstoreOutlined,
  CloudServerOutlined,
  CodeOutlined,
  ApiOutlined,
  HddOutlined,
  WifiOutlined,
  FolderOutlined,
  ClusterOutlined,
  PlayCircleOutlined,
  PauseCircleOutlined
} from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { useTheme } from '@/context/ThemeContext'

const { Text, Title } = Typography

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
  splitView = false 
}) => {
  const { t } = useTranslation(['resources', 'common'])
  const { theme } = useTheme()

  // Handle escape key
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && visible) {
        onClose()
      }
    }

    if (visible) {
      document.addEventListener('keydown', handleEscape)
      return () => document.removeEventListener('keydown', handleEscape)
    }
  }, [visible, onClose])

  // Parse resource usage values
  const resourceUsage = useMemo(() => {
    if (!container) return null

    // Parse CPU percentage
    const cpuValue = parseFloat(container.cpu_percent?.replace('%', '') || '0')
    
    // Parse memory values
    const memoryParts = container.memory_usage?.split(' / ') || []
    const memoryUsed = memoryParts[0] || '0'
    const memoryTotal = memoryParts[1] || '0'
    const memoryPercent = parseFloat(container.memory_percent?.replace('%', '') || '0')

    // Parse network I/O
    const netParts = container.net_io?.split(' / ') || []
    const netIn = netParts[0] || '0'
    const netOut = netParts[1] || '0'

    // Parse block I/O
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
      pids: parseInt(container.pids || '0')
    }
  }, [container])

  // Check if this is a plugin container
  const isPlugin = container?.name?.startsWith('plugin-')
  const pluginName = isPlugin ? container.name.replace('plugin-', '') : null

  if (!visible || !container) {
    return null
  }

  return (
    <>
      {/* Header with close button */}
      <div style={{
        padding: splitView ? '16px 24px' : '16px 24px 0',
        borderBottom: `1px solid ${theme === 'dark' ? '#303030' : '#f0f0f0'}`,
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
      }}
      data-testid="container-detail-header">
        <Title level={4} style={{ margin: 0 }} data-testid="container-detail-title">
          {isPlugin ? t('resources:containers.pluginDetails') : t('resources:containers.containerDetails')}
        </Title>
        {!splitView && (
          <Button
            type="text"
            icon={<CloseOutlined />}
            onClick={onClose}
            style={{ marginRight: -8 }}
            data-testid="container-detail-close"
          />
        )}
      </div>

      {/* Content */}
      <div style={{
        padding: '24px',
        height: splitView ? 'calc(100% - 57px)' : undefined,
        overflow: 'auto',
      }}>
        <div style={{ marginBottom: 16 }}>
          <Space size="small" style={{ marginBottom: 8 }}>
            <Tag color={isPlugin ? "blue" : "cyan"} icon={isPlugin ? <ApiOutlined /> : <AppstoreOutlined />} data-testid="container-detail-name-tag">
              {isPlugin ? `Plugin: ${pluginName}` : container.name}
            </Tag>
            <Tag 
              color={container.state === 'running' ? 'success' : 'default'}
              icon={container.state === 'running' ? <PlayCircleOutlined /> : <PauseCircleOutlined />}
              data-testid="container-detail-state-tag"
            >
              {container.state}
            </Tag>
          </Space>
        </div>

        {container && (
          <>
            {/* Basic Information */}
            <Card size="small" style={{ marginBottom: 16 }} data-testid="container-detail-basic-info">
              <Row gutter={[16, 16]}>
                <Col span={24}>
                  <Space direction="vertical" style={{ width: '100%' }} size="small">
                    <div>
                      <Text type="secondary">{t('resources:containers.containerID')}:</Text>
                      <br />
                      <Text copyable style={{ fontFamily: 'monospace', fontSize: 12 }} data-testid="container-detail-id">
                        {container.id}
                      </Text>
                    </div>
                    <div>
                      <Text type="secondary">{t('resources:containers.image')}:</Text>
                      <br />
                      <Text style={{ fontSize: 12, wordBreak: 'break-all' }} data-testid="container-detail-image">{container.image}</Text>
                    </div>
                    <div>
                      <Text type="secondary">{t('resources:containers.status')}:</Text>
                      <br />
                      <Text style={{ fontSize: 12 }} data-testid="container-detail-status">{container.status}</Text>
                    </div>
                    <div>
                      <Text type="secondary">{t('resources:containers.created')}:</Text>
                      <br />
                      <Text style={{ fontSize: 12 }} data-testid="container-detail-created">{container.created}</Text>
                    </div>
                  </Space>
                </Col>
              </Row>
            </Card>

            {/* Resource Usage */}
            <Divider style={{ margin: '24px 0' }}>
              <Space>
                <CloudServerOutlined />
                {t('resources:containers.resourceUsage')}
              </Space>
            </Divider>

            <Row gutter={[16, 16]}>
              <Col xs={24} sm={12}>
                <Card size="small" data-testid="container-detail-cpu-card">
                  <Statistic
                    title={t('resources:containers.cpuUsage')}
                    value={resourceUsage?.cpu || 0}
                    suffix="%"
                    valueStyle={{ 
                      color: resourceUsage?.cpu && resourceUsage.cpu > 80 ? '#ff4d4f' : undefined 
                    }}
                  />
                  <Progress 
                    percent={resourceUsage?.cpu || 0} 
                    showInfo={false}
                    status={resourceUsage?.cpu && resourceUsage.cpu > 80 ? 'exception' : 'normal'}
                  />
                </Card>
              </Col>
              <Col xs={24} sm={12}>
                <Card size="small" data-testid="container-detail-memory-card">
                  <Statistic
                    title={t('resources:containers.memoryUsage')}
                    value={`${resourceUsage?.memoryUsed} / ${resourceUsage?.memoryTotal}`}
                    valueStyle={{ fontSize: 16 }}
                  />
                  <Progress 
                    percent={resourceUsage?.memoryPercent || 0} 
                    status={resourceUsage?.memoryPercent && resourceUsage.memoryPercent > 90 ? 'exception' : 'normal'}
                  />
                </Card>
              </Col>
              <Col xs={24} sm={12}>
                <Card size="small" data-testid="container-detail-network-card">
                  <Space direction="vertical" style={{ width: '100%' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <Text type="secondary">{t('resources:containers.networkIO')}:</Text>
                    </div>
                    <div>
                      <Text style={{ fontSize: 12 }}>
                        <WifiOutlined style={{ marginRight: 4 }} />
                        ↓ {resourceUsage?.netIn} / ↑ {resourceUsage?.netOut}
                      </Text>
                    </div>
                  </Space>
                </Card>
              </Col>
              <Col xs={24} sm={12}>
                <Card size="small" data-testid="container-detail-block-io-card">
                  <Space direction="vertical" style={{ width: '100%' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <Text type="secondary">{t('resources:containers.blockIO')}:</Text>
                    </div>
                    <div>
                      <Text style={{ fontSize: 12 }}>
                        <HddOutlined style={{ marginRight: 4 }} />
                        R: {resourceUsage?.blockRead} / W: {resourceUsage?.blockWrite}
                      </Text>
                    </div>
                  </Space>
                </Card>
              </Col>
            </Row>

            {/* Configuration */}
            <Divider style={{ margin: '24px 0' }}>
              <Space>
                <CodeOutlined />
                {t('resources:containers.configuration')}
              </Space>
            </Divider>

            <Card size="small" style={{ marginBottom: 16 }} data-testid="container-detail-configuration">
              <Space direction="vertical" style={{ width: '100%' }} size="middle">
                {/* Command */}
                <div>
                  <Text type="secondary">{t('resources:containers.command')}:</Text>
                  <br />
                  <Text code style={{ fontSize: 11, wordBreak: 'break-all' }} data-testid="container-detail-command">
                    {container.command}
                  </Text>
                </div>

                {/* Port Mappings */}
                {(container.port_mappings?.length > 0 || container.ports) && (
                  <div>
                    <Text type="secondary">{t('resources:containers.ports')}:</Text>
                    <br />
                    {container.port_mappings && container.port_mappings.length > 0 ? (
                      <Space direction="vertical" size="small" style={{ marginTop: 4 }}>
                        {container.port_mappings.map((mapping, index) => (
                          <Tag key={index} color="blue" data-testid={`container-detail-port-${index}`}>
                            {mapping.host_port ? (
                              `${mapping.host || '0.0.0.0'}:${mapping.host_port} → ${mapping.container_port}/${mapping.protocol}`
                            ) : (
                              `${mapping.container_port}/${mapping.protocol}`
                            )}
                          </Tag>
                        ))}
                      </Space>
                    ) : container.ports ? (
                      <Text style={{ fontSize: 12 }} data-testid="container-detail-ports-text">{container.ports}</Text>
                    ) : null}
                  </div>
                )}

                {/* Networks */}
                <div>
                  <Text type="secondary">{t('resources:containers.networks')}:</Text>
                  <br />
                  <Tag color="purple" data-testid="container-detail-network-tag">{container.networks}</Tag>
                </div>

                {/* Size */}
                <div>
                  <Text type="secondary">{t('resources:containers.size')}:</Text>
                  <br />
                  <Text style={{ fontSize: 12 }} data-testid="container-detail-size">{container.size}</Text>
                </div>

                {/* PIDs */}
                <div>
                  <Text type="secondary">{t('resources:containers.processes')}:</Text>
                  <br />
                  <Tag data-testid="container-detail-pids">{resourceUsage?.pids || 0} {t('resources:containers.pids')}</Tag>
                </div>
              </Space>
            </Card>

            {/* Environment */}
            <Divider style={{ margin: '24px 0' }}>
              <Space>
                <FolderOutlined />
                {t('resources:containers.environment')}
              </Space>
            </Divider>

            <Card size="small" data-testid="container-detail-environment">
              <Space direction="vertical" style={{ width: '100%' }} size="middle">
                {/* Mounts */}
                <div>
                  <Text type="secondary">{t('resources:containers.mounts')}:</Text>
                  <br />
                  <Text style={{ fontSize: 11, wordBreak: 'break-all' }} data-testid="container-detail-mounts">
                    {container.mounts}
                  </Text>
                </div>

                {/* Labels */}
                {container.labels && (
                  <div>
                    <Text type="secondary">{t('resources:containers.labels')}:</Text>
                    <br />
                    <Text style={{ fontSize: 11, wordBreak: 'break-all' }} data-testid="container-detail-labels">
                      {container.labels}
                    </Text>
                  </div>
                )}
              </Space>
            </Card>
          </>
        )}
      </div>
    </>
  )
}