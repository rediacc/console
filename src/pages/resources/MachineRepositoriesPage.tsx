import React, { useState, useEffect } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import { Card, Button, Space, Tag, Typography, Spin, Alert, Tooltip } from 'antd'
import { DoubleLeftOutlined, ReloadOutlined, DesktopOutlined } from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { useComponentStyles } from '@/hooks/useComponentStyles'
import { useMachines } from '@/api/queries/machines'
import { useRepositories } from '@/api/queries/repositories'
import { MachineRepositoryList } from '@/components/resources/MachineRepositoryList'
import { Machine, Repository } from '@/types'
import { UnifiedDetailPanel } from '@/components/resources/UnifiedDetailPanel'

const { Title } = Typography

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

const MachineRepositoriesPage: React.FC = () => {
  const { machineName } = useParams<{ machineName: string }>()
  const navigate = useNavigate()
  const location = useLocation()
  const { t } = useTranslation(['resources', 'machines', 'common'])
  const styles = useComponentStyles()

  // State for machine data - can come from route state or API
  const routeState = location.state as { machine?: Machine } | null
  const [machine, setMachine] = useState<Machine | null>(
    routeState?.machine || null
  )

  // State for selected resource (repository or container) and panel
  const [selectedResource, setSelectedResource] = useState<Repository | ContainerData | null>(null)
  const [isPanelCollapsed, setIsPanelCollapsed] = useState(true)
  const [splitWidth, setSplitWidth] = useState(400)

  // Refresh key for forcing MachineRepositoryList updates
  const [refreshKey, setRefreshKey] = useState(0)

  // Fetch all machines to find our specific machine if not passed via state
  const { data: machines = [], isLoading: machinesLoading, error: machinesError } = useMachines(
    machine?.teamName ? [machine.teamName] : undefined,
    true
  )

  // Fetch repositories (needed for MachineRepositoryList)
  const { data: repositories = [], refetch: refetchRepositories } = useRepositories(
    machine?.teamName ? [machine.teamName] : undefined
  )

  // Find the machine from API if not already set
  useEffect(() => {
    if (!machine && machines.length > 0 && machineName) {
      const foundMachine = machines.find(m => m.machineName === machineName)
      if (foundMachine) {
        // Use a microtask to avoid synchronous setState during render
        Promise.resolve().then(() => setMachine(foundMachine))
      }
    }
  }, [machines, machineName, machine])

  const handleBackToMachines = () => {
    navigate('/resources', { state: { activeTab: 'machines' } })
  }

  const handleRefresh = () => {
    setRefreshKey(prev => prev + 1)
    refetchRepositories()
  }

  const handleRepositoryClick = (repository: any) => {
    // Map repository data to Repository type
    const mappedRepository: Repository = {
      repositoryName: repository.name,
      repositoryGuid: repository.originalGuid || repository.name,
      teamName: machine!.teamName,
      vaultVersion: 0,
      vaultContent: undefined,
      grandGuid: undefined
    }

    // Find the actual repository from the API data
    const actualRepository = repositories.find(r =>
      r.repositoryName === repository.name ||
      r.repositoryGuid === repository.originalGuid ||
      r.repositoryGuid === repository.name
    )

    setSelectedResource(actualRepository || mappedRepository)
    setIsPanelCollapsed(false)
  }

  const handleContainerClick = (container: any) => {
    setSelectedResource(container)
    setIsPanelCollapsed(false)
  }

  const handlePanelClose = () => {
    setSelectedResource(null)
    setIsPanelCollapsed(true)
  }

  const handleTogglePanelCollapse = () => {
    setIsPanelCollapsed(!isPanelCollapsed)
  }

  // Calculate panel width (25% of window width, min 300px, max 600px)
  const calculatePanelWidth = () => {
    const windowWidth = window.innerWidth
    const panelWidth = Math.floor(windowWidth * 0.25)
    return Math.max(300, Math.min(600, panelWidth))
  }

  useEffect(() => {
    const handleResize = () => {
      setSplitWidth(calculatePanelWidth())
    }

    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  const COLLAPSED_PANEL_WIDTH = 50
  const actualPanelWidth = isPanelCollapsed ? COLLAPSED_PANEL_WIDTH : splitWidth

  // Loading state
  if (machinesLoading && !machine) {
    return (
      <div style={{ padding: 24 }}>
        <Card>
          <div style={{ textAlign: 'center', padding: '100px 0' }}>
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
  if (machinesError || (!machinesLoading && !machine)) {
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

  return (
    <div style={{ padding: 24, height: '100%' }}>
      <Card style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
        {/* Header */}
        <div style={{ marginBottom: 24, flexShrink: 0 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div style={{ flex: 1 }}>
              {/* Back button and title */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 12 }}>
                <Tooltip title={t('machines:backToMachines')}>
                  <Button
                    icon={<DoubleLeftOutlined />}
                    onClick={handleBackToMachines}
                    style={styles.touchTarget}
                    data-testid="machine-repositories-back-button"
                  />
                </Tooltip>
                <Title level={4} style={{ ...styles.heading4, margin: 0 }}>
                  <Space>
                    <DesktopOutlined />
                    <span>{t('machines:machine')}: {machine?.machineName}</span>
                  </Space>
                </Title>
              </div>

              {/* Machine info tags */}
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <Tag color="green">{t('machines:team')}: {machine?.teamName}</Tag>
                <Tag color="blue">{t('machines:bridge')}: {machine?.bridgeName}</Tag>
                {machine?.regionName && (
                  <Tag color="purple">{t('machines:region')}: {machine.regionName}</Tag>
                )}
              </div>
            </div>

            {/* Refresh button */}
            <Tooltip title={t('common:actions.refresh')}>
              <Button
                icon={<ReloadOutlined />}
                onClick={handleRefresh}
                style={styles.touchTarget}
                data-testid="machine-repositories-refresh-button"
              />
            </Tooltip>
          </div>
        </div>

        {/* Repository List */}
        <div
          style={{
            display: 'flex',
            flex: 1,
            overflow: 'hidden',
            position: 'relative'
          }}
        >
          {/* Left Panel - Repository List */}
          <div
            style={{
              width: selectedResource ? `calc(100% - ${actualPanelWidth}px)` : '100%',
              height: '100%',
              overflow: 'auto',
              minWidth: 300,
              transition: 'width 0.3s ease-in-out',
            }}
          >
            {machine && (
              <MachineRepositoryList
                machine={machine}
                key={`${machine.machineName}-${refreshKey}`}
                refreshKey={refreshKey}
                onActionComplete={handleRefresh}
                onRepositoryClick={handleRepositoryClick}
                onContainerClick={handleContainerClick}
              />
            )}
          </div>

          {/* Right Panel - Detail Panel */}
          {selectedResource && (
            <UnifiedDetailPanel
              type={'repositoryName' in selectedResource ? 'repository' : 'container'}
              data={selectedResource}
              visible={true}
              onClose={handlePanelClose}
              splitWidth={splitWidth}
              onSplitWidthChange={setSplitWidth}
              isCollapsed={isPanelCollapsed}
              onToggleCollapse={handleTogglePanelCollapse}
              collapsedWidth={COLLAPSED_PANEL_WIDTH}
            />
          )}
        </div>
      </Card>
    </div>
  )
}

export default MachineRepositoriesPage
