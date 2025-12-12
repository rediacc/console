import React from 'react';
import { Space } from 'antd';
import { useTranslation } from 'react-i18next';
import { useTheme as useStyledTheme } from 'styled-components';
import { createStatusColumn, createTruncatedColumn } from '@/components/common/columns';
import { StatusIcon } from '@/components/common/styled';
import {
  isCredential as coreIsCredential,
  createArrayLengthSorter,
  createCustomSorter,
  createSorter,
} from '@/platform';
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloudServerOutlined,
  CopyOutlined,
  DisconnectOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  StarOutlined,
  StopOutlined,
} from '@/utils/optimizedIcons';
import type { GetTeamRepositories_ResultSet1 as TeamRepo } from '@rediacc/shared/types';
import { GrandTag, SmallText } from './styledComponents';
import { getRepositoryDisplayName } from './utils';
import type { Container, PortMapping, RepositoryTableRow } from './types';
import type { ColumnsType } from 'antd/es/table';

export const useRepositoryColumns = (teamRepositories: TeamRepo[]) => {
  const { t } = useTranslation(['resources', 'common']);
  const theme = useStyledTheme();

  const RepoStatusColumn = createStatusColumn<RepositoryTableRow>({
    title: t('resources:repositories.status'),
    dataIndex: 'status',
    key: 'status',
    width: 80,
    statusMap: {
      'mounted-running': {
        color: 'success',
        label: t('resources:repositories.statusMountedRunning'),
        icon: <CheckCircleOutlined />,
      },
      mounted: {
        color: 'warning',
        label: t('resources:repositories.statusMountedNotRunning'),
        icon: <ClockCircleOutlined />,
      },
      unmounted: {
        color: 'default',
        label: t('resources:repositories.statusUnmounted'),
        icon: <DisconnectOutlined />,
      },
    },
    defaultConfig: {
      color: 'default',
      label: t('resources:repositories.statusUnmounted'),
      icon: <DisconnectOutlined />,
    },
  });

  const repositoryNameColumn = {
    title: t('resources:repositories.repositoryName'),
    dataIndex: 'name',
    key: 'name',
    ellipsis: true,
    render: (_name: string, record: RepositoryTableRow) => {
      const RepoData = teamRepositories.find(
        (r) => r.repositoryName === record.name && r.repositoryTag === record.repositoryTag
      );
      const isGrand = RepoData && coreIsCredential(RepoData);

      return (
        <Space>
          <StatusIcon $color={isGrand ? theme.colors.iconGrand : theme.colors.iconFork} $size="LG">
            {isGrand ? <StarOutlined /> : <CopyOutlined />}
          </StatusIcon>
          <strong>{getRepositoryDisplayName(record)}</strong>
          {isGrand && <GrandTag>Grand</GrandTag>}
        </Space>
      );
    },
  };

  const repositoryStatusColumn = {
    ...RepoStatusColumn,
    align: 'center' as const,
    sorter: createCustomSorter<RepositoryTableRow>((r) => {
      if (r.mounted && r.docker_running) return 0;
      if (r.mounted) return 1;
      return 2;
    }),
    render: (_: unknown, record: RepositoryTableRow, index: number) => {
      const statusKey =
        record.mounted && record.docker_running
          ? 'mounted-running'
          : record.mounted
            ? 'mounted'
            : 'unmounted';
      return RepoStatusColumn.render?.(statusKey, record, index) as React.ReactNode;
    },
  };

  return { repositoryStatusColumn, repositoryNameColumn };
};

