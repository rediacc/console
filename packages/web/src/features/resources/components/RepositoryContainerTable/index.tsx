import { Alert, Flex, type MenuProps, Space, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import React, { useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useGetTeamRepositories } from '@/api/api-hooks.generated';
import { ActionButtonGroup } from '@/components/common/ActionButtonGroup';
import {
  createStatusColumn,
  createTruncatedColumn,
  RESPONSIVE_HIDE_XS,
} from '@/components/common/columns';
import { createActionColumn } from '@/components/common/columns/factories/action';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import ResourceListView from '@/components/common/ResourceListView';
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
import { ContainerMobileCard } from './components/ContainerMobileCard';
import { useContainerActions } from './hooks/useContainerActions';
import { useContainerParser } from './hooks/useContainerParser';
import type { Container, RepositoryContainerTableProps } from './types';

export const RepositoryContainerTable: React.FC<RepositoryContainerTableProps> = ({
  machine,
  repository,
  onContainerClick,
  highlightedContainer,
  onQueueItemCreated,
  refreshKey,
}) => {
  const { t } = useTranslation(['resources', 'common', 'machines', 'functions']);
  const userEmail = useAppSelector((state) => state.auth.user?.email ?? '');
  const { executeDynamic, isExecuting } = useQueueAction();
  const { data: teamRepositories = [] } = useGetTeamRepositories(machine.teamName ?? undefined);

  // Parse containers from vaultStatus
  const { loading, error, containers, pluginContainers } = useContainerParser({
    vaultStatus: machine.vaultStatus ?? '',
    repository,
    refreshKey,
    t,
  });

  // Find repository data for credentials
  const repositoryData = teamRepositories.find(
    (r) =>
      (r.repositoryName === repository.name && r.repositoryTag === repository.repositoryTag) ||
      r.repositoryGuid === repository.originalGuid ||
      r.repositoryGuid === repository.name
  );

  // Get grand repository vault
  const grandRepoVault = repositoryData
    ? (getGrandVaultForOperation(
        repositoryData.repositoryGuid ?? '',
        repositoryData.grandGuid ?? '',
        teamRepositories
      ) ?? '{}')
    : '{}';

  // Container actions
  const { handleContainerAction } = useContainerActions({
    teamName: machine.teamName ?? '',
    machineName: machine.machineName ?? '',
    bridgeName: machine.bridgeName ?? '',
    repository,
    repositoryData: repositoryData as Parameters<typeof useContainerActions>[0]['repositoryData'],
    grandRepoVault,
    machineVault: machine.vaultContent ?? '{}',
    executeDynamic,
    onQueueItemCreated,
    t,
  });

  const getRowClassName = (container: Container) => {
    const classNames = ['repository-container-row'];
    if (highlightedContainer?.id === container.id) {
      classNames.push('repository-container-row--selected');
    }
    return classNames.join(' ');
  };

  // Column definitions
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
      exited: { icon: <DisconnectOutlined />, label: t('machines:connectionFailed') },
      restarting: {
        icon: <ReloadOutlined />,
        label: t('resources:containers.containerStatusRestarting'),
      },
    },
    defaultConfig: { icon: <DisconnectOutlined />, label: t('machines:connectionFailed') },
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
      exited: { icon: <StopOutlined />, label: t('resources:containers.containerStatusStopped') },
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

  const containerColumns: ColumnsType<Container> = useMemo(
    () => [
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
      {
        ...imageColumn,
        responsive: RESPONSIVE_HIDE_XS,
      },
      {
        title: t('resources:containers.ports'),
        dataIndex: 'port_mappings',
        key: 'ports',
        width: 150,
        responsive: RESPONSIVE_HIDE_XS,
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
                <Typography.Text>
                  {t('common:table.moreItems', { count: record.port_mappings.length - 2 })}
                </Typography.Text>
              )}
            </Space>
          );
        },
      },
      createActionColumn<Container>({
        title: t('common:table.actions'),
        fixed: 'right',
        renderActions: (container) => {
          const createActionLabel = (actionKey: string, label: React.ReactNode) => (
            <Typography.Text data-testid={`container-action-${actionKey.replaceAll('_', '-')}`}>
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
                label: createActionLabel(
                  'restart',
                  t('functions:functions.container_restart.name')
                ),
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
                      machine={machine.machineName ?? ''}
                      repository={repository.name}
                      teamName={machine.teamName ?? ''}
                      userEmail={userEmail}
                      containerId={row.id}
                      containerName={row.name}
                      containerState={row.state}
                      isContainerMenu
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
    ],
    [
      t,
      connectionStatusColumn,
      containerNameColumn,
      stateColumn,
      imageColumn,
      handleContainerAction,
      isExecuting,
      onContainerClick,
      machine,
      repository,
      userEmail,
    ]
  );

  const containerMobileRender = useCallback(
    (record: Container) => (
      <ContainerMobileCard
        record={record}
        onContainerClick={onContainerClick}
        onContainerAction={handleContainerAction}
        isExecuting={isExecuting}
        t={t}
      />
    ),
    [onContainerClick, handleContainerAction, isExecuting, t]
  );

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
        data-testid="container-list-error"
      />
    );
  }

  return (
    <Flex vertical data-testid="repository-container-list">
      <ResourceListView<Container>
        loading={false}
        data={containers}
        columns={containerColumns}
        rowKey="id"
        pagination={false}
        emptyDescription={t('resources:containers.noContainers')}
        mobileRender={containerMobileRender}
        onRow={(container) => ({ className: getRowClassName(container) })}
        data-testid="regular-containers-table"
      />

      {featureFlags.isEnabled('plugins') && pluginContainers.length > 0 && (
        <Flex vertical data-testid="plugin-containers-section">
          <Typography.Title level={5}>
            {t('resources:containers.pluginContainers')}
          </Typography.Title>
          <ResourceListView<Container>
            loading={false}
            data={pluginContainers}
            columns={containerColumns}
            rowKey="id"
            pagination={false}
            mobileRender={containerMobileRender}
            onRow={(container) => ({ className: getRowClassName(container) })}
            data-testid="plugin-containers-table"
          />
        </Flex>
      )}
    </Flex>
  );
};
