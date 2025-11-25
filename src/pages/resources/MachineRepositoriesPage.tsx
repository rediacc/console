import React, { useState, useEffect } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import { Button, Space, Tag, Typography, Alert, Tooltip } from 'antd'
import { DoubleLeftOutlined, ReloadOutlined, DesktopOutlined, PlusOutlined, CloudDownloadOutlined } from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { usePanelWidth } from '@/hooks/usePanelWidth'
import { DETAIL_PANEL } from '@/constants/layout'
import { useMachines } from '@/api/queries/machines'
import { useRepositories } from '@/api/queries/repositories'
import { MachineRepositoryTable } from '@/components/resources/MachineRepositoryTable'
import { Machine, Repository } from '@/types'
import { UnifiedDetailPanel } from '@/components/resources/UnifiedDetailPanel'
import QueueItemTraceModal from '@/components/common/QueueItemTraceModal'
import { RemoteFileBrowserModal } from '@/pages/resources/components/RemoteFileBrowserModal'
import UnifiedResourceModal from '@/components/common/UnifiedResourceModal'
import { useRepositoryCreation } from '@/hooks/useRepositoryCreation'
import { useDialogState, useQueueTraceModal } from '@/hooks/useDialogState'
import { IconButton } from '@/styles/primitives'
import LoadingWrapper from '@/components/common/LoadingWrapper'
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
  HeaderTitleText,
  SplitLayout,
  ListPanel,
  DetailBackdrop,
  CenteredState,
  ErrorWrapper,
} from './styles'

const { Text } = Typography

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

  // Refresh key for forcing MachineRepositoryTable updates
  const [refreshKey, setRefreshKey] = useState(0)

  // Queue trace modal state
  const queueTrace = useQueueTraceModal()

  // Remote file browser modal state
  const fileBrowserModal = useDialogState<Machine>()

  // Unified resource modal state (kept as useState due to complex prefilled data needs)
  const [unifiedModalState, setUnifiedModalState] = useState<{
    open: boolean
    mode: 'create' | 'edit' | 'vault'
    data?: Record<string, unknown>
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

  // Fetch repositories (needed for MachineRepositoryTable)
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

    fileBrowserModal.open(machine)
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const handleUnifiedModalSubmit = async (data: any) => {
    const result = await createRepository(data)

    if (result.success) {
      setUnifiedModalState({ open: false, mode: 'create' })

      // If we have a taskId, open the queue trace modal
      if (result.taskId) {
        queueTrace.open(result.taskId, result.machineName || undefined)
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
      grandGuid: undefined,
      repoTag: repository.repoTag
    }

    // Find the actual repository from the API data - must match both name AND tag to distinguish forks
    const actualRepository = repositories.find(r =>
      r.repositoryName === repository.name &&
      r.repoTag === repository.repoTag
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

  const actualPanelWidth = isPanelCollapsed ? DETAIL_PANEL.COLLAPSED_WIDTH : splitWidth

  // Loading state
  if (machinesLoading && !machine) {
    return (
      <PageWrapper>
        <FullHeightCard>
          <CenteredState>
            <LoadingWrapper loading centered minHeight={160}>
              <div />
            </LoadingWrapper>
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
              <MachineRepositoryTable
                machine={machine}
                key={`${machine.machineName}-${refreshKey}`}
                refreshKey={refreshKey}
                onActionComplete={handleRefresh}
                onRepositoryClick={handleRepositoryClick}
                onContainerClick={handleContainerClick}
                onQueueItemCreated={(taskId, machineName) => {
                  queueTrace.open(taskId, machineName || undefined)
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
              collapsedWidth={DETAIL_PANEL.COLLAPSED_WIDTH}
            />
          )}
        </SplitLayout>
      </FullHeightCard>

      <QueueItemTraceModal
        taskId={queueTrace.state.taskId}
        open={queueTrace.state.open}
        onCancel={() => {
          queueTrace.close()
          handleRefresh()
        }}
      />

      {fileBrowserModal.state.data && (
        <RemoteFileBrowserModal
          open={fileBrowserModal.isOpen}
          onCancel={fileBrowserModal.close}
          machineName={fileBrowserModal.state.data.machineName}
          teamName={fileBrowserModal.state.data.teamName}
          bridgeName={fileBrowserModal.state.data.bridgeName}
          onQueueItemCreated={(taskId: string) => {
            queueTrace.open(taskId, fileBrowserModal.state.data?.machineName || undefined)
            fileBrowserModal.close()
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
