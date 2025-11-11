import React, { useState, useEffect } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import { Button, Space, Tag, Typography, Spin, Alert, Tooltip } from 'antd'
import { DoubleLeftOutlined, ReloadOutlined, DesktopOutlined, PlusOutlined, CloudDownloadOutlined } from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { usePanelWidth } from '@/hooks/usePanelWidth'
import { useMachines } from '@/api/queries/machines'
import { useRepositories } from '@/api/queries/repositories'
import { MachineRepositoryList } from '@/components/resources/MachineRepositoryList'
import { Machine, Repository } from '@/types'
import { UnifiedDetailPanel } from '@/components/resources/UnifiedDetailPanel'
import QueueItemTraceModal from '@/components/common/QueueItemTraceModal'
import { RemoteFileBrowserModal } from '@/components/resources/RemoteFileBrowserModal'
import UnifiedResourceModal from '@/components/common/UnifiedResourceModal'
import { useRepositoryCreation } from '@/hooks/useRepositoryCreation'
import {
  PageWrapper,
  FullHeightCard,
  BreadcrumbWrapper,
  HeaderSection,
  HeaderRow,
  TitleColumn,
  TitleRow,
  TagRow,
  ActionsRow,
  IconButton,
  HeaderTitleText,
  SplitLayout,
  ListPanel,
  DetailBackdrop,
  CenteredState,
  ErrorWrapper,
} from './styles'

