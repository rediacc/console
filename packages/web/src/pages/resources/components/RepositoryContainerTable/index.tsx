import React, { useEffect, useState } from 'react';
import { Alert, Flex, Space, Table, Typography, type MenuProps } from 'antd';
import { useTranslation } from 'react-i18next';
import { useRepositories } from '@/api/queries/repositories';
import { ActionButtonGroup } from '@/components/common/ActionButtonGroup';
import {
  createActionColumn,
  createStatusColumn,
  createTruncatedColumn,
} from '@/components/common/columns';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import { LocalActionsMenu } from '@/components/resources/internal/LocalActionsMenu';
import { featureFlags } from '@/config/featureFlags';
import { useQueueAction } from '@/hooks/useQueueAction';
import {
  createArrayLengthSorter,
  createCustomSorter,
  createSorter,
  getGrandVaultForOperation,
} from '@/platform';
import { useAppSelector } from '@/store/store';
import { Machine, PluginContainer } from '@/types';
import { showMessage } from '@/utils/messages';
import {
  CheckCircleOutlined,
  DeleteOutlined,
  DisconnectOutlined,
  EyeOutlined,
  FunctionOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  StopOutlined,
} from '@/utils/optimizedIcons';
import { parseVaultStatus } from '@rediacc/shared/services/machine';
import type { ColumnsType } from 'antd/es/table';

interface PortMapping {
  host: string;

  host_port: string;

  container_port: string;

  protocol: string;
}

interface Container {
  id: string;

  name: string;

  state: string;

  status?: string;

  image?: string;

  ports?: string;

  created?: string;

  repository?: string;

  port_mappings?: PortMapping[];

  cpu_percent?: string;

  memory_usage?: string;

  memory_percent?: string;

  net_io?: string;

  block_io?: string;

  pids?: string;

  [key: string]: unknown;
}

// Repository interface from vaultStatus (runtime data)

interface Repository {
  name: string;

  repositoryTag?: string;

  size: number;

  size_human: string;

  modified: number;

  modified_human: string;

  mounted: boolean;

  mount_path: string;

  image_path: string;

  accessible: boolean;

  has_rediaccfile: boolean;

  docker_available: boolean;

  docker_running: boolean;

  container_count: number;

  plugin_count: number;

  has_services: boolean;

  service_count: number;

  isUnmapped?: boolean;

  originalGuid?: string;
}

interface RepositoryContainerTableProps {
  machine: Machine;

  repository: Repository;

  onContainerClick?: (container: Container | PluginContainer) => void;

  highlightedContainer?: Container | PluginContainer | null;

  onQueueItemCreated?: (taskId: string, machineName: string) => void;

  refreshKey?: number;
}

interface VaultStatusRepo {
  name?: string;

  mount_path?: string;

  image_path?: string;
}

interface VaultStatusResult {
  repositories?: VaultStatusRepo[];

  containers?: {
    containers: Container[];
    total_count?: number;
    running_count?: number;
    stopped_count?: number;
    docker_version?: string;
  };
}

export const RepositoryContainerTable: React.FC<RepositoryContainerTableProps> = ({
  machine,

  repository,

  onContainerClick,

  highlightedContainer,

  onQueueItemCreated,

  refreshKey,
}) => {
  const { t } = useTranslation(['resources', 'common', 'machines', 'functions']);

  const userEmail = useAppSelector((state) => state.auth.user?.email || '');

  const [loading, setLoading] = useState(false);

  const [error, setError] = useState<string | null>(null);

  const [containers, setContainers] = useState<Container[]>([]);

  const [pluginContainers, setPluginContainers] = useState<Container[]>([]);

  const { executeAction, isExecuting } = useQueueAction();

  const { data: teamRepositories = [] } = useRepositories(machine.teamName);

  const getRowClassName = (container: Container) => {
    const classNames = ['repository-container-row'];

    if (onContainerClick) {
      classNames.push('repository-container-row--clickable');
    }

    if (highlightedContainer?.id === container.id) {
      classNames.push('repository-container-row--selected');
    }

    return classNames.join(' ');
  };

  const buildRowHandlers = (container: Container) => ({
    className: getRowClassName(container),

    onClick: (e: React.MouseEvent<HTMLElement>) => {
      if (!onContainerClick) {
        return;
      }

      const target = e.target as HTMLElement;

      if (target.closest('button') || target.closest('.ant-dropdown')) {
        return;
      }

      onContainerClick(container);
    },
  });

  // Find repository data for credentials - must match both name AND tag to distinguish forks

  const repositoryData = teamRepositories.find(
    (r) =>
      (r.repositoryName === repository.name && r.repositoryTag === repository.repositoryTag) ||
      r.repositoryGuid === repository.originalGuid ||
      r.repositoryGuid === repository.name
  );

  // Get grand repository vault (for credentials) using core orchestration

  const grandRepoVault = repositoryData
    ? getGrandVaultForOperation(
        repositoryData.repositoryGuid,

        repositoryData.grandGuid,

        teamRepositories
      ) || '{}'
    : '{}';

  // Parse containers from machine vaultStatus

  useEffect(() => {
    const parseContainers = () => {
      setLoading(true);

      setError(null);

      try {
        // Check if machine has vaultStatus data

        if (!machine.vaultStatus) {
          setContainers([]);

          setPluginContainers([]);

          setLoading(false);

          return;
        }

        // Parse vaultStatus using core utility

        const parsed = parseVaultStatus(machine.vaultStatus);

        if (parsed.error) {
          // Invalid vaultStatus data format (e.g., jq errors)

          setError('Invalid repository data');

          setLoading(false);

          return;
        }

        if (parsed.status === 'completed' && parsed.rawResult) {
          const result = JSON.parse(parsed.rawResult) as VaultStatusResult;

          if (
            result &&
            result.containers?.containers &&
            Array.isArray(result.containers.containers)
          ) {
            // Filter containers that belong to this repo

            // We need to match containers by finding the corresponding repository in vaultStatus

            // and comparing mount_path or image_path

            const repoContainers = result.containers.containers.filter((container: Container) => {
              // Get the repository GUID from container

              const containerRepoGuid = container.repository;

              if (!containerRepoGuid) {
                return false;
              }

              // Find the repository in vaultStatus with this GUID

              const vaultRepo = result.repositories?.find(
                (r: VaultStatusRepo) => r.name === containerRepoGuid
              );

              if (!vaultRepo) {
                return false;
              }

              // Match by mount_path or image_path

              return (
                repository.mount_path === vaultRepo.mount_path ||
                repository.image_path === vaultRepo.image_path
              );
            });

            // Separate plugin containers from regular containers

            const plugins = repoContainers.filter(
              (c: Container) => c.name && c.name.startsWith('plugin-')
            );

            const regular = repoContainers.filter(
              (c: Container) => !c.name || !c.name.startsWith('plugin-')
            );

            setPluginContainers(plugins);

            setContainers(regular);
          } else {
            setContainers([]);

            setPluginContainers([]);
          }
        } else {
          setContainers([]);

          setPluginContainers([]);
        }

        setLoading(false);
      } catch (err: unknown) {
        const errorMessage =
          err instanceof Error ? err.message : t('resources:repositories.errorLoadingContainers');

        setError(errorMessage);

        setLoading(false);
      }
    };

    parseContainers();
  }, [
    machine.vaultStatus,
    repository.image_path,
    repository.mount_path,
    repository.name,
    refreshKey,
    t,
  ]);

  // Handle container actions

  const handleContainerAction = async (container: Container, functionName: string) => {
    const result = await executeAction({
      teamName: machine.teamName,

      machineName: machine.machineName,

      bridgeName: machine.bridgeName,

      functionName,

      params: {
        repository: repositoryData?.repositoryGuid || repository.name,
        repositoryName: repositoryData?.repositoryName || repository.name,

        container: container.id,
      },

      priority: 4,

      addedVia: 'container-action',

      machineVault: machine.vaultContent || '{}',

      repositoryGuid: repositoryData?.repositoryGuid,

      vaultContent: grandRepoVault,

      repositoryNetworkId: repositoryData?.repositoryNetworkId,

      repositoryNetworkMode: repositoryData?.repositoryNetworkMode,

      repositoryTag: repositoryData?.repositoryTag,
    });

    if (result.success) {
      if (result.taskId) {
        showMessage('success', t('machines:queueItemCreated'));

        if (onQueueItemCreated) {
          onQueueItemCreated(result.taskId, machine.machineName);
        }
      } else if (result.isQueued) {
        showMessage('info', t('resources:repositories.highestPriorityQueued'));
      }
    } else {
      showMessage('error', result.error || t('common:errors.somethingWentWrong'));
    }
  };

  // Container columns

  const connectionStatusColumn = createStatusColumn<Container>({
    title: t('machines:status'),

    dataIndex: 'state',

    key: 'status',

    statusMap: {
      running: { icon: <CheckCircleOutlined />, label: t('machines:connected') },

      paused: {
        icon: <PauseCircleOutlined />,
        label: t('resources:containers.containerStatusPaused'),
      },

      exited: {
        icon: <DisconnectOutlined />,
        label: t('machines:connectionFailed'),
      },

      restarting: {
        icon: <ReloadOutlined />,
        label: t('resources:containers.containerStatusRestarting'),
      },
    },

    defaultConfig: {
      icon: <DisconnectOutlined />,
      label: t('machines:connectionFailed'),
    },
  });

  const stateColumn = createStatusColumn<Container>({
    title: t('resources:containers.state'),

    dataIndex: 'state',

    key: 'state',

    statusMap: {
      running: {
        icon: <PlayCircleOutlined />,
        label: t('resources:containers.containerStatusRunning'),
      },

      paused: {
        icon: <PauseCircleOutlined />,
        label: t('resources:containers.containerStatusPaused'),
      },

      restarting: {
        icon: <ReloadOutlined />,
        label: t('resources:containers.containerStatusRestarting'),
      },

      exited: {
        icon: <StopOutlined />,
        label: t('resources:containers.containerStatusStopped'),
      },
    },

    defaultConfig: {
      icon: <StopOutlined />,
      label: t('resources:containers.containerStatusStopped'),
    },
  });

  const containerNameColumn = createTruncatedColumn<Container>({
    title: t('resources:containers.containerName'),

    dataIndex: 'name',

    key: 'name',

    sorter: createSorter<Container>('name'),

    renderText: (name: string | null | undefined) => name ?? 'N/A',

    renderWrapper: (content) => <strong>{content}</strong>,
  });

  const imageColumn = createTruncatedColumn<Container>({
    title: t('resources:containers.image'),

    dataIndex: 'image',

    key: 'image',

    sorter: createSorter<Container>('image'),

    renderText: (image: string | null | undefined) => image ?? 'N/A',
  });

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

          {record.status && <Typography.Text>{record.status}</Typography.Text>}
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
          return <Typography.Text>-</Typography.Text>;
        }

        return (
          <Space direction="vertical" size={4}>
            {record.port_mappings.slice(0, 2).map((pm, idx) => (
              <Typography.Text key={idx}>
                {pm.host_port}:{pm.container_port}/{pm.protocol}
              </Typography.Text>
            ))}

            {record.port_mappings.length > 2 && (
              <Typography.Text>+{record.port_mappings.length - 2} more</Typography.Text>
            )}
          </Space>
        );
      },
    },

    createActionColumn<Container>({
      title: t('common:table.actions'),

      fixed: 'right',

      renderActions: (container) => {
        // Helper to create menu labels with consistent data-testid
        const createActionLabel = (actionKey: string, label: React.ReactNode) => (
          <Typography.Text data-testid={`container-action-${actionKey.replace(/_/g, '-')}`}>
            {label}
          </Typography.Text>
        );

        const menuItems: MenuProps['items'] = [];

        if (container.state === 'running') {
          menuItems.push(
            {
              key: 'stop',

              label: createActionLabel('stop', t('functions:functions.container_stop.name')),

              icon: <StopOutlined />,

              onClick: () => handleContainerAction(container, 'container_stop'),
            },

            {
              key: 'restart',

              label: createActionLabel('restart', t('functions:functions.container_restart.name')),

              icon: <ReloadOutlined />,

              onClick: () => handleContainerAction(container, 'container_restart'),
            },

            {
              key: 'pause',

              label: createActionLabel('pause', t('functions:functions.container_pause.name')),

              icon: <PauseCircleOutlined />,

              onClick: () => handleContainerAction(container, 'container_pause'),
            }
          );
        } else if (container.state === 'paused') {
          menuItems.push({
            key: 'unpause',

            label: createActionLabel('unpause', t('functions:functions.container_unpause.name')),

            icon: <PlayCircleOutlined />,

            onClick: () => handleContainerAction(container, 'container_unpause'),
          });
        } else {
          menuItems.push(
            {
              key: 'start',

              label: createActionLabel('start', t('functions:functions.container_start.name')),

              icon: <PlayCircleOutlined />,

              onClick: () => handleContainerAction(container, 'container_start'),
            },

            {
              key: 'remove',

              label: createActionLabel('remove', t('functions:functions.container_remove.name')),

              icon: <DeleteOutlined />,

              onClick: () => handleContainerAction(container, 'container_remove'),
            }
          );
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
                    repository={repository.name}
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
        );
      },
    }),
  ];

  if (loading) {
    return (
      <Flex vertical data-testid="container-list-loading">
        <LoadingWrapper
          loading
          centered
          minHeight={200}
          tip={t('resources:containers.fetchingContainers')}
        >
          <Flex />
        </LoadingWrapper>
      </Flex>
    );
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
    );
  }

  return (
    <Flex vertical data-testid="repository-container-list">
      {/* Regular Containers */}

      {containers.length > 0 ? (
        <Flex vertical data-testid="regular-containers-section">
          <Flex>
            <Table<Container>
              columns={containerColumns}
              dataSource={containers}
              rowKey="id"
              size="small"
              pagination={false}
              scroll={{ x: 'max-content' }}
              data-testid="regular-containers-table"
              onRow={(container) => buildRowHandlers(container)}
            />
          </Flex>
        </Flex>
      ) : (
        <Flex data-testid="no-containers" className="text-center" justify="center">
          <Typography.Text>{t('resources:containers.noContainers')}</Typography.Text>
        </Flex>
      )}

      {/* Plugin Containers */}

      {featureFlags.isEnabled('plugins') && pluginContainers.length > 0 && (
        <Flex vertical data-testid="plugin-containers-section">
          <Typography.Title level={5}>
            {t('resources:containers.pluginContainers')}
          </Typography.Title>

          <Flex>
            <Table<Container>
              columns={containerColumns}
              dataSource={pluginContainers}
              rowKey="id"
              size="small"
              pagination={false}
              scroll={{ x: 'max-content' }}
              data-testid="plugin-containers-table"
              onRow={(container) => buildRowHandlers(container)}
            />
          </Flex>
        </Flex>
      )}
    </Flex>
  );
};
