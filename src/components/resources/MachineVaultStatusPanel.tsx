import React, { useEffect, useMemo, useState } from 'react'
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
  List,
  Statistic,
  Badge
} from 'antd'
import { useComponentStyles } from '@/hooks/useComponentStyles'
import { 
  CloseOutlined,
  DesktopOutlined,
  DatabaseOutlined,
  GlobalOutlined,
  HddOutlined,
  WifiOutlined,
  ApiOutlined,
  ContainerOutlined,
  CloudServerOutlined,
  InfoCircleOutlined,
  AppstoreOutlined,
  FieldTimeOutlined,
  CodeOutlined,
  CompassOutlined
} from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { Machine } from '@/types'
import { useTheme } from '@/context/ThemeContext'
import { getLocalizedRelativeTime, formatTimestampAsIs } from '@/utils/timeUtils'
import { calculateResourcePercent } from '@/utils/sizeUtils'
import { DistributedStorageSection } from './DistributedStorageSection'
import AuditTraceModal from '@/components/common/AuditTraceModal'

const { Text, Title } = Typography

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
  partitions: Array<{
    name: string
    path: string
    size_bytes: number
    size_human: string
    filesystem: string | null
    mountpoint: string | null
  }>
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

export const MachineVaultStatusPanel: React.FC<MachineVaultStatusPanelProps> = ({ 
  machine, 
  visible, 
  onClose,
  splitView = false 
}) => {
  const { t } = useTranslation(['machines', 'resources', 'common', 'distributedStorage'])
  const { theme } = useTheme()
  const componentStyles = useComponentStyles()
  
  // State for audit trace modal
  const [auditTraceModal, setAuditTraceModal] = useState<{
    open: boolean
    entityType: string | null
    entityIdentifier: string | null
    entityName?: string
  }>({ open: false, entityType: null, entityIdentifier: null })

  // Parse vault status data
  const vaultData = useMemo((): { system?: SystemInfo; network?: any; block_devices?: BlockDevice[]; system_containers?: Container[] } | null => {
    if (!machine?.vaultStatus) return null

    try {
      // Check if vaultStatus is invalid
      if (machine.vaultStatus.trim().startsWith('jq:') || 
          machine.vaultStatus.trim().startsWith('error:') ||
          !machine.vaultStatus.trim().startsWith('{')) {
        return null
      }

      const vaultStatusData = JSON.parse(machine.vaultStatus)
      
      if (vaultStatusData.status === 'completed' && vaultStatusData.result) {
        // Clean the result string
        let cleanedResult = vaultStatusData.result
        
        // Remove trailing content after JSON
        const jsonEndMatch = cleanedResult.match(/(\}[\s\n]*$)/)
        if (jsonEndMatch) {
          const lastBraceIndex = cleanedResult.lastIndexOf('}')
          if (lastBraceIndex < cleanedResult.length - 10) {
            cleanedResult = cleanedResult.substring(0, lastBraceIndex + 1)
          }
        }
        
        // Handle newline followed by jq errors
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

  // Handle escape key
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && visible) {
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

  if (!machine || !visible) return null

  return (
    <>
      {/* Panel */}
      <div
        className="machine-vault-status-panel"
        style={splitView ? {
          height: '100%',
          backgroundColor: theme === 'dark' ? '#141414' : '#fff',
          overflowY: 'auto',
          overflowX: 'hidden',
        } : {
          position: 'fixed',
          top: 0,
          right: visible ? 0 : '-520px',
          bottom: 0,
          width: '520px',
          maxWidth: '100vw',
          backgroundColor: theme === 'dark' ? '#141414' : '#fff',
          boxShadow: '-2px 0 8px rgba(0, 0, 0, 0.15)',
          zIndex: 1000,
          transition: 'right 0.3s ease-in-out',
          overflowY: 'auto',
          overflowX: 'hidden',
        }}
      >
        {/* Header */}
        <div 
          style={{ 
            padding: '16px 24px',
            borderBottom: `1px solid ${theme === 'dark' ? '#303030' : '#f0f0f0'}`,
            position: 'sticky',
            top: 0,
            backgroundColor: theme === 'dark' ? '#141414' : '#fff',
            zIndex: splitView ? 0 : 1,
          }}
          data-testid="vault-status-header"
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Space>
              <CloudServerOutlined style={{ fontSize: 24, color: '#556b2f' }} />
              <Title level={4} style={{ margin: 0 }} data-testid="vault-status-machine-name">{machine.machineName}</Title>
            </Space>
            <Button
              type="text"
              icon={<CloseOutlined />}
              onClick={onClose}
              style={componentStyles.touchTarget}
              data-testid="vault-status-close"
            />
          </div>
          <Space wrap style={{ marginTop: 8 }}>
            <Tag color="#8FBC8F" icon={<AppstoreOutlined />} data-testid="vault-status-team-tag">Team: {machine.teamName}</Tag>
            <Tag color="green" icon={<ApiOutlined />} data-testid="vault-status-bridge-tag">Bridge: {machine.bridgeName}</Tag>
            {machine.regionName && <Tag color="purple" icon={<GlobalOutlined />} data-testid="vault-status-region-tag">Region: {machine.regionName}</Tag>}
            <Badge count={machine.queueCount} style={{ backgroundColor: '#52c41a' }} data-testid="vault-status-queue-badge">
              <Tag color="blue">{t('machines:queueItems')}</Tag>
            </Badge>
            <Tag color="blue" data-testid="vault-status-version-tag">{t('machines:vaultVersion')}: {machine.vaultVersion}</Tag>
          </Space>
          {machine.vaultStatusTime && (
            <div style={{ marginTop: 8 }}>
              <Text type="secondary" style={{ fontSize: 12 }} title={formatTimestampAsIs(machine.vaultStatusTime, 'datetime')} data-testid="vault-status-last-updated">
                {t('machines:lastUpdated')}: {getLocalizedRelativeTime(machine.vaultStatusTime, t)}
              </Text>
            </div>
          )}
        </div>

        {/* Content */}
        <div style={{ padding: '24px' }} data-testid="vault-status-content">
          {!vaultData ? (
            <Empty 
              description={t('machines:noVaultData')}
              style={{ marginTop: 48 }}
              data-testid="vault-status-empty"
            />
          ) : (
            <>
              {/* System Information Section */}
              {vaultData.system && (
                <>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
                    <DesktopOutlined style={{ fontSize: 20, color: '#556b2f' }} />
                    <Title level={5} style={{ margin: 0 }} data-testid="vault-status-system-info-title">{t('resources:repositories.systemInfo')}</Title>
                  </div>
                  
                  <Row gutter={[16, 16]} style={componentStyles.marginBottom.md}>
                    <Col span={12}>
                      <Card size="small" style={{ height: '100%' }} data-testid="vault-status-hostname-card">
                        <Statistic
                          title={t('resources:repositories.hostname')}
                          value={vaultData.system.hostname}
                          prefix={<CloudServerOutlined />}
                          valueStyle={{ fontSize: 16 }}
                        />
                      </Card>
                    </Col>
                    <Col span={12}>
                      <Card size="small" style={{ height: '100%' }} data-testid="vault-status-uptime-card">
                        <Statistic
                          title={t('resources:repositories.uptime')}
                          value={vaultData.system.uptime}
                          prefix={<FieldTimeOutlined />}
                          valueStyle={{ fontSize: 16 }}
                        />
                      </Card>
                    </Col>
                    <Col span={24}>
                      <Card size="small" data-testid="vault-status-os-info-card">
                        <Space direction="vertical" style={{ width: '100%' }} size="small">
                          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                            <Text type="secondary">{t('resources:repositories.osName')}:</Text>
                            <Text strong data-testid="vault-status-os-name">{vaultData.system.os_name}</Text>
                          </div>
                          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                            <Text type="secondary">{t('resources:repositories.kernel')}:</Text>
                            <Text data-testid="vault-status-kernel">{vaultData.system.kernel}</Text>
                          </div>
                          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                            <Text type="secondary">{t('resources:repositories.cpu')}:</Text>
                            <Text data-testid="vault-status-cpu">{vaultData.system.cpu_count} × {vaultData.system.cpu_model}</Text>
                          </div>
                          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                            <Text type="secondary">{t('resources:repositories.systemTime')}:</Text>
                            <Text data-testid="vault-status-system-time">{vaultData.system.system_time_human} ({vaultData.system.timezone})</Text>
                          </div>
                        </Space>
                      </Card>
                    </Col>
                  </Row>

                  <Divider style={{ margin: '24px 0' }}>
                    <Space>
                      <InfoCircleOutlined />
                      {t('resources:repositories.resourceUsage')}
                    </Space>
                  </Divider>

                  {/* Resource Usage Cards */}
                  <Row gutter={[16, 16]} style={componentStyles.marginBottom.lg}>
                    {/* Memory Card */}
                    <Col span={24}>
                      <Card size="small" data-testid="vault-status-memory-card">
                        <div style={{ marginBottom: 12 }}>
                          <Space>
                            <DatabaseOutlined style={{ color: '#1890ff' }} />
                            <Text strong>{t('resources:repositories.memory')}</Text>
                          </Space>
                        </div>
                        <div style={{ marginBottom: 8 }}>
                          <Text>{vaultData.system.memory.used} / {vaultData.system.memory.total}</Text>
                        </div>
                        <Progress 
                          percent={calculateResourcePercent(
                            undefined,
                            vaultData.system.memory.used,
                            vaultData.system.memory.total
                          )} 
                          strokeColor="#1890ff"
                          trailColor={theme === 'dark' ? 'rgba(255,255,255,0.08)' : undefined}
                        />
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          {t('resources:repositories.available')}: {vaultData.system.memory.available}
                        </Text>
                      </Card>
                    </Col>

                    {/* Root Disk Card */}
                    <Col span={24}>
                      <Card size="small" data-testid="vault-status-disk-card">
                        <div style={{ marginBottom: 12 }}>
                          <Space>
                            <HddOutlined style={{ color: '#fa8c16' }} />
                            <Text strong>{t('resources:repositories.rootDisk')}</Text>
                          </Space>
                        </div>
                        <div style={{ marginBottom: 8 }}>
                          <Text>{vaultData.system.disk.used} / {vaultData.system.disk.total}</Text>
                        </div>
                        <Progress 
                          percent={calculateResourcePercent(
                            vaultData.system.disk.use_percent,
                            vaultData.system.disk.used,
                            vaultData.system.disk.total
                          )} 
                          status={(() => {
                            const percent = parseInt(vaultData.system.disk.use_percent) || 0
                            return percent > 90 ? 'exception' : 'normal'
                          })()}
                          strokeColor={(() => {
                            const percent = parseInt(vaultData.system.disk.use_percent) || 0
                            return percent > 90 ? '#ff4d4f' : '#fa8c16'
                          })()}
                          trailColor={theme === 'dark' ? 'rgba(255,255,255,0.08)' : undefined}
                        />
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          {t('resources:repositories.available')}: {vaultData.system.disk.available}
                        </Text>
                      </Card>
                    </Col>

                    {/* Datastore Card */}
                    {vaultData.system.datastore?.path && (
                      <Col span={24}>
                        <Card size="small" data-testid="vault-status-datastore-card">
                          <div style={{ marginBottom: 12 }}>
                            <Space>
                              <DatabaseOutlined style={{ color: '#52c41a' }} />
                              <Text strong>{t('resources:repositories.datastore')}</Text>
                            </Space>
                          </div>
                          <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 8, wordBreak: 'break-all' }}>
                            {vaultData.system.datastore.path}
                          </Text>
                          <div style={{ marginBottom: 8 }}>
                            <Text>{vaultData.system.datastore.used} / {vaultData.system.datastore.total}</Text>
                          </div>
                          <Progress 
                            percent={calculateResourcePercent(
                              vaultData.system.datastore.use_percent,
                              vaultData.system.datastore.used,
                              vaultData.system.datastore.total
                            )} 
                            status={(() => {
                              const percent = parseInt(vaultData.system.datastore.use_percent) || 0
                              return percent > 90 ? 'exception' : 'normal'
                            })()}
                            strokeColor={(() => {
                              const percent = parseInt(vaultData.system.datastore.use_percent) || 0
                              return percent > 90 ? '#ff4d4f' : '#52c41a'
                            })()}
                            trailColor={theme === 'dark' ? 'rgba(255,255,255,0.08)' : undefined}
                          />
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            {t('resources:repositories.available')}: {vaultData.system.datastore.available}
                          </Text>
                        </Card>
                      </Col>
                    )}
                  </Row>
                </>
              )}

              {/* Network Information Section */}
              {vaultData.network && (
                <>
                  <Divider style={{ margin: '24px 0' }}>
                    <Space>
                      <WifiOutlined />
                      {t('resources:repositories.networkInfo')}
                    </Space>
                  </Divider>

                  {/* Default Gateway Info */}
                  {vaultData.network.default_gateway && (
                    <Card size="small" style={{ marginBottom: 16 }} data-testid="vault-status-gateway-card">
                      <Space direction="vertical" style={{ width: '100%' }} size="small">
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <Text type="secondary">{t('resources:repositories.defaultGateway')}:</Text>
                          <Text strong data-testid="vault-status-gateway">{vaultData.network.default_gateway}</Text>
                        </div>
                        {vaultData.network.default_interface && (
                          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                            <Text type="secondary">{t('resources:repositories.defaultInterface')}:</Text>
                            <Text data-testid="vault-status-interface">{vaultData.network.default_interface}</Text>
                          </div>
                        )}
                      </Space>
                    </Card>
                  )}

                  {/* Network Interfaces List */}
                  <List
                    dataSource={vaultData.network.interfaces.filter((iface: NetworkInterface) => 
                      iface.state !== 'unknown' && iface.name !== 'lo'
                    )}
                    style={componentStyles.marginBottom.lg}
                    data-testid="vault-status-network-list"
                    renderItem={(iface: NetworkInterface) => (
                      <Card size="small" style={{ marginBottom: 12 }} data-testid={`vault-status-network-${iface.name}`}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                          <Space>
                            <CompassOutlined style={{ color: '#1890ff' }} />
                            <Text strong data-testid={`vault-status-network-name-${iface.name}`}>{iface.name}</Text>
                          </Space>
                          <Tag color={iface.state === 'UP' ? 'success' : 'default'} data-testid={`vault-status-network-state-${iface.name}`}>{iface.state}</Tag>
                        </div>
                        <Space direction="vertical" style={{ width: '100%' }} size="small">
                          {iface.ipv4_addresses.length > 0 && (
                            <div>
                              <Text type="secondary">{t('resources:repositories.ipAddresses')}:</Text>
                              {iface.ipv4_addresses.map((ip, idx) => (
                                <div key={idx} style={{ marginLeft: 16 }}>
                                  <Tag color="blue" data-testid={`vault-status-ip-${ip}`}>{ip}</Tag>
                                </div>
                              ))}
                            </div>
                          )}
                          {iface.mac_address && iface.mac_address !== 'unknown' && (
                            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                              <Text type="secondary">{t('resources:repositories.macAddress')}:</Text>
                              <Text style={{ fontSize: 12 }}>{iface.mac_address}</Text>
                            </div>
                          )}
                          {iface.mtu > 0 && (
                            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                              <Text type="secondary">MTU:</Text>
                              <Text>{iface.mtu}</Text>
                            </div>
                          )}
                        </Space>
                      </Card>
                    )}
                  />
                </>
              )}

              {/* Block Devices Section */}
              {vaultData.block_devices && vaultData.block_devices.length > 0 && (
                <>
                  <Divider style={{ margin: '24px 0' }}>
                    <Space>
                      <HddOutlined />
                      {t('resources:repositories.blockDevices')}
                    </Space>
                  </Divider>

                  <List
                    dataSource={vaultData.block_devices}
                    style={componentStyles.marginBottom.lg}
                    data-testid="vault-status-block-devices-list"
                    renderItem={(device: BlockDevice) => (
                      <Card size="small" style={{ marginBottom: 12 }} data-testid={`vault-status-block-device-${device.name}`}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                          <Space>
                            <HddOutlined style={{ color: '#fa8c16' }} />
                            <Text strong data-testid={`vault-status-device-path-${device.name}`}>{device.path}</Text>
                          </Space>
                          <Space>
                            <Tag data-testid={`vault-status-device-type-${device.name}`}>{device.type}</Tag>
                            <Tag color="blue" data-testid={`vault-status-device-size-${device.name}`}>{device.size_human}</Tag>
                          </Space>
                        </div>
                        <Space direction="vertical" style={{ width: '100%' }} size="small">
                          {device.model && device.model !== 'Unknown' && (
                            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                              <Text type="secondary">{t('resources:repositories.model')}:</Text>
                              <Text style={{ fontSize: 12 }}>{device.model}</Text>
                            </div>
                          )}
                          {device.partitions.length > 0 && (
                            <div>
                              <Text type="secondary">{t('resources:repositories.partitions')}:</Text>
                              <div style={{ marginLeft: 16, marginTop: 8 }}>
                                {device.partitions.map((part, idx) => (
                                  <div key={idx} style={{ marginBottom: 4 }}>
                                    <Space>
                                      <CodeOutlined style={{ fontSize: 12 }} />
                                      <Text style={{ fontSize: 12 }}>
                                        {part.name}: {part.size_human}
                                        {part.filesystem && ` (${part.filesystem})`}
                                        {part.mountpoint && ` → ${part.mountpoint}`}
                                      </Text>
                                    </Space>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </Space>
                      </Card>
                    )}
                  />
                </>
              )}

              {/* System Containers Section */}
              {vaultData.system_containers && vaultData.system_containers.length > 0 && (
                <>
                  <Divider style={{ margin: '24px 0' }}>
                    <Space>
                      <ContainerOutlined />
                      {t('resources:repositories.systemContainers')}
                    </Space>
                  </Divider>

                  <List
                    dataSource={vaultData.system_containers}
                    style={componentStyles.marginBottom.lg}
                    data-testid="vault-status-containers-list"
                    renderItem={(container: Container) => (
                      <Card size="small" style={{ marginBottom: 12 }} data-testid={`vault-status-container-${container.id}`}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                          <Space>
                            <ContainerOutlined style={{ color: '#722ed1' }} />
                            <Text strong data-testid={`vault-status-container-name-${container.id}`}>{container.name}</Text>
                          </Space>
                          <Tag color={container.state === 'running' ? 'success' : 'default'} data-testid={`vault-status-container-state-${container.id}`}>
                            {container.state}
                          </Tag>
                        </div>
                        <Space direction="vertical" style={{ width: '100%' }} size="small">
                          <Text type="secondary" style={{ fontSize: 12 }} ellipsis>
                            {container.image}
                          </Text>
                          {container.cpu_percent && (
                            <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                              <Text type="secondary">CPU:</Text>
                              <Text>{container.cpu_percent}</Text>
                            </Space>
                          )}
                          {container.memory_usage && (
                            <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                              <Text type="secondary">{t('resources:repositories.memory')}:</Text>
                              <Text>{container.memory_usage}</Text>
                            </Space>
                          )}
                        </Space>
                      </Card>
                    )}
                  />
                </>
              )}
              
              {/* Distributed Storage Section */}
              {machine && (
                <div data-testid="vault-status-distributed-storage">
                  <DistributedStorageSection 
                    machine={machine}
                    onViewDetails={() => {
                      setAuditTraceModal({
                        open: true,
                        entityType: 'Machine',
                        entityIdentifier: machine.machineName,
                        entityName: machine.machineName
                      })
                    }}
                  />
                </div>
              )}
            </>
          )}
        </div>
      </div>
      
      {/* Audit Trace Modal */}
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