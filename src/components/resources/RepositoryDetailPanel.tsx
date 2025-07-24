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
  Statistic,
  Badge
} from 'antd'
import { 
  CloseOutlined,
  DatabaseOutlined,
  ClockCircleOutlined,
  HddOutlined,
  InfoCircleOutlined,
  AppstoreOutlined,
  FieldTimeOutlined,
  CloudServerOutlined,
  FolderOutlined,
  CheckCircleOutlined,
  StopOutlined
} from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { Repository } from '@/api/queries/repositories'
import { useTheme } from '@/context/ThemeContext'
import { useMachines } from '@/api/queries/machines'

const { Text, Title } = Typography

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
}

export const RepositoryDetailPanel: React.FC<RepositoryDetailPanelProps> = ({ 
  repository, 
  visible, 
  onClose,
  splitView = false 
}) => {
  const { t } = useTranslation(['resources', 'common', 'machines'])
  const { theme } = useTheme()
  const { data: machines = [] } = useMachines(repository?.teamName)

  // Find the machine that has this repository data
  const repositoryData = useMemo(() => {
    if (!repository || !machines.length) return null

    for (const machine of machines) {
      if (!machine.vaultStatus) continue

      try {
        // Check if vaultStatus is invalid
        if (machine.vaultStatus.trim().startsWith('jq:') || 
            machine.vaultStatus.trim().startsWith('error:') ||
            !machine.vaultStatus.trim().startsWith('{')) {
          continue
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
          
          const result = JSON.parse(cleanedResult)
          
          // Find the repository in the machine's data
          if (result.repositories && Array.isArray(result.repositories)) {
            const repoData = result.repositories.find((r: RepositoryVaultData) => {
              // Match by repository name or GUID
              return r.name === repository.repositoryName || r.name === repository.repositoryGuid
            })
            
            if (repoData) {
              return {
                machine: machine,
                repositoryData: repoData,
                systemData: result.system
              }
            }
          }
        }
      } catch (err) {
        console.error('Error parsing vault status:', err)
      }
    }
    
    return null
  }, [repository, machines])

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

  if (!repository || !visible) return null

  return (
    <>
      {/* Panel */}
      <div
        className="repository-detail-panel"
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
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Space>
              <FolderOutlined style={{ fontSize: 24, color: '#8FBC8F' }} />
              <Title level={4} style={{ margin: 0 }}>{repository.repositoryName}</Title>
            </Space>
            <Button
              type="text"
              icon={<CloseOutlined />}
              onClick={onClose}
            />
          </div>
          <Space wrap style={{ marginTop: 8 }}>
            <Tag color="#8FBC8F" icon={<AppstoreOutlined />}>Team: {repository.teamName}</Tag>
            {repositoryData && (
              <Tag color="green" icon={<CloudServerOutlined />}>Machine: {repositoryData.machine.machineName}</Tag>
            )}
            <Tag color="blue">{t('resources:repositories.vaultVersion')}: {repository.vaultVersion}</Tag>
          </Space>
        </div>

        {/* Content */}
        <div style={{ padding: '24px' }}>
          {!repositoryData ? (
            <Empty 
              description={t('resources:repositories.noRepositoryData')}
              style={{ marginTop: 48 }}
            />
          ) : (
            <>
              {/* Repository Information Section */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
                <FolderOutlined style={{ fontSize: 20, color: '#8FBC8F' }} />
                <Title level={5} style={{ margin: 0 }}>{t('resources:repositories.repositoryInfo')}</Title>
              </div>
              
              <Row gutter={[16, 16]}>
                <Col span={24}>
                  <Card size="small">
                    <Space direction="vertical" style={{ width: '100%' }} size="small">
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <Text type="secondary">{t('resources:repositories.repositoryGuid')}:</Text>
                        <Text copyable style={{ fontSize: 11, fontFamily: 'monospace' }}>{repository.repositoryGuid}</Text>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <Text type="secondary">{t('resources:repositories.status')}:</Text>
                        <Space>
                          {repositoryData.repositoryData.mounted ? (
                            <Tag color="success" icon={<CheckCircleOutlined />}>
                              {t('resources:repositories.mounted')}
                            </Tag>
                          ) : (
                            <Tag color="default" icon={<StopOutlined />}>
                              {t('resources:repositories.notMounted')}
                            </Tag>
                          )}
                          {repositoryData.repositoryData.accessible && (
                            <Tag color="green">{t('resources:repositories.accessible')}</Tag>
                          )}
                        </Space>
                      </div>
                      {repositoryData.repositoryData.has_rediaccfile && (
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <Text type="secondary">{t('resources:repositories.rediaccfile')}:</Text>
                          <Tag color="purple">{t('resources:repositories.hasRediaccfile')}</Tag>
                        </div>
                      )}
                    </Space>
                  </Card>
                </Col>
              </Row>

              <Divider style={{ margin: '24px 0' }}>
                <Space>
                  <InfoCircleOutlined />
                  {t('resources:repositories.storageInfo')}
                </Space>
              </Divider>

              {/* Storage Information */}
              <Row gutter={[16, 16]}>
                <Col span={12}>
                  <Card size="small" style={{ height: '100%' }}>
                    <Statistic
                      title={t('resources:repositories.imageSize')}
                      value={repositoryData.repositoryData.size_human}
                      prefix={<HddOutlined />}
                    />
                  </Card>
                </Col>
                <Col span={12}>
                  <Card size="small" style={{ height: '100%' }}>
                    <Statistic
                      title={t('resources:repositories.lastModified')}
                      value={repositoryData.repositoryData.modified_human}
                      prefix={<ClockCircleOutlined />}
                    />
                  </Card>
                </Col>
                
                {/* Disk Usage Card - only show if mounted */}
                {repositoryData.repositoryData.mounted && repositoryData.repositoryData.disk_space && (
                  <Col span={24}>
                    <Card size="small">
                      <div style={{ marginBottom: 12 }}>
                        <Space>
                          <DatabaseOutlined style={{ color: '#52c41a' }} />
                          <Text strong>{t('resources:repositories.diskUsage')}</Text>
                        </Space>
                      </div>
                      <div style={{ marginBottom: 8 }}>
                        <Text>{repositoryData.repositoryData.disk_space.used} / {repositoryData.repositoryData.disk_space.total}</Text>
                      </div>
                      <Progress 
                        percent={parseInt(repositoryData.repositoryData.disk_space.use_percent)} 
                        status={parseInt(repositoryData.repositoryData.disk_space.use_percent) > 90 ? 'exception' : 'normal'}
                        strokeColor={parseInt(repositoryData.repositoryData.disk_space.use_percent) > 90 ? '#ff4d4f' : '#52c41a'}
                        trailColor={theme === 'dark' ? 'rgba(255,255,255,0.08)' : undefined}
                      />
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        {t('resources:repositories.available')}: {repositoryData.repositoryData.disk_space.available}
                      </Text>
                    </Card>
                  </Col>
                )}
              </Row>

              {/* File Paths Section */}
              <Divider style={{ margin: '24px 0' }}>
                <Space>
                  <FolderOutlined />
                  {t('resources:repositories.filePaths')}
                </Space>
              </Divider>

              <Card size="small">
                <Space direction="vertical" style={{ width: '100%' }} size="small">
                  <div>
                    <Text type="secondary">{t('resources:repositories.imagePath')}:</Text>
                    <Text copyable style={{ display: 'block', fontSize: 12, wordBreak: 'break-all', marginTop: 4 }}>
                      {repositoryData.repositoryData.image_path}
                    </Text>
                  </div>
                  {repositoryData.repositoryData.mount_path && (
                    <div>
                      <Text type="secondary">{t('resources:repositories.mountPath')}:</Text>
                      <Text copyable style={{ display: 'block', fontSize: 12, wordBreak: 'break-all', marginTop: 4 }}>
                        {repositoryData.repositoryData.mount_path}
                      </Text>
                    </div>
                  )}
                </Space>
              </Card>

              {/* Repository Activity Section */}
              {repositoryData.repositoryData.mounted && (
                <>
                  <Divider style={{ margin: '24px 0' }}>
                    <Space>
                      <FieldTimeOutlined />
                      {t('resources:repositories.activity')}
                    </Space>
                  </Divider>

                  <Row gutter={[16, 16]}>
                    {repositoryData.repositoryData.docker_running && (
                      <Col span={12}>
                        <Card size="small" style={{ height: '100%' }}>
                          <Statistic
                            title={t('resources:repositories.containers')}
                            value={repositoryData.repositoryData.container_count}
                            valueStyle={{ color: '#1890ff' }}
                          />
                        </Card>
                      </Col>
                    )}
                    {repositoryData.repositoryData.has_services && (
                      <Col span={12}>
                        <Card size="small" style={{ height: '100%' }}>
                          <Statistic
                            title={t('resources:repositories.services')}
                            value={repositoryData.repositoryData.service_count}
                            valueStyle={{ color: '#fa8c16' }}
                          />
                        </Card>
                      </Col>
                    )}
                  </Row>
                </>
              )}

              {/* System Information Section - if available */}
              {repositoryData.systemData && (
                <>
                  <Divider style={{ margin: '24px 0' }}>
                    <Space>
                      <CloudServerOutlined />
                      {t('resources:repositories.machineSystemInfo')}
                    </Space>
                  </Divider>

                  <Card size="small">
                    <Space direction="vertical" style={{ width: '100%' }} size="small">
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <Text type="secondary">{t('resources:repositories.datastore')}:</Text>
                        <Text style={{ fontSize: 12, wordBreak: 'break-all' }}>
                          {repositoryData.systemData.datastore?.path || 'N/A'}
                        </Text>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <Text type="secondary">{t('resources:repositories.datastoreUsage')}:</Text>
                        <Text style={{ fontSize: 12 }}>
                          {repositoryData.systemData.datastore?.used || '0'} / {repositoryData.systemData.datastore?.total || '0'}
                        </Text>
                      </div>
                    </Space>
                  </Card>
                </>
              )}
            </>
          )}
        </div>
      </div>
    </>
  )
}