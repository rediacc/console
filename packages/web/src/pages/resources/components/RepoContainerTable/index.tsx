import React, { useEffect, useState } from 'react'
import { Alert, Space, Typography } from 'antd'
import type { MenuProps } from 'antd'
import { useTableStyles } from '@/hooks/useComponentStyles'
import { FunctionOutlined, PlayCircleOutlined, StopOutlined, ReloadOutlined, DeleteOutlined, PauseCircleOutlined, CheckCircleOutlined, DisconnectOutlined, EyeOutlined } from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import * as S from './styles'
import { useQueueAction } from '@/hooks/useQueueAction'
import { Machine } from '@/types'
import { useRepos } from '@/api/queries/repos'
import type { ColumnsType } from 'antd/es/table'
import { LocalActionsMenu } from '@/components/resources/internal/LocalActionsMenu'
import { showMessage } from '@/utils/messages'
import { useAppSelector } from '@/store/store'
import { featureFlags } from '@/config/featureFlags'
import { createSorter, createCustomSorter, createArrayLengthSorter, getGrandVaultForOperation } from '@/core'
import { parseVaultStatus } from '@/core/services/machine'
import LoadingWrapper from '@/components/common/LoadingWrapper'
import { createActionColumn, createStatusColumn, createTruncatedColumn } from '@/components/common/columns'
import { ActionButtonGroup } from '@/components/common/ActionButtonGroup'
import { DESIGN_TOKENS } from '@/utils/styleConstants'

const { Text } = Typography

interface PortMapping {
  host: string
  host_port: string
  container_port: string
  protocol: string
}

interface Container {
  id: string
  name: string
  state: string
  status?: string
  image?: string
  ports?: string
  created?: string
  repo?: string
  port_mappings?: PortMapping[]
  cpu_percent?: string
  memory_usage?: string
  memory_percent?: string
  net_io?: string
  block_io?: string
  pids?: string
  [key: string]: unknown
}

