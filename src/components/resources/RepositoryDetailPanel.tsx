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
  Alert
} from 'antd'
import { useComponentStyles } from '@/hooks/useComponentStyles'
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
  WarningOutlined
} from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { Repository } from '@/api/queries/repositories'
import { useTheme } from '@/context/ThemeContext'
import { useMachines } from '@/api/queries/machines'
import { getPanelWrapperStyles, getStickyHeaderStyles, getContentWrapperStyles } from '@/utils/detailPanelStyles'
import { abbreviatePath } from '@/utils/pathUtils'
import { DETAIL_PANEL_TEXT, DETAIL_PANEL_LAYOUT } from '@/styles/detailPanelStyles'

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
  const componentStyles = useComponentStyles()

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
              // Extract services for this repository
              const servicesForRepo: ServiceData[] = []
              if (result.services && Array.isArray(result.services)) {
                result.services.forEach((service: any) => {
                  // Check if service belongs to this repository
                  if (service.repository === repoData.name || 
                      service.repository === repository.repositoryGuid) {
                    servicesForRepo.push(service)
                  } else if (service.service_name || service.unit_file) {
                    // Check by service name pattern
                    const serviceName = service.service_name || service.unit_file || ''
                    const guidMatch = serviceName.match(/rediacc_([0-9a-f-]{36})_/)
                    if (guidMatch && (guidMatch[1] === repository.repositoryGuid || guidMatch[1] === repoData.name)) {
                      servicesForRepo.push(service)
                    }
                  }
                })
              }

              return {
                machine: machine,
                repositoryData: repoData,
                systemData: result.system,
                services: servicesForRepo
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
        data-testid="repo-detail-panel"
        style={getPanelWrapperStyles({ splitView, visible, theme })}
      >
        {/* Header */}
        <div
          style={getStickyHeaderStyles(theme)}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Space>
              <FolderOutlined style={{ fontSize: 24, color: '#8FBC8F' }} />
              <Title level={4} style={{ margin: 0 }} data-testid={`repo-detail-title-${repository.repositoryName}`}>{repository.repositoryName}</Title>
            </Space>
            <Button
              type="text"
              icon={<DoubleRightOutlined />}
              onClick={onClose}
              style={componentStyles.controlSurface}
              data-testid="repo-detail-collapse"
              aria-label="Collapse Panel"
            />
          </div>
          <Space wrap style={{ marginTop: 8 }}>
            <Tag color="#8FBC8F" icon={<AppstoreOutlined />} data-testid={`repo-detail-team-tag-${repository.repositoryName}`}>Team: {repository.teamName}</Tag>
            {repositoryData && (
              <Tag color="green" icon={<CloudServerOutlined />} data-testid={`repo-detail-machine-tag-${repository.repositoryName}`}>Machine: {repositoryData.machine.machineName}</Tag>
            )}
            <Tag color="blue" data-testid={`repo-detail-vault-version-tag-${repository.repositoryName}`}>{t('resources:repositories.vaultVersion')}: {repository.vaultVersion}</Tag>
          </Space>
        </div>

        {/* Content */}
        <div style={getContentWrapperStyles()} data-testid="repo-detail-content">
          {!repositoryData ? (
            <Empty 
              description={t('resources:repositories.noRepositoryData')}
              style={{ marginTop: 48 }}
              data-testid="repo-detail-empty-state"
            />
          ) : (
            <>
              {/* Repository Information Section */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }} data-testid="repo-detail-info-section">
                <FolderOutlined style={{ fontSize: 20, color: '#8FBC8F' }} />
                <Title level={5} style={{ margin: 0 }}>{t('resources:repositories.repositoryInfo')}</Title>
              </div>
              
              <Row gutter={[16, 16]} style={componentStyles.marginBottom.lg}>
                <Col span={24}>
                  <Card size="small" style={componentStyles.card} data-testid="repo-detail-info-card">
                    <Space direction="vertical" style={{ width: '100%' }} size="small">
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <Text type="secondary">{t('resources:repositories.repositoryGuid')}:</Text>
                        <Text copyable style={{ fontSize: 11, fontFamily: 'monospace' }} data-testid={`repo-detail-guid-${repository.repositoryName}`}>{repository.repositoryGuid}</Text>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <Text type="secondary">{t('resources:repositories.status')}:</Text>
                        <Space>
                          {repositoryData.repositoryData.mounted ? (
                            <Tag color="success" icon={<CheckCircleOutlined />} data-testid={`repo-detail-status-mounted-${repository.repositoryName}`}>
                              {t('resources:repositories.mounted')}
                            </Tag>
                          ) : (
                            <Tag color="default" icon={<StopOutlined />} data-testid={`repo-detail-status-unmounted-${repository.repositoryName}`}>
                              {t('resources:repositories.notMounted')}
                            </Tag>
                          )}
                          {repositoryData.repositoryData.accessible && (
                            <Tag color="green" data-testid={`repo-detail-status-accessible-${repository.repositoryName}`}>{t('resources:repositories.accessible')}</Tag>
                          )}
                        </Space>
                      </div>
                      {repositoryData.repositoryData.has_rediaccfile && (
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <Text type="secondary">{t('resources:repositories.rediaccfile')}:</Text>
                          <Tag color="purple" data-testid={`repo-detail-rediaccfile-${repository.repositoryName}`}>{t('resources:repositories.hasRediaccfile')}</Tag>
                        </div>
                      )}
                      {repositoryData.repositoryData.docker_running && repositoryData.repositoryData.volume_status && repositoryData.repositoryData.volume_status !== 'none' && (
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <Text type="secondary">Docker Volumes:</Text>
                          {repositoryData.repositoryData.volume_status === 'safe' ? (
                            <Tag color="success" icon={<CheckCircleOutlined />} data-testid={`repo-detail-volume-safe-${repository.repositoryName}`}>
                              {repositoryData.repositoryData.internal_volumes} Safe Volume{repositoryData.repositoryData.internal_volumes !== 1 ? 's' : ''}
                            </Tag>
                          ) : repositoryData.repositoryData.volume_status === 'warning' ? (
                            <Tag color="warning" icon={<WarningOutlined />} data-testid={`repo-detail-volume-warning-${repository.repositoryName}`}>
                              {repositoryData.repositoryData.external_volumes} External, {repositoryData.repositoryData.internal_volumes} Internal
                            </Tag>
                          ) : null}
                        </div>
                      )}
                    </Space>
                  </Card>
                </Col>
              </Row>

              {/* External Volume Warning Alert */}
              {repositoryData.repositoryData.volume_status === 'warning' && repositoryData.repositoryData.external_volume_names && repositoryData.repositoryData.external_volume_names.length > 0 && (
                <Alert
                  type="warning"
                  showIcon
                  icon={<WarningOutlined />}
                  message="External Docker Volumes Detected"
                  description={
                    <div>
                      <Text>The following volumes are stored outside the repository:</Text>
                      <ul style={{ marginTop: 8, marginBottom: 8 }}>
                        {repositoryData.repositoryData.external_volume_names.map((vol: string) => (
                          <li key={vol}><Text code>{vol}</Text></li>
                        ))}
                      </ul>
                      <Text type="secondary">
                        <strong>Warning:</strong> If this repository is cloned, these volumes will be orphaned.
                        Consider using bind mounts to <Text code>$REPO_PATH</Text> instead.
                      </Text>
                    </div>
                  }
                  style={{ marginBottom: 16 }}
                  data-testid={`repo-detail-volume-warning-alert-${repository.repositoryName}`}
                />
              )}

              <Divider style={{ margin: '24px 0' }} data-testid="repo-detail-storage-divider">
                <Space>
                  <InfoCircleOutlined style={{ fontSize: 16 }} />
                  {t('resources:repositories.storageInfo')}
                </Space>
              </Divider>

              {/* Storage Information */}
              <Row gutter={[16, 16]} style={componentStyles.marginBottom.lg}>
                <Col span={24}>
                  <Card size="small" data-testid={`repo-detail-storage-info-card-${repository.repositoryName}`}>
                    <Space direction="vertical" style={{ width: '100%' }} size="small">
                      <div style={DETAIL_PANEL_LAYOUT.inlineField}>
                        <Text type="secondary" style={DETAIL_PANEL_TEXT.label}>{t('resources:repositories.imageSize')}:</Text>
                        <Text style={DETAIL_PANEL_TEXT.value}>{repositoryData.repositoryData.size_human}</Text>
                      </div>
                      <div style={DETAIL_PANEL_LAYOUT.inlineField}>
                        <Text type="secondary" style={DETAIL_PANEL_TEXT.label}>{t('resources:repositories.lastModified')}:</Text>
                        <Text style={DETAIL_PANEL_TEXT.value}>{repositoryData.repositoryData.modified_human}</Text>
                      </div>
                    </Space>
                  </Card>
                </Col>
                
                {/* Disk Usage Card - only show if mounted */}
                {repositoryData.repositoryData.mounted && repositoryData.repositoryData.disk_space && (
                  <Col span={24}>
                    <Card size="small" data-testid={`repo-detail-disk-usage-card-${repository.repositoryName}`}>
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
                        data-testid={`repo-detail-disk-usage-progress-${repository.repositoryName}`}
                      />
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        {t('resources:repositories.available')}: {repositoryData.repositoryData.disk_space.available}
                      </Text>
                    </Card>
                  </Col>
                )}
              </Row>

              {/* File Paths Section */}
              <Divider style={{ margin: '24px 0' }} data-testid="repo-detail-file-paths-divider">
                <Space>
                  <FolderOutlined style={{ fontSize: 16 }} />
                  {t('resources:repositories.filePaths')}
                </Space>
              </Divider>

              <Card size="small" style={componentStyles.card} data-testid={`repo-detail-file-paths-card-${repository.repositoryName}`}>
                <Space direction="vertical" style={{ width: '100%' }} size="small">
                  <div style={DETAIL_PANEL_LAYOUT.inlineField}>
                    <Text type="secondary" style={DETAIL_PANEL_TEXT.label}>{t('resources:repositories.imagePath')}:</Text>
                    <Text
                      copyable={{ text: repositoryData.repositoryData.image_path }}
                      style={DETAIL_PANEL_TEXT.monospace}
                      data-testid={`repo-detail-image-path-${repository.repositoryName}`}
                    >
                      {abbreviatePath(repositoryData.repositoryData.image_path, 45)}
                    </Text>
                  </div>
                  {repositoryData.repositoryData.mount_path && (
                    <div style={DETAIL_PANEL_LAYOUT.inlineField}>
                      <Text type="secondary" style={DETAIL_PANEL_TEXT.label}>{t('resources:repositories.mountPath')}:</Text>
                      <Text
                        copyable={{ text: repositoryData.repositoryData.mount_path }}
                        style={DETAIL_PANEL_TEXT.monospace}
                        data-testid={`repo-detail-mount-path-${repository.repositoryName}`}
                      >
                        {abbreviatePath(repositoryData.repositoryData.mount_path, 45)}
                      </Text>
                    </div>
                  )}
                </Space>
              </Card>

              {/* Repository Activity Section */}
              {repositoryData.repositoryData.mounted && (
                <>
                  <Divider style={{ margin: '24px 0' }} data-testid="repo-detail-activity-divider">
                    <Space>
                      <FieldTimeOutlined style={{ fontSize: 16 }} />
                      {t('resources:repositories.activity')}
                    </Space>
                  </Divider>

                  <Row gutter={[16, 16]} style={componentStyles.marginBottom.lg}>
                    <Col span={24}>
                      <Card size="small" data-testid={`repo-detail-activity-card-${repository.repositoryName}`}>
                        <Space direction="vertical" style={{ width: '100%' }} size="small">
                          {repositoryData.repositoryData.docker_running && (
                            <div style={DETAIL_PANEL_LAYOUT.inlineField}>
                              <Text type="secondary" style={DETAIL_PANEL_TEXT.label}>{t('resources:repositories.containers')}:</Text>
                              <Text style={DETAIL_PANEL_TEXT.value}>{repositoryData.repositoryData.container_count}</Text>
                            </div>
                          )}
                          {repositoryData.repositoryData.has_services && (
                            <div style={DETAIL_PANEL_LAYOUT.inlineField}>
                              <Text type="secondary" style={DETAIL_PANEL_TEXT.label}>{t('resources:repositories.services')}:</Text>
                              <Text style={DETAIL_PANEL_TEXT.value}>{repositoryData.repositoryData.service_count}</Text>
                            </div>
                          )}
                        </Space>
                      </Card>
                    </Col>
                  </Row>
                </>
              )}

              {/* Services Section */}
              {repositoryData.services && repositoryData.services.length > 0 && (
                <>
                  <Divider style={{ margin: '24px 0' }} data-testid="repo-detail-services-divider">
                    <Space>
                      <CodeOutlined style={{ fontSize: 16 }} />
                      {t('resources:repositories.servicesSection')}
                    </Space>
                  </Divider>

                  <Space direction="vertical" style={{ width: '100%' }} size="middle" data-testid="repo-detail-services-list">
                    {repositoryData.services.map((service: ServiceData, index: number) => (
                      <Card 
                        key={`${service.name}-${index}`} 
                        size="small"
                        data-testid={`repo-detail-service-card-${repository.repositoryName}-${service.name}`}
                        style={{ 
                          borderLeft: `4px solid ${
                            service.active_state === 'active' ? '#52c41a' :
                            service.active_state === 'failed' ? '#ff4d4f' : '#d9d9d9'
                          }`
                        }}
                      >
                        <Row gutter={[16, 8]}>
                          <Col span={24}>
                            <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                              <Text strong data-testid={`repo-detail-service-name-${repository.repositoryName}-${service.name}`}>{service.name}</Text>
                              <Tag data-testid={`repo-detail-service-status-${repository.repositoryName}-${service.name}`} color={
                                service.active_state === 'active' ? 'success' : 
                                service.active_state === 'failed' ? 'error' : 'default'
                              }>
                                {service.active_state}
                              </Tag>
                            </Space>
                          </Col>
                          {(service.memory_human || service.main_pid || service.uptime_human) && (
                            <Col span={24}>
                              <Space wrap size="middle">
                                {service.memory_human && (
                                  <div>
                                    <Text type="secondary" style={{ fontSize: 11 }}>Memory</Text>
                                    <br />
                                    <Text style={{ fontSize: 12 }}>{service.memory_human}</Text>
                                  </div>
                                )}
                                {service.main_pid && (
                                  <div>
                                    <Text type="secondary" style={{ fontSize: 11 }}>PID</Text>
                                    <br />
                                    <Text style={{ fontSize: 12 }}>{service.main_pid}</Text>
                                  </div>
                                )}
                                {service.uptime_human && (
                                  <div>
                                    <Text type="secondary" style={{ fontSize: 11 }}>Uptime</Text>
                                    <br />
                                    <Text style={{ fontSize: 12 }}>{service.uptime_human}</Text>
                                  </div>
                                )}
                                {service.restarts !== undefined && (
                                  <div>
                                    <Text type="secondary" style={{ fontSize: 11 }}>Restarts</Text>
                                    <br />
                                    <Text style={{ fontSize: 12 }}>{service.restarts}</Text>
                                  </div>
                                )}
                              </Space>
                            </Col>
                          )}
                        </Row>
                      </Card>
                    ))}
                  </Space>
                </>
              )}

            </>
          )}
        </div>
      </div>
    </>
  )
}