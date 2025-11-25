import React, { useState, useEffect, useMemo } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import { Button, Space, Tag, Typography, Alert, Tooltip } from 'antd'
import { DoubleLeftOutlined, ReloadOutlined, InboxOutlined } from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { usePanelWidth } from '@/hooks/usePanelWidth'
import { DETAIL_PANEL } from '@/constants/layout'
import { useMachines } from '@/api/queries/machines'
import { RepositoryContainerTable } from '@/pages/resources/components/RepositoryContainerTable'
import { Machine } from '@/types'
import { UnifiedDetailPanel } from '@/components/resources/UnifiedDetailPanel'
import QueueItemTraceModal from '@/components/common/QueueItemTraceModal'
import { useQueueTraceModal } from '@/hooks/useDialogState'
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
  SplitLayout,
  ListPanel,
  DetailBackdrop,
  CenteredState,
  ErrorWrapper,
  HeaderTitleText,
} from './styles'

const { Text } = Typography

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

  // Extract machine and repository from navigation state
  const machine = (location.state as any)?.machine as Machine | undefined
  const repository = (location.state as any)?.repository as Repository | undefined

  const [selectedContainer, setSelectedContainer] = useState<ContainerData | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const queueTrace = useQueueTraceModal()

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
  const panelWidth = usePanelWidth()
  const [splitWidth, setSplitWidth] = useState(panelWidth)
  const [isPanelCollapsed, setIsPanelCollapsed] = useState(true)

  // Update splitWidth when window resizes
  useEffect(() => {
    setSplitWidth(panelWidth)
  }, [panelWidth])

  const actualPanelWidth = isPanelCollapsed ? DETAIL_PANEL.COLLAPSED_WIDTH : splitWidth

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
  if (!actualMachine) {
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

  // Error state - repository not found
  if (!actualRepository) {
    return (
      <PageWrapper>
        <FullHeightCard>
          <Alert
            message={t('machines:repositoryNotFound')}
            description={
              <ErrorWrapper>
                <p>{t('machines:repositoryNotFoundDescription', { repositoryName, machineName })}</p>
                <Button type="primary" onClick={handleBackToRepositories}>
                  {t('machines:backToRepositories')}
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

  const actualRepositoryName = actualRepository.name

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
                title: <span>{actualMachine.machineName}</span>,
                onClick: () => navigate(`/machines/${machineName}/repositories`, { state: { machine: actualMachine } })
              },
              {
                title: <span>{t('resources:repositories.repositories')}</span>,
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

          <HeaderRow>
            <TitleColumn>
              <TitleRow>
                <Tooltip title={t('machines:backToRepositories')}>
                  <IconButton
                    icon={<DoubleLeftOutlined />}
                    onClick={handleBackToRepositories}
                    aria-label={t('machines:backToRepositories')}
                    data-testid="repository-containers-back-button"
                  />
                </Tooltip>
                <HeaderTitleText level={4}>
                  <Space>
                    <InboxOutlined />
                    <span>{t('machines:repositoryContainers')}: {actualRepositoryName}</span>
                  </Space>
                </HeaderTitleText>
              </TitleRow>
              <TagRow>
                <Tag color="purple">{t('machines:machine')}: {actualMachine.machineName}</Tag>
                <Tag color="green">{t('machines:team')}: {actualMachine.teamName}</Tag>
                <Tag color="blue">{t('machines:bridge')}: {actualMachine.bridgeName}</Tag>
                {actualMachine.regionName && (
                  <Tag color="cyan">{t('machines:region')}: {actualMachine.regionName}</Tag>
                )}
              </TagRow>
            </TitleColumn>

            <ActionsRow>
              <Tooltip title={t('common:actions.refresh')}>
                <IconButton
                  icon={<ReloadOutlined />}
                  onClick={handleRefresh}
                  data-testid="repository-containers-refresh-button"
                />
              </Tooltip>
            </ActionsRow>
          </HeaderRow>
        </HeaderSection>

        <SplitLayout>
          <ListPanel $showDetail={Boolean(selectedResource)} $detailWidth={actualPanelWidth}>
            <RepositoryContainerTable
              machine={actualMachine}
              repository={actualRepository}
              key={`${actualMachine.machineName}-${actualRepositoryName}-${refreshKey}`}
              refreshKey={refreshKey}
              onContainerClick={handleContainerClick}
              highlightedContainer={selectedContainer as any}
              onQueueItemCreated={(taskId, machineName) => {
                queueTrace.open(taskId, machineName)
              }}
            />
          </ListPanel>

          {/* Backdrop must come BEFORE panel for correct z-index layering */}
          {selectedResource && !isPanelCollapsed && (
            <DetailBackdrop
              $right={actualPanelWidth}
              $visible={true}
              onClick={() => {
                setSelectedContainer(null)
                setIsPanelCollapsed(true)
              }}
              data-testid="repository-containers-backdrop"
            />
          )}

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
              collapsedWidth={DETAIL_PANEL.COLLAPSED_WIDTH}
            />
          )}
        </SplitLayout>
      </FullHeightCard>

      {queueTrace.state.open && (
        <QueueItemTraceModal
          taskId={queueTrace.state.taskId}
          open={queueTrace.state.open}
          onCancel={() => {
            queueTrace.close()
            handleRefresh()
          }}
        />
      )}
    </PageWrapper>
  )
}

export default RepositoryContainersPage