// Repo interface from vaultStatus (runtime data)
interface Repo {
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

interface RepoContainerTableProps {
  machine: Machine
  repo: Repo
  onContainerClick?: (container: Container) => void
  highlightedContainer?: Container | null
  onQueueItemCreated?: (taskId: string, machineName: string) => void
  refreshKey?: number
}

interface VaultStatusRepo {
  name?: string
  mount_path?: string
  image_path?: string
}

interface VaultStatusResult {
  repos?: VaultStatusRepo[]
  containers?: Container[]
}

export const RepoContainerTable: React.FC<RepoContainerTableProps> = ({
  machine,
  repo,
  onContainerClick,
  highlightedContainer,
  onQueueItemCreated,
  refreshKey
}) => {
  const { t } = useTranslation(['resources', 'common', 'machines', 'functions'])
  const userEmail = useAppSelector((state) => state.auth.user?.email || '')
  const tableStyles = useTableStyles()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [containers, setContainers] = useState<Container[]>([])
  const [pluginContainers, setPluginContainers] = useState<Container[]>([])

  const { executeAction, isExecuting } = useQueueAction()
  const { data: teamRepos = [] } = useRepos(machine.teamName)

  // Find repo data for credentials - must match both name AND tag to distinguish forks
  const repoData = teamRepos.find(r =>
    (r.repoName === repo.name && r.repoTag === repo.repoTag) ||
    r.repoGuid === repo.originalGuid ||
    r.repoGuid === repo.name
  )

  // Get grand repo vault (for credentials) using core orchestration
  const grandRepoVault = repoData
    ? getGrandVaultForOperation(
        repoData.repoGuid,
        repoData.grandGuid,
        teamRepos
      ) || '{}'
    : '{}'

  // Parse containers from machine vaultStatus
  useEffect(() => {
    const parseContainers = () => {
      setLoading(true)
      setError(null)

      try {
        // Check if machine has vaultStatus data
        if (!machine.vaultStatus) {
          setContainers([])
          setPluginContainers([])
          setLoading(false)
          return
        }

        // Parse vaultStatus using core utility
        const parsed = parseVaultStatus(machine.vaultStatus)

        if (parsed.error) {
          // Invalid vaultStatus data format (e.g., jq errors)
          setError('Invalid repo data')
          setLoading(false)
          return
        }

        if (parsed.status === 'completed' && parsed.rawResult) {
          const result = JSON.parse(parsed.rawResult) as VaultStatusResult

          if (result && result.containers && Array.isArray(result.containers)) {
            // Filter containers that belong to this repo
            // We need to match containers by finding the corresponding repo in vaultStatus
            // and comparing mount_path or image_path
            const repoContainers = result.containers.filter((container: Container) => {
              // Get the repo GUID from container
              const containerRepoGuid = container.repo

              if (!containerRepoGuid) {
                return false
              }

              // Find the repo in vaultStatus with this GUID
              const vaultRepo = result.repositories?.find((r) => r.name === containerRepoGuid)
              if (!vaultRepo) {
                return false
              }

              // Match by mount_path or image_path
              return repo.mount_path === vaultRepo.mount_path ||
                     repo.image_path === vaultRepo.image_path
            })

            // Separate plugin containers from regular containers
            const plugins = repoContainers.filter((c: Container) =>
              c.name && c.name.startsWith('plugin-')
            )
            const regular = repoContainers.filter((c: Container) =>
              !c.name || !c.name.startsWith('plugin-')
            )

            setPluginContainers(plugins)
            setContainers(regular)
          } else {
            setContainers([])
            setPluginContainers([])
          }
        } else {
          setContainers([])
          setPluginContainers([])
        }

        setLoading(false)
      } catch (err: unknown) {
        const errorMessage = err instanceof Error ? err.message : t('resources:repos.errorLoadingContainers')
        setError(errorMessage)
        setLoading(false)
      }
    }

    parseContainers()
  }, [machine.vaultStatus, repo.image_path, repo.mount_path, repo.name, refreshKey, t])

  // Handle container actions
  const handleContainerAction = async (container: Container, functionName: string) => {
    const result = await executeAction({
      teamName: machine.teamName,
      machineName: machine.machineName,
      bridgeName: machine.bridgeName,
      functionName,
      params: {
        repo: repoData?.repoGuid || repo.name,
        container: container.id
      },
      priority: 4,
      addedVia: 'container-action',
      machineVault: machine.vaultContent || '{}',
      repoGuid: repoData?.repoGuid,
      repoVault: grandRepoVault,
      repoNetworkId: repoData?.repoNetworkId,
      repoNetworkMode: repoData?.repoNetworkMode,
      repoTag: repoData?.repoTag
    })

    if (result.success) {
      if (result.taskId) {
        showMessage('success', t('machines:queueItemCreated'))
        if (onQueueItemCreated) {
          onQueueItemCreated(result.taskId, machine.machineName)
        }
      } else if (result.isQueued) {
        showMessage('info', t('resources:repos.highestPriorityQueued'))
      }
    } else {
      showMessage('error', result.error || t('common:errors.somethingWentWrong'))
    }
  }

  // Container columns
  const connectionStatusColumn = createStatusColumn<Container>({
    title: t('machines:status'),
    dataIndex: 'state',
    key: 'status',
    statusMap: {
      running: { icon: <CheckCircleOutlined />, label: t('machines:connected'), color: 'success' },
      paused: { icon: <PauseCircleOutlined />, label: t('resources:containers.containerStatusPaused'), color: 'warning' },
      exited: { icon: <DisconnectOutlined />, label: t('machines:connectionFailed'), color: 'default' },
      restarting: { icon: <ReloadOutlined />, label: t('resources:containers.containerStatusRestarting'), color: 'blue' },
    },
    defaultConfig: { icon: <DisconnectOutlined />, label: t('machines:connectionFailed'), color: 'default' },
  })

  const stateColumn = createStatusColumn<Container>({
    title: t('resources:containers.state'),
    dataIndex: 'state',
    key: 'state',
    statusMap: {
      running: { icon: <PlayCircleOutlined />, label: t('resources:containers.containerStatusRunning'), color: 'success' },
      paused: { icon: <PauseCircleOutlined />, label: t('resources:containers.containerStatusPaused'), color: 'warning' },
      restarting: { icon: <ReloadOutlined />, label: t('resources:containers.containerStatusRestarting'), color: 'blue' },
      exited: { icon: <StopOutlined />, label: t('resources:containers.containerStatusStopped'), color: 'default' },
    },
    defaultConfig: { icon: <StopOutlined />, label: t('resources:containers.containerStatusStopped'), color: 'default' },
  })

  const containerNameColumn = createTruncatedColumn<Container>({
    title: t('resources:containers.containerName'),
    dataIndex: 'name',
    key: 'name',
    sorter: createSorter<Container>('name'),
    renderText: (name: string | null | undefined) => name ?? 'N/A',
    renderWrapper: (content) => <strong>{content}</strong>,
  })

  const imageColumn = createTruncatedColumn<Container>({
    title: t('resources:containers.image'),
    dataIndex: 'image',
    key: 'image',
    sorter: createSorter<Container>('image'),
    renderText: (image: string | null | undefined) => image ?? 'N/A',
  })

  const containerColumns: ColumnsType<Container> = [
    {
      ...connectionStatusColumn,
      align: 'center',
      sorter: createCustomSorter<Container>((c) => (c.state === 'running' ? 0 : 1)),
      render: (state: string, record: Container, index) =>
        connectionStatusColumn.render?.(state, record, index) as React.ReactNode,
    },
    containerNameColumn,
    {
      ...stateColumn,
      render: (state: string, record: Container, index) => (
        <Space>
          {stateColumn.render?.(state, record, index) as React.ReactNode}
          {record.status && <Text type="secondary" style={{ fontSize: 12 }}>{record.status}</Text>}
        </Space>
      ),
    },
    imageColumn,
    {
      title: t('resources:containers.ports'),
      dataIndex: 'port_mappings',
      key: 'ports',
      width: 150,
      sorter: createArrayLengthSorter<Container>('port_mappings'),
      render: (_: unknown, record: Container) => {
        if (!record.port_mappings || record.port_mappings.length === 0) {
          return <Text type="secondary">-</Text>
        }

        return (
          <Space direction="vertical" size={0}>
            {record.port_mappings.slice(0, 2).map((pm, idx) => (
              <Text key={idx} style={{ fontSize: 12 }}>
                {pm.host}:{pm.host_port} â†’ {pm.container_port}/{pm.protocol}
              </Text>
            ))}
            {record.port_mappings.length > 2 && (
              <Text type="secondary" style={{ fontSize: 11 }}>
                +{record.port_mappings.length - 2} more
              </Text>
            )}
          </Space>
        )
      },
    },
    createActionColumn<Container>({
      title: t('common:table.actions'),
      width: DESIGN_TOKENS.DIMENSIONS.CARD_WIDTH,
      fixed: 'right',
      renderActions: (container) => {
        const menuItems: MenuProps['items'] = []

        if (container.state === 'running') {
          menuItems.push(
            {
              key: 'stop',
              label: t('functions:functions.container_stop.name'),
              icon: <StopOutlined />,
              onClick: () => handleContainerAction(container, 'container_stop'),
            },
            {
              key: 'restart',
              label: t('functions:functions.container_restart.name'),
              icon: <ReloadOutlined />,
              onClick: () => handleContainerAction(container, 'container_restart'),
            },
            {
              key: 'pause',
              label: t('functions:functions.container_pause.name'),
              icon: <PauseCircleOutlined />,
              onClick: () => handleContainerAction(container, 'container_pause'),
            },
          )
        } else if (container.state === 'paused') {
          menuItems.push({
            key: 'unpause',
            label: t('functions:functions.container_unpause.name'),
            icon: <PlayCircleOutlined />,
            onClick: () => handleContainerAction(container, 'container_unpause'),
          })
        } else {
          menuItems.push(
            {
              key: 'start',
              label: t('functions:functions.container_start.name'),
              icon: <PlayCircleOutlined />,
              onClick: () => handleContainerAction(container, 'container_start'),
            },
            {
              key: 'remove',
              label: t('functions:functions.container_remove.name'),
              icon: <DeleteOutlined />,
              onClick: () => handleContainerAction(container, 'container_remove'),
            },
          )
        }

        return (
          <ActionButtonGroup
            buttons={[
              {
                type: 'view',
                icon: <EyeOutlined />,
                tooltip: 'common:viewDetails',
                variant: 'default',
                onClick: (row) => onContainerClick?.(row),
                testId: (row) => `container-view-details-${row.id}`,
              },
              {
                type: 'remote',
                icon: <FunctionOutlined />,
                tooltip: 'machines:remote',
                variant: 'primary',
                dropdownItems: menuItems,
                loading: isExecuting,
                testId: (row) => `container-actions-${row.id}`,
              },
              {
                type: 'custom',
                render: (row) => (
                  <LocalActionsMenu
                    machine={machine.machineName}
                    repo={repo.name}
                    teamName={machine.teamName}
                    userEmail={userEmail}
                    containerId={row.id}
                    containerName={row.name}
                    containerState={row.state}
                    isContainerMenu={true}
                  />
                ),
              },
            ]}
            record={container}
            idField="id"
            t={t}
          />
        )
      },
    }),
  ]

  if (loading) {
    return (
      <div data-testid="container-list-loading">
        <LoadingWrapper
          loading
          centered
          minHeight={200}
          tip={t('resources:containers.fetchingContainers') as string}
        >
          <div />
        </LoadingWrapper>
      </div>
    )
  }

  if (error) {
    return (
      <Alert
        message={t('resources:repos.errorLoadingContainers')}
        description={error}
        type="error"
        showIcon
        data-testid="container-list-error"
      />
    )
  }

  return (
    <div data-testid="repo-container-list">
      {/* Regular Containers */}
      {containers.length > 0 ? (
        <S.ContainersSection data-testid="regular-containers-section">
          <S.StyledTable
            columns={containerColumns}
            dataSource={containers}
            rowKey="id"
            size="small"
            $removeMargins={true}
            pagination={false}
            scroll={{ x: 'max-content' }}
            style={tableStyles.tableContainer}
            data-testid="regular-containers-table"
            onRow={(container: Container) => ({
              onClick: (e: React.MouseEvent<HTMLElement>) => {
                const target = e.target as HTMLElement
                // Don't trigger if clicking on buttons or dropdowns
                if (target.closest('button') || target.closest('.ant-dropdown')) {
                  return
                }
                onContainerClick?.(container)
              },
              style: {
                cursor: onContainerClick ? 'pointer' : 'default',
                backgroundColor: highlightedContainer?.id === container.id ? 'rgba(24, 144, 255, 0.05)' : undefined,
                transition: 'background-color 0.3s ease'
              },
              onMouseEnter: (e: React.MouseEvent<HTMLElement>) => {
                if (onContainerClick) {
                  e.currentTarget.style.backgroundColor = highlightedContainer?.id === container.id ? 'rgba(24, 144, 255, 0.05)' : 'rgba(0, 0, 0, 0.02)'
                }
              },
              onMouseLeave: (e: React.MouseEvent<HTMLElement>) => {
                e.currentTarget.style.backgroundColor = highlightedContainer?.id === container.id ? 'rgba(24, 144, 255, 0.05)' : ''
              }
            })}
          />
        </S.ContainersSection>
      ) : (
        <div style={{ padding: '40px', textAlign: 'center' }} data-testid="no-containers">
          <Text type="secondary">{t('resources:containers.noContainers')}</Text>
        </div>
      )}

      {/* Plugin Containers */}
      {featureFlags.isEnabled('plugins') && pluginContainers.length > 0 && (
        <S.ContainersSection data-testid="plugin-containers-section" style={{ marginTop: 24 }}>
          <Typography.Title level={5} style={{ marginBottom: 16 }}>
            {t('resources:containers.pluginContainers')}
          </Typography.Title>
          <S.StyledTable
            columns={containerColumns}
            dataSource={pluginContainers}
            rowKey="id"
            size="small"
            $removeMargins={true}
            pagination={false}
            scroll={{ x: 'max-content' }}
            style={tableStyles.tableContainer}
            data-testid="plugin-containers-table"
            onRow={(container: Container) => ({
              onClick: (e: React.MouseEvent<HTMLElement>) => {
                const target = e.target as HTMLElement
                // Don't trigger if clicking on buttons or dropdowns
                if (target.closest('button') || target.closest('.ant-dropdown')) {
                  return
                }
                onContainerClick?.(container)
              },
              style: {
                cursor: onContainerClick ? 'pointer' : 'default',
                backgroundColor: highlightedContainer?.id === container.id ? 'rgba(24, 144, 255, 0.05)' : undefined,
                transition: 'background-color 0.3s ease'
              }
            })}
          />
        </S.ContainersSection>
      )}
    </div>
  )
}


