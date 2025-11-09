import React, { useEffect, useState } from 'react'
import { Spin, Alert, Space, Typography, Button, Dropdown, Tooltip } from 'antd'
import { useTableStyles, useComponentStyles } from '@/hooks/useComponentStyles'
import { FunctionOutlined, PlayCircleOutlined, StopOutlined, ReloadOutlined, DeleteOutlined, PauseCircleOutlined, CheckCircleOutlined, DisconnectOutlined, EyeOutlined } from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import * as S from './styles'
import { useQueueVaultBuilder } from '@/hooks/useQueueVaultBuilder'
import { useManagedQueueItem } from '@/hooks/useManagedQueueItem'
import { Machine } from '@/types'
import { useTeams } from '@/api/queries/teams'
import type { ColumnsType } from 'antd/es/table'
import { LocalActionsMenu } from '../LocalActionsMenu'
import { showMessage } from '@/utils/messages'
import { useAppSelector } from '@/store/store'
import { featureFlags } from '@/config/featureFlags'

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
  repository?: string
  port_mappings?: PortMapping[]
  cpu_percent?: string
  memory_usage?: string
  memory_percent?: string
  net_io?: string
  block_io?: string
  pids?: string
  [key: string]: any // eslint-disable-line @typescript-eslint/no-explicit-any -- Allow additional properties from API
}

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

interface RepositoryContainerListProps {
  machine: Machine
  repository: Repository
  onContainerClick?: (container: Container) => void
  highlightedContainer?: Container | null
  onQueueItemCreated?: (taskId: string, machineName: string) => void
  refreshKey?: number
}

export const RepositoryContainerList: React.FC<RepositoryContainerListProps> = ({
  machine,
  repository,
  onContainerClick,
  highlightedContainer,
  onQueueItemCreated,
  refreshKey
}) => {
  const { t } = useTranslation(['resources', 'common', 'machines', 'functions'])
  const userEmail = useAppSelector((state) => state.auth.user?.email || '')
  const tableStyles = useTableStyles()
  const componentStyles = useComponentStyles()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [containers, setContainers] = useState<Container[]>([])
  const [pluginContainers, setPluginContainers] = useState<Container[]>([])

  const { data: teamsData } = useTeams()
  const { buildQueueVault } = useQueueVaultBuilder()
  const managedQueueMutation = useManagedQueueItem()

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

        // Check if vaultStatus is valid JSON
        if (machine.vaultStatus.trim().startsWith('jq:') ||
            machine.vaultStatus.trim().startsWith('error:') ||
            !machine.vaultStatus.trim().startsWith('{')) {
          setError('Invalid repository data')
          setLoading(false)
          return
        }

        // Parse vaultStatus
        const vaultStatusData = JSON.parse(machine.vaultStatus)

        if (vaultStatusData.status === 'completed' && vaultStatusData.result) {
          // Clean the result string
          let cleanedResult = vaultStatusData.result.trim()

          // Remove any jq errors at the end
          const newlineIndex = cleanedResult.indexOf('\njq:')
          if (newlineIndex > 0) {
            cleanedResult = cleanedResult.substring(0, newlineIndex)
          }

          const result = JSON.parse(cleanedResult)

          if (result && result.containers && Array.isArray(result.containers)) {
            // Filter containers that belong to this repository
            // We need to match containers by finding the corresponding repository in vaultStatus
            // and comparing mount_path or image_path
            const repositoryContainers = result.containers.filter((container: Container) => {
              // Get the repository GUID from container
              const containerRepoGuid = container.repository

              if (!containerRepoGuid) {
                return false
              }

              // Find the repository in vaultStatus with this GUID
              const vaultRepo = result.repositories?.find((r: any) => r.name === containerRepoGuid)
              if (!vaultRepo) {
                return false
              }

              // Match by mount_path or image_path
              return repository.mount_path === vaultRepo.mount_path ||
                     repository.image_path === vaultRepo.image_path
            })

            // Separate plugin containers from regular containers
            const plugins = repositoryContainers.filter((c: Container) =>
              c.name && c.name.startsWith('plugin-')
            )
            const regular = repositoryContainers.filter((c: Container) =>
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
      } catch (err: any) {
        setError(err.message || t('resources:repositories.errorLoadingContainers'))
        setLoading(false)
      }
    }

    parseContainers()
  }, [machine.vaultStatus, repository.name, refreshKey, t])

  // Handle container actions
  const handleContainerAction = async (container: Container, functionName: string) => {
    try {
      const team = teamsData?.find(t => t.teamName === machine.teamName)

      const queueVault = await buildQueueVault({
        teamName: machine.teamName,
        machineName: machine.machineName,
        bridgeName: machine.bridgeName,
        functionName,
        params: {
          repo: repository.name,
          container: container.id
        },
        priority: 4,
        description: `${functionName} for container ${container.name}`,
        addedVia: 'container-action',
        teamVault: team?.vaultContent || '{}',
        machineVault: machine.vaultContent || '{}'
      })

      const response = await managedQueueMutation.mutateAsync({
        teamName: machine.teamName,
        machineName: machine.machineName,
        bridgeName: machine.bridgeName,
        queueVault,
        priority: 4
      })

      if (response?.taskId) {
        showMessage('success', t('machines:queueItemCreated'))
        if (onQueueItemCreated) {
          onQueueItemCreated(response.taskId, machine.machineName)
        }
      } else if (response?.isQueued) {
        showMessage('info', t('resources:repositories.highestPriorityQueued'))
      }
    } catch (error: any) {
      showMessage('error', error.message || t('common:errors.somethingWentWrong'))
    }
  }

  // Container columns
  const containerColumns: ColumnsType<Container> = [
    {
      title: t('machines:status'),
      dataIndex: 'state',
      key: 'status',
      width: 80,
      align: 'center',
      sorter: (a: Container, b: Container) => {
        const getStatusValue = (container: Container) => container.state === 'running' ? 1 : 0
        return getStatusValue(b) - getStatusValue(a)
      },
      render: (_: any, record: Container) => {
        const isOnline = record.state === 'running'
        const tooltipText = isOnline ? t('machines:connected') : t('machines:connectionFailed')

        return (
          <Tooltip title={tooltipText}>
            <span style={{ fontSize: 18, color: isOnline ? '#52c41a' : '#d9d9d9' }}>
              {isOnline ? <CheckCircleOutlined /> : <DisconnectOutlined />}
            </span>
          </Tooltip>
        )
      },
    },
    {
      title: t('resources:containers.containerName'),
      dataIndex: 'name',
      key: 'name',
      ellipsis: true,
      render: (name: string) => <strong>{name || 'N/A'}</strong>,
    },
    {
      title: t('resources:containers.state'),
      dataIndex: 'state',
      key: 'state',
      width: 100,
      render: (state: string) => {
        let color = 'default'
        if (state === 'running') color = 'green'
        else if (state === 'paused') color = 'orange'
        else if (state === 'exited') color = 'gray'

        return <span style={{ color: `var(--ant-color-${color})`, fontWeight: 500 }}>{state}</span>
      },
    },
    {
      title: t('resources:containers.image'),
      dataIndex: 'image',
      key: 'image',
      ellipsis: true,
      render: (image: string) => image || 'N/A',
    },
    {
      title: t('resources:containers.ports'),
      dataIndex: 'port_mappings',
      key: 'ports',
      width: 150,
      render: (_: any, record: Container) => {
        if (!record.port_mappings || record.port_mappings.length === 0) {
          return <Text type="secondary">-</Text>
        }

        return (
          <Space direction="vertical" size={0}>
            {record.port_mappings.slice(0, 2).map((pm, idx) => (
              <Text key={idx} style={{ fontSize: 12 }}>
                {pm.host}:{pm.host_port} → {pm.container_port}/{pm.protocol}
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
    {
      title: t('common:table.actions'),
      key: 'actions',
      fixed: 'right',
      width: 120,
      render: (_: any, container: Container) => {
        const menuItems = []

        if (container.state === 'running') {
          menuItems.push({
            key: 'stop',
            label: t('functions:functions.container_stop.name'),
            icon: <StopOutlined style={componentStyles.icon.small} />,
            onClick: () => handleContainerAction(container, 'container_stop')
          })
          menuItems.push({
            key: 'restart',
            label: t('functions:functions.container_restart.name'),
            icon: <ReloadOutlined style={componentStyles.icon.small} />,
            onClick: () => handleContainerAction(container, 'container_restart')
          })
          menuItems.push({
            key: 'pause',
            label: t('functions:functions.container_pause.name'),
            icon: <PauseCircleOutlined style={componentStyles.icon.small} />,
            onClick: () => handleContainerAction(container, 'container_pause')
          })
        } else if (container.state === 'paused') {
          menuItems.push({
            key: 'unpause',
            label: t('functions:functions.container_unpause.name'),
            icon: <PlayCircleOutlined style={componentStyles.icon.small} />,
            onClick: () => handleContainerAction(container, 'container_unpause')
          })
        } else {
          menuItems.push({
            key: 'start',
            label: t('functions:functions.container_start.name'),
            icon: <PlayCircleOutlined style={componentStyles.icon.small} />,
            onClick: () => handleContainerAction(container, 'container_start')
          })
          menuItems.push({
            key: 'remove',
            label: t('functions:functions.container_remove.name'),
            icon: <DeleteOutlined style={componentStyles.icon.small} />,
            onClick: () => handleContainerAction(container, 'container_remove')
          })
        }

        return (
          <Space size="small">
            {/* Eye button - opens detail panel */}
            <Tooltip title={t('common:viewDetails')}>
              <Button
                type="default"
                size="small"
                icon={<EyeOutlined />}
                onClick={(e) => {
                  e.stopPropagation()
                  onContainerClick?.(container)
                }}
                data-testid={`container-view-details-${container.id}`}
                aria-label={t('common:viewDetails')}
              />
            </Tooltip>

            <Dropdown
              menu={{ items: menuItems }}
              trigger={['click']}
            >
              <Tooltip title={t('machines:remote')}>
                <Button
                  type="primary"
                  size="small"
                  icon={<FunctionOutlined />}
                  loading={managedQueueMutation.isPending}
                  data-testid={`container-actions-${container.id}`}
                  aria-label={t('machines:remote')}
                />
              </Tooltip>
            </Dropdown>
            <LocalActionsMenu
              machine={machine.machineName}
              repository={repository.name}
              teamName={machine.teamName}
              userEmail={userEmail}
              containerId={container.id}
              containerName={container.name}
              containerState={container.state}
              isContainerMenu={true}
            />
          </Space>
        )
      },
    },
  ]

  if (loading) {
    return (
      <div style={{ padding: '20px', textAlign: 'center' }} data-testid="container-list-loading">
        <Spin />
        <div style={{ marginTop: 16, color: 'var(--ant-color-text-secondary)' }}>
          {t('resources:containers.fetchingContainers')}
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <Alert
        message={t('resources:repositories.errorLoadingContainers')}
        description={error}
        type="error"
        showIcon
        data-testid="container-list-error"
      />
    )
  }

  return (
    <div data-testid="repository-container-list">
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
                if (target.closest('button') || target.closest('.ant-dropdown-trigger')) {
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
                if (target.closest('button') || target.closest('.ant-dropdown-trigger')) {
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