const { Title, Text } = Typography

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

  // State for machine data - can come from route state or API
  const routeState = location.state as { machine?: Machine } | null
  const [machine, setMachine] = useState<Machine | null>(
    routeState?.machine || null
  )

  // Use shared panel width hook (33% of window, min 300px, max 700px)
  const panelWidth = usePanelWidth()

  // State for selected resource (repository or container) and panel
  const [selectedResource, setSelectedResource] = useState<Repository | ContainerData | null>(null)
  const [isPanelCollapsed, setIsPanelCollapsed] = useState(true)
  const [splitWidth, setSplitWidth] = useState(panelWidth)
  const [backdropVisible, setBackdropVisible] = useState(false)
  const [shouldRenderBackdrop, setShouldRenderBackdrop] = useState(false)

  // Refresh key for forcing MachineRepositoryList updates
  const [refreshKey, setRefreshKey] = useState(0)

  // Queue trace modal state
  const [queueTraceModal, setQueueTraceModal] = useState<{
    visible: boolean
    taskId: string | null
    machineName: string | null
  }>({
    visible: false,
    taskId: null,
    machineName: null
  })

  // Remote file browser modal state
  const [remoteFileBrowserModal, setRemoteFileBrowserModal] = useState<{
    open: boolean
    machine: Machine | null
  }>({ open: false, machine: null })

  // Unified resource modal state
  const [unifiedModalState, setUnifiedModalState] = useState<{
    open: boolean
    mode: 'create' | 'edit' | 'vault'
    data?: any
    creationContext?: 'credentials-only' | 'normal'
  }>({
    open: false,
    mode: 'create'
  })

  // Fetch all machines to find our specific machine if not passed via state
  const { data: machines = [], isLoading: machinesLoading, error: machinesError, refetch: refetchMachines } = useMachines(
    machine?.teamName ? [machine.teamName] : undefined,
    true
  )

  // Repository creation hook (handles credentials + queue item)
  const { createRepository } = useRepositoryCreation(machines)

  // Fetch repositories (needed for MachineRepositoryList)
  const { data: repositories = [], refetch: refetchRepositories } = useRepositories(
    machine?.teamName ? [machine.teamName] : undefined
  )

  // Find the machine from API if not already set OR update it when machines data changes
  useEffect(() => {
    if (machines.length > 0 && machineName) {
      const foundMachine = machines.find(m => m.machineName === machineName)
      if (foundMachine) {
        // Update machine state with fresh data (including updated vaultStatus)
        setMachine(foundMachine)
      }
    }
  }, [machines, machineName])

  const handleBackToMachines = () => {
    navigate('/machines')
  }

  const handleRefresh = async () => {
    setRefreshKey(prev => prev + 1)
    // Refetch both repositories AND machines to get updated vaultStatus
    await Promise.all([
      refetchRepositories(),
      refetchMachines()
    ])
  }

  const handleCreateRepository = () => {
    if (!machine) return

    // Open the repository creation modal with prefilled machine
    setUnifiedModalState({
      open: true,
      mode: 'create',
      data: {
        machineName: machine.machineName,
        teamName: machine.teamName,
        prefilledMachine: true
      },
      creationContext: 'normal'
    })
  }

  const handlePull = () => {
    if (!machine) return

    setRemoteFileBrowserModal({
      open: true,
      machine: machine
    })
  }

  const handleUnifiedModalSubmit = async (data: any) => {
    const result = await createRepository(data)

    if (result.success) {
      setUnifiedModalState({ open: false, mode: 'create' })

      // If we have a taskId, open the queue trace modal
      if (result.taskId) {
        setQueueTraceModal({
          visible: true,
          taskId: result.taskId,
          machineName: result.machineName || null
        })
      } else {
        // No queue item (credentials-only mode), just refresh
        await handleRefresh()
      }
    }
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
    // Panel closes completely, no need to set collapsed state
  }

  const handleTogglePanelCollapse = () => {
    setIsPanelCollapsed(!isPanelCollapsed)
  }

  // Update splitWidth when window resizes (to keep within bounds)
  useEffect(() => {
    setSplitWidth(panelWidth)
  }, [panelWidth])

  // Manage backdrop fade in/out
  useEffect(() => {
    if (selectedResource) {
      // Mount backdrop and trigger fade-in
      setShouldRenderBackdrop(true)
      requestAnimationFrame(() => {
        setBackdropVisible(true)
      })
    } else {
      // Trigger fade-out
      setBackdropVisible(false)
      // Unmount backdrop after fade-out animation completes
      const timer = setTimeout(() => {
        setShouldRenderBackdrop(false)
      }, 250) // Match transition duration
      return () => clearTimeout(timer)
    }
  }, [selectedResource])

  const COLLAPSED_PANEL_WIDTH = 50
  const actualPanelWidth = isPanelCollapsed ? COLLAPSED_PANEL_WIDTH : splitWidth

  // Loading state
  if (machinesLoading && !machine) {
    return (
      <PageWrapper>
        <FullHeightCard>
          <CenteredState>
            <Spin size="large" />
            <Text type="secondary">{t('common:general.loading')}</Text>
          </CenteredState>
        </FullHeightCard>
      </PageWrapper>
    )
  }

  // Error state - machine not found
  if (machinesError || (!machinesLoading && !machine)) {
    return (
      <PageWrapper>
        <FullHeightCard>
          <Alert
            message={t('machines:machineNotFound')}
            description={
              <ErrorWrapper>
                <p>{t('machines:machineNotFoundDescription', { machineName })}</p>
                <Button type="primary" onClick={handleBackToMachines}>
                  {t('machines:backToMachines')}
                </Button>
              </ErrorWrapper>
            }
            type="error"
            showIcon
          />
        </FullHeightCard>
      </PageWrapper>
    )
  }

  return (
    <PageWrapper>
      <FullHeightCard>
        <HeaderSection>
          <BreadcrumbWrapper
            items={[
              {
                title: <span>{t('machines:machines')}</span>,
                onClick: () => navigate('/machines')
              },
              {
                title: machine?.machineName || machineName
              },
              {
                title: t('resources:repositories.repositories')
              }
            ]}
            data-testid="machine-repositories-breadcrumb"
          />

          <HeaderRow>
            <TitleColumn>
              <TitleRow>
                <Tooltip title={t('machines:backToMachines')}>
                  <IconButton
                    icon={<DoubleLeftOutlined />}
                    onClick={handleBackToMachines}
                    aria-label={t('machines:backToMachines')}
                    data-testid="machine-repositories-back-button"
                  />
                </Tooltip>
                <HeaderTitleText level={4}>
                  <Space>
                    <DesktopOutlined />
                    <span>{t('machines:machine')}: {machine?.machineName}</span>
                  </Space>
                </HeaderTitleText>
              </TitleRow>
              <TagRow>
                <Tag color="green">{t('machines:team')}: {machine?.teamName}</Tag>
                <Tag color="blue">{t('machines:bridge')}: {machine?.bridgeName}</Tag>
                {machine?.regionName && (
                  <Tag color="purple">{t('machines:region')}: {machine.regionName}</Tag>
                )}
              </TagRow>
            </TitleColumn>

            <ActionsRow>
              <Tooltip title={t('machines:createRepo')}>
                <IconButton
                  type="primary"
                  icon={<PlusOutlined />}
                  onClick={handleCreateRepository}
                  data-testid="machine-repositories-create-repo-button"
                />
              </Tooltip>
              <Tooltip title={t('functions:functions.pull.name')}>
                <IconButton
                  type="primary"
                  icon={<CloudDownloadOutlined />}
                  onClick={handlePull}
                  data-testid="machine-repositories-pull-button"
                />
              </Tooltip>
              <Tooltip title={t('common:actions.refresh')}>
                <IconButton
                  icon={<ReloadOutlined />}
                  onClick={handleRefresh}
                  data-testid="machine-repositories-refresh-button"
                />
              </Tooltip>
            </ActionsRow>
          </HeaderRow>
        </HeaderSection>

        <SplitLayout>
          <ListPanel $showDetail={Boolean(selectedResource)} $detailWidth={actualPanelWidth}>
            {machine && (
              <MachineRepositoryList
                machine={machine}
                key={`${machine.machineName}-${refreshKey}`}
                refreshKey={refreshKey}
                onActionComplete={handleRefresh}
                onRepositoryClick={handleRepositoryClick}
                onContainerClick={handleContainerClick}
                onQueueItemCreated={(taskId, machineName) => {
                  setQueueTraceModal({ visible: true, taskId, machineName })
                }}
              />
            )}
          </ListPanel>

          {shouldRenderBackdrop && (
            <DetailBackdrop
              $right={actualPanelWidth}
              $visible={backdropVisible}
              onClick={handlePanelClose}
              data-testid="machine-repositories-backdrop"
            />
          )}

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
        </SplitLayout>
      </FullHeightCard>

      <QueueItemTraceModal
        taskId={queueTraceModal.taskId}
        visible={queueTraceModal.visible}
        onClose={() => {
          setQueueTraceModal({ visible: false, taskId: null, machineName: null })
          handleRefresh()
        }}
      />

      {remoteFileBrowserModal.machine && (
        <RemoteFileBrowserModal
          open={remoteFileBrowserModal.open}
          onCancel={() => setRemoteFileBrowserModal({ open: false, machine: null })}
          machineName={remoteFileBrowserModal.machine.machineName}
          teamName={remoteFileBrowserModal.machine.teamName}
          bridgeName={remoteFileBrowserModal.machine.bridgeName}
          onQueueItemCreated={(taskId: string) => {
            setQueueTraceModal({
              visible: true,
              taskId,
              machineName: remoteFileBrowserModal.machine?.machineName || null
            })
            setRemoteFileBrowserModal({ open: false, machine: null })
          }}
        />
      )}

      <UnifiedResourceModal
        open={unifiedModalState.open}
        onCancel={() => setUnifiedModalState({ open: false, mode: 'create' })}
        resourceType="repository"
        mode={unifiedModalState.mode}
        existingData={unifiedModalState.data}
        teamFilter={machine?.teamName ? [machine.teamName] : undefined}
        creationContext={unifiedModalState.creationContext}
        onSubmit={handleUnifiedModalSubmit}
      />
    </PageWrapper>
  )
}

export default MachineRepositoriesPage