export const useSystemContainerColumns = () => {
  const { t } = useTranslation(['resources', 'common']);
  const theme = useStyledTheme();

  const systemStatusColumn = createStatusColumn<Container>({
    title: t('resources:containers.status'),
    dataIndex: 'state',
    key: 'status',
    width: 80,
    statusMap: {
      running: {
        color: 'success',
        label: t('resources:containers.containerStatusRunning'),
        icon: <PlayCircleOutlined />,
      },
      paused: {
        color: 'warning',
        label: t('resources:containers.containerStatusPaused'),
        icon: <PauseCircleOutlined />,
      },
      restarting: {
        color: 'blue',
        label: t('resources:containers.containerStatusRestarting'),
        icon: <ReloadOutlined />,
      },
      stopped: {
        color: 'default',
        label: t('resources:containers.containerStatusStopped'),
        icon: <StopOutlined />,
      },
    },
    defaultConfig: {
      color: 'default',
      label: t('resources:containers.containerStatusStopped'),
      icon: <StopOutlined />,
    },
  });

  const systemStateColumn = createStatusColumn<Container>({
    title: t('resources:repositories.containerStatus'),
    dataIndex: 'state',
    key: 'state',
    statusMap: {
      running: {
        color: 'success',
        label: t('resources:containers.containerStatusRunning'),
        icon: <PlayCircleOutlined />,
      },
      paused: {
        color: 'warning',
        label: t('resources:containers.containerStatusPaused'),
        icon: <PauseCircleOutlined />,
      },
      restarting: {
        color: 'blue',
        label: t('resources:containers.containerStatusRestarting'),
        icon: <ReloadOutlined />,
      },
      stopped: {
        color: 'default',
        label: t('resources:containers.containerStatusStopped'),
        icon: <StopOutlined />,
      },
    },
    defaultConfig: {
      color: 'default',
      label: t('resources:containers.containerStatusStopped'),
      icon: <StopOutlined />,
    },
  });

  const systemNameColumn = createTruncatedColumn<Container>({
    title: t('resources:repositories.containerName'),
    dataIndex: 'name',
    key: 'name',
    sorter: createSorter<Container>('name'),
  });

  const systemImageColumn = createTruncatedColumn<Container>({
    title: t('resources:repositories.containerImage'),
    dataIndex: 'image',
    key: 'image',
    width: 250,
    sorter: createSorter<Container>('image'),
  });

  const systemContainerColumns: ColumnsType<Container> = [
    {
      ...systemStatusColumn,
      align: 'center',
      sorter: createCustomSorter<Container>((c) =>
        c.state === 'running' ? 0 : c.state === 'paused' ? 1 : 2
      ),
      render: (state: string, record: Container, index) =>
        systemStatusColumn.render?.(
          state === 'exited' ? 'stopped' : state,
          record,
          index
        ) as React.ReactNode,
    },
    {
      ...systemNameColumn,
      render: (name: string, record: Container, index) => (
        <Space>
          <StatusIcon $color={theme.colors.iconSystem} $size="LG">
            <CloudServerOutlined />
          </StatusIcon>
          <strong>{systemNameColumn.render?.(name, record, index) as React.ReactNode}</strong>
        </Space>
      ),
    },
    systemImageColumn,
    {
      ...systemStateColumn,
      render: (state: string, record: Container, index) => (
        <Space>
          {
            systemStateColumn.render?.(
              state === 'exited' ? 'stopped' : state,
              record,
              index
            ) as React.ReactNode
          }
          {record.status && <SmallText color="secondary">{record.status}</SmallText>}
        </Space>
      ),
    },
    {
      title: t('resources:repositories.containerCPU'),
      dataIndex: 'cpu_percent',
      key: 'cpu_percent',
      sorter: createSorter<Container>('cpu_percent'),
      render: (cpu: string) => cpu || '-',
    },
    {
      title: t('resources:repositories.containerMemory'),
      dataIndex: 'memory_usage',
      key: 'memory_usage',
      sorter: createSorter<Container>('memory_usage'),
      render: (memory: string) => memory || '-',
    },
    {
      title: t('resources:repositories.containerPorts'),
      dataIndex: 'port_mappings',
      key: 'port_mappings',
      ellipsis: true,
      sorter: createArrayLengthSorter<Container>('port_mappings'),
      render: (portMappings: PortMapping[], record: Container) => {
        if (portMappings && Array.isArray(portMappings) && portMappings.length > 0) {
          return (
            <Space direction="vertical" size={4}>
              {portMappings.map((mapping, index) => (
                <SmallText key={index}>
                  {mapping.host_port ? (
                    <span>
                      {mapping.host}:{mapping.host_port} → {mapping.container_port}/
                      {mapping.protocol}
                    </span>
                  ) : (
                    <span>
                      {mapping.container_port}/{mapping.protocol}
                    </span>
                  )}
                </SmallText>
              ))}
            </Space>
          );
        } else if (record.ports) {
          return <SmallText>{record.ports}</SmallText>;
        }
        return '-';
      },
    },
  ];

  return { systemContainerColumns };
};
