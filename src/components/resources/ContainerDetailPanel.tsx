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
  
  Divider,
  Statistic
} from 'antd'
import { useComponentStyles } from '@/hooks/useComponentStyles'
import {
  DoubleRightOutlined,
  AppstoreOutlined,
  CloudServerOutlined,
  CodeOutlined,
  ApiOutlined,
  HddOutlined,
  WifiOutlined,
  FolderOutlined,
  PlayCircleOutlined,
  PauseCircleOutlined,
  ContainerOutlined
} from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { useTheme } from '@/context/ThemeContext'
import { getPanelWrapperStyles, getStickyHeaderStyles, getContentWrapperStyles } from '@/utils/detailPanelStyles'
import { DETAIL_PANEL_TEXT, DETAIL_PANEL_LAYOUT } from '@/styles/detailPanelStyles'

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
  const componentStyles = useComponentStyles()

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
  const pluginName = isPlugin && container ? container.name.replace('plugin-', '') : null

  if (!visible || !container) {
    return null
  }

  return (
    <>
      {/* Panel */}
      <div
        className="container-detail-panel"
        data-testid="container-detail-panel"
        style={getPanelWrapperStyles({ splitView, visible, theme })}
      >
        {/* Header */}
        <div
          style={getStickyHeaderStyles(theme)}
          data-testid="container-detail-header"
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Space>
              {isPlugin ? (
                <ApiOutlined style={{ fontSize: 24, color: '#1890ff' }} />
              ) : (
                <AppstoreOutlined style={{ fontSize: 24, color: '#52c41a' }} />
              )}
              <Title level={4} style={{ margin: 0 }} data-testid="container-detail-title">
                {isPlugin ? pluginName : container.name}
              </Title>
            </Space>
            <Button
              type="text"
              icon={<DoubleRightOutlined />}
              onClick={onClose}
              style={componentStyles.controlSurface}
              data-testid="container-detail-collapse"
              aria-label="Collapse Panel"
            />
          </div>
          <Space wrap style={{ marginTop: 8 }}>
            <Tag
              color={container.state === 'running' ? 'success' : 'default'}
              icon={container.state === 'running' ? <PlayCircleOutlined /> : <PauseCircleOutlined />}
              data-testid="container-detail-state-tag"
            >
              {container.state}
            </Tag>
            <Tag color="blue" icon={<FolderOutlined />} data-testid="container-detail-repo-tag">
              Repository: {container.repository}
            </Tag>
          </Space>
        </div>

        {/* Content */}
        <div style={getContentWrapperStyles()} data-testid="container-detail-content">

        {container && (
          <>
            {/* Container Information Section */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }} data-testid="container-detail-info-section">
              {isPlugin ? (
                <ApiOutlined style={{ fontSize: 20, color: '#1890ff' }} />
              ) : (
                <ContainerOutlined style={{ fontSize: 20, color: '#1890ff' }} />
              )}
              <Title level={5} style={{ margin: 0 }}>{t('resources:containers.containerInfo')}</Title>
            </div>

            {/* Basic Information */}
            <Card size="small" style={{ ...componentStyles.card, marginBottom: 16 }} data-testid="container-detail-basic-info">
              <Row gutter={[16, 16]} style={componentStyles.marginBottom.lg}>
                <Col span={24}>
                  <Space direction="vertical" style={{ width: '100%' }} size="small">
                    <div style={DETAIL_PANEL_LAYOUT.inlineField}>
                      <Text type="secondary" style={DETAIL_PANEL_TEXT.label}>{t('resources:containers.containerID')}:</Text>
                      <Text copyable style={DETAIL_PANEL_TEXT.monospace} data-testid="container-detail-id">
                        {container.id}
                      </Text>
                    </div>
                    <div style={DETAIL_PANEL_LAYOUT.inlineField}>
                      <Text type="secondary" style={DETAIL_PANEL_TEXT.label}>{t('resources:containers.image')}:</Text>
                      <Text style={DETAIL_PANEL_TEXT.value} data-testid="container-detail-image">{container.image}</Text>
                    </div>
                    <div style={DETAIL_PANEL_LAYOUT.inlineField}>
                      <Text type="secondary" style={DETAIL_PANEL_TEXT.label}>{t('resources:containers.status')}:</Text>
                      <Text style={DETAIL_PANEL_TEXT.value} data-testid="container-detail-status">{container.status}</Text>
                    </div>
                    <div style={DETAIL_PANEL_LAYOUT.inlineField}>
                      <Text type="secondary" style={DETAIL_PANEL_TEXT.label}>{t('resources:containers.created')}:</Text>
                      <Text style={DETAIL_PANEL_TEXT.value} data-testid="container-detail-created">{container.created}</Text>
                    </div>
                  </Space>
                </Col>
              </Row>
            </Card>

            {/* Resource Usage */}
            <Divider style={{ margin: '24px 0' }}>
              <Space>
                <CloudServerOutlined style={{ fontSize: 16 }} />
                {t('resources:containers.resourceUsage')}
              </Space>
            </Divider>

            <Row gutter={[16, 16]} style={componentStyles.marginBottom.lg}>
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
                <CodeOutlined style={{ fontSize: 16 }} />
                {t('resources:containers.configuration')}
              </Space>
            </Divider>

            <Card size="small" style={{ ...componentStyles.card, marginBottom: 16 }} data-testid="container-detail-configuration">
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
                {(container.port_mappings && container.port_mappings.length > 0 || container.ports) && (
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
                <div style={DETAIL_PANEL_LAYOUT.inlineField}>
                  <Text type="secondary" style={DETAIL_PANEL_TEXT.label}>{t('resources:containers.networks')}:</Text>
                  <Tag color="purple" data-testid="container-detail-network-tag">{container.networks}</Tag>
                </div>

                {/* Size */}
                <div style={DETAIL_PANEL_LAYOUT.inlineField}>
                  <Text type="secondary" style={DETAIL_PANEL_TEXT.label}>{t('resources:containers.size')}:</Text>
                  <Text style={DETAIL_PANEL_TEXT.value} data-testid="container-detail-size">{container.size}</Text>
                </div>

                {/* PIDs */}
                <div style={DETAIL_PANEL_LAYOUT.inlineField}>
                  <Text type="secondary" style={DETAIL_PANEL_TEXT.label}>{t('resources:containers.processes')}:</Text>
                  <Tag data-testid="container-detail-pids">{resourceUsage?.pids || 0} {t('resources:containers.pids')}</Tag>
                </div>
              </Space>
            </Card>

            {/* Environment */}
            <Divider style={{ margin: '24px 0' }}>
              <Space>
                <FolderOutlined style={{ fontSize: 16 }} />
                {t('resources:containers.environment')}
              </Space>
            </Divider>

            <Card size="small" style={componentStyles.card} data-testid="container-detail-environment">
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
      </div>
    </>
  )
}