import React, { useState, useEffect, useMemo } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import { Card, Button, Space, Tag, Typography, Spin, Alert, Tooltip, Breadcrumb } from 'antd'
import { DoubleLeftOutlined, ReloadOutlined, InboxOutlined } from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { useComponentStyles } from '@/hooks/useComponentStyles'
import { usePanelWidth } from '@/hooks/usePanelWidth'
import { useMachines } from '@/api/queries/machines'
import { RepositoryContainerList } from '@/components/resources/RepositoryContainerList'
import { Machine } from '@/types'
import { UnifiedDetailPanel } from '@/components/resources/UnifiedDetailPanel'
import QueueItemTraceModal from '@/components/common/QueueItemTraceModal'

const { Title } = Typography

// Repository interface from vaultStatus (runtime data)
interface Repository {
  name: string
  repoTag?: string
  size: number
  size_human: string
  modified: number
  modified_human: string
  mounted: boolean
  mount_path: string
  image_path: string
  accessible: boolean
  has_rediaccfile: boolean
  docker_available: boolean
  docker_running: boolean
  container_count: number
  plugin_count: number
  has_services: boolean
  service_count: number
  isUnmapped?: boolean
  originalGuid?: string
}

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

const RepositoryContainersPage: React.FC = () => {
  const { machineName, repositoryName } = useParams<{ machineName: string; repositoryName: string }>()
  const navigate = useNavigate()
  const location = useLocation()
  const { t } = useTranslation(['resources', 'machines', 'common'])
  const styles = useComponentStyles()

  // Extract machine and repository from navigation state
  const machine = (location.state as any)?.machine as Machine | undefined
  const repository = (location.state as any)?.repository as Repository | undefined

  const [selectedContainer, setSelectedContainer] = useState<ContainerData | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const [queueTraceModal, setQueueTraceModal] = useState<{
    visible: boolean
    taskId: string
    machineName: string
  }>({ visible: false, taskId: '', machineName: '' })

  // Fetch machine data if not provided via state
  const { data: machines, isLoading: machinesLoading, refetch: refetchMachines } = useMachines()
  const actualMachine = machine || machines?.find(m => m.machineName === machineName)

  // Reconstruct repository from vaultStatus if not provided via state
  const actualRepository = useMemo(() => {
    if (repository) return repository

    if (!actualMachine?.vaultStatus || !repositoryName) return null

    try {
      const vaultStatusData = JSON.parse(actualMachine.vaultStatus)
      if (vaultStatusData.status === 'completed' && vaultStatusData.result) {
        let cleanedResult = vaultStatusData.result.trim()
        const newlineIndex = cleanedResult.indexOf('\njq:')
        if (newlineIndex > 0) {
          cleanedResult = cleanedResult.substring(0, newlineIndex)
        }
        const result = JSON.parse(cleanedResult)

        if (result?.repositories && Array.isArray(result.repositories)) {
          // Find repository by name
          return result.repositories.find((r: any) => r.name === repositoryName)
        }
      }
    } catch (err) {
      console.error('Failed to parse repository from vaultStatus:', err)
    }

    return null
  }, [repository, actualMachine?.vaultStatus, repositoryName])

  // Panel width management
  const COLLAPSED_PANEL_WIDTH = 50
  const panelWidth = usePanelWidth()
  const [splitWidth, setSplitWidth] = useState(panelWidth)
  const [isPanelCollapsed, setIsPanelCollapsed] = useState(true)

  // Update splitWidth when window resizes
  useEffect(() => {
    setSplitWidth(panelWidth)
  }, [panelWidth])

  const actualPanelWidth = isPanelCollapsed ? COLLAPSED_PANEL_WIDTH : splitWidth

  // Determine selected resource for detail panel
  const selectedResource = selectedContainer
    ? { type: 'container' as const, data: selectedContainer }
    : null

  // Navigation handlers
  const handleBackToRepositories = () => {
    navigate(`/machines/${machineName}/repositories`, {
      state: { machine: actualMachine }
    })
  }

  const handleBackToMachines = () => {
    navigate('/machines')
  }

  const handleContainerClick = (container: any) => { // eslint-disable-line @typescript-eslint/no-explicit-any
    setSelectedContainer(container as ContainerData)
    setIsPanelCollapsed(false)
  }

  const handleRefresh = async () => {
    setRefreshKey(prev => prev + 1)
    // Refetch machines to get updated vaultStatus with container data
    await refetchMachines()
  }

  // Loading state
  if (machinesLoading) {
    return (
      <div style={{ padding: 24 }}>
        <Card>
          <div style={{ textAlign: 'center', padding: '40px 0' }}>
            <Spin size="large" />
            <div style={{ marginTop: 16, color: 'var(--ant-color-text-secondary)' }}>
              {t('common:general.loading')}
            </div>
          </div>
        </Card>
      </div>
    )
  }

  // Error state - machine not found
  if (!actualMachine) {
    return (
      <div style={{ padding: 24 }}>
        <Card>
          <Alert
            message={t('machines:machineNotFound')}
            description={
              <div>
                <p>{t('machines:machineNotFoundDescription', { machineName })}</p>
                <Button
                  type="primary"
                  onClick={handleBackToMachines}
                  style={{ marginTop: 16 }}
                >
                  {t('machines:backToMachines')}
                </Button>
              </div>
            }
            type="error"
            showIcon
          />
        </Card>
      </div>
    )
  }

  // Error state - repository not found
  if (!actualRepository) {
    return (
      <div style={{ padding: 24 }}>
        <Card>
          <Alert
            message={t('machines:repositoryNotFound')}
            description={
              <div>
                <p>{t('machines:repositoryNotFoundDescription', { repositoryName, machineName })}</p>
                <Button
                  type="primary"
                  onClick={handleBackToRepositories}
                  style={{ marginTop: 16 }}
                >
                  {t('machines:backToRepositories')}
                </Button>
              </div>
            }
            type="error"
            showIcon
          />
        </Card>
      </div>
    )
  }

  const actualRepositoryName = actualRepository.name

  return (
    <div style={{ padding: 24, height: '100%' }}>
      <Card style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
        {/* Header */}
        <div style={{ marginBottom: 24, flexShrink: 0 }}>
          {/* Breadcrumb Navigation */}
          <Breadcrumb
            style={{ marginBottom: 16 }}
            items={[
              {
                title: <span style={{ cursor: 'pointer' }}>{t('machines:machines')}</span>,
                onClick: () => navigate('/machines')
              },
              {
                title: <span style={{ cursor: 'pointer' }}>{actualMachine.machineName}</span>,
                onClick: () => navigate(`/machines/${machineName}/repositories`, { state: { machine: actualMachine } })
              },
              {
                title: <span style={{ cursor: 'pointer' }}>{t('resources:repositories.repositories')}</span>,
                onClick: () => navigate(`/machines/${machineName}/repositories`, { state: { machine: actualMachine } })
              },
              {
                title: actualRepositoryName
              },
              {
                title: t('resources:containers.containers')
              }
            ]}
            data-testid="repository-containers-breadcrumb"
          />

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div style={{ flex: 1 }}>
              {/* Back button and title */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 12 }}>
                <Tooltip title={t('machines:backToRepositories')}>
                  <Button
                    icon={<DoubleLeftOutlined />}
                    onClick={handleBackToRepositories}
                    style={styles.touchTarget}
                    data-testid="repository-containers-back-button"
                  />
                </Tooltip>
                <Title level={4} style={{ ...styles.heading4, margin: 0 }}>
                  <Space>
                    <InboxOutlined />
                    <span>{t('machines:repositoryContainers')}: {actualRepositoryName}</span>
                  </Space>
                </Title>
              </div>

              {/* Machine and Repository info tags */}
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <Tag color="purple">{t('machines:machine')}: {actualMachine.machineName}</Tag>
                <Tag color="green">{t('machines:team')}: {actualMachine.teamName}</Tag>
                <Tag color="blue">{t('machines:bridge')}: {actualMachine.bridgeName}</Tag>
                {actualMachine.regionName && (
                  <Tag color="cyan">{t('machines:region')}: {actualMachine.regionName}</Tag>
                )}
              </div>
            </div>

            {/* Refresh button */}
            <Tooltip title={t('common:actions.refresh')}>
              <Button
                icon={<ReloadOutlined />}
                onClick={handleRefresh}
                style={styles.touchTarget}
                data-testid="repository-containers-refresh-button"
              />
            </Tooltip>
          </div>
        </div>

        {/* Container List */}
        <div
          style={{
            display: 'flex',
            flex: 1,
            overflow: 'hidden',
            position: 'relative'
          }}
        >
          {/* Left Panel - Container List */}
          <div
            style={{
              width: selectedResource ? `calc(100% - ${actualPanelWidth}px)` : '100%',
              height: '100%',
              overflow: 'auto',
              minWidth: 300,
              transition: 'width 0.3s ease-in-out',
            }}
          >
            {actualMachine && actualRepository && (
              <RepositoryContainerList
                machine={actualMachine}
                repository={actualRepository}
                key={`${actualMachine.machineName}-${actualRepositoryName}-${refreshKey}`}
                refreshKey={refreshKey}
                onContainerClick={handleContainerClick}
                highlightedContainer={selectedContainer as any} // eslint-disable-line @typescript-eslint/no-explicit-any
                onQueueItemCreated={(taskId, machineName) => {
                  setQueueTraceModal({ visible: true, taskId, machineName })
                }}
              />
            )}
          </div>

          {/* Right Panel - Detail Panel */}
          {selectedResource && (
            <UnifiedDetailPanel
              type={selectedResource.type}
              data={selectedResource.data}
              visible={true}
              onClose={() => {
                setSelectedContainer(null)
                setIsPanelCollapsed(true)
              }}
              splitWidth={splitWidth}
              onSplitWidthChange={setSplitWidth}
              isCollapsed={isPanelCollapsed}
              onToggleCollapse={() => setIsPanelCollapsed(!isPanelCollapsed)}
              collapsedWidth={COLLAPSED_PANEL_WIDTH}
            />
          )}

          {/* Backdrop for detail panel */}
          {selectedResource && !isPanelCollapsed && (
            <div
              style={{
                position: 'fixed',
                top: 0,
                left: 0,
                right: 0,
                bottom: 0,
                backgroundColor: 'rgba(0, 0, 0, 0.2)',
                zIndex: 999,
                pointerEvents: 'auto'
              }}
              onClick={() => {
                setSelectedContainer(null)
                setIsPanelCollapsed(true)
              }}
            />
          )}
        </div>
      </Card>

      {/* Queue Item Trace Modal */}
      {queueTraceModal.visible && (
        <QueueItemTraceModal
          taskId={queueTraceModal.taskId}
          visible={queueTraceModal.visible}
          onClose={() => {
            setQueueTraceModal({ visible: false, taskId: '', machineName: '' })
            // Refresh the page after task completion
            handleRefresh()
          }}
        />
      )}
    </div>
  )
}

export default RepositoryContainersPage
