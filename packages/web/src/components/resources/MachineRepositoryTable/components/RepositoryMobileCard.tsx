import type { TypedTFunction } from '@rediacc/shared/i18n/types';
import { Flex, type MenuProps, Space, Tag, Typography } from 'antd';
import React, { useMemo } from 'react';
import { MobileCard } from '@/components/common/MobileCard';
import { ResourceActionsDropdown } from '@/components/common/ResourceActionsDropdown';
import { isFork as coreIsFork } from '@/platform';
import {
  CheckCircleOutlined,
  ContainerOutlined,
  DeleteOutlined,
  DisconnectOutlined,
  EyeOutlined,
  FunctionOutlined,
  InboxOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
} from '@/utils/optimizedIcons';
import type { Repository, RepositoryTableRow } from '../types';

interface RepositoryMobileCardProps {
  record: RepositoryTableRow;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  teamRepositories: any[];
  machineName: string;
  onNavigateToContainers: (record: RepositoryTableRow) => void;
  onRepositoryClick?: (record: RepositoryTableRow) => void;
  onQuickAction: (record: Repository, action: string, priority: number, label?: string) => void;
  onRunFunction: (record: Repository) => void;
  onConfirmForkDeletion: (record: Repository) => void;
  onConfirmRepositoryDeletion: (record: Repository) => void;
  t: TypedTFunction;
}

export const RepositoryMobileCard: React.FC<RepositoryMobileCardProps> = ({
  record,
  teamRepositories,
  machineName: _machineName,
  onNavigateToContainers,
  onRepositoryClick,
  onQuickAction,
  onRunFunction,
  onConfirmForkDeletion,
  onConfirmRepositoryDeletion,
  t,
}) => {
  const repositoryData = teamRepositories.find(
    (r) => r.repositoryName === record.name && r.repositoryTag === record.repositoryTag
  );
  const isRepoFork = repositoryData ? coreIsFork(repositoryData) : false;

  const menuItems: MenuProps['items'] = useMemo(
    () => [
      {
        key: 'viewContainers',
        label: t('resources:containers.containers'),
        icon: <ContainerOutlined />,
        onClick: () => onNavigateToContainers(record),
      },
      {
        key: 'viewDetails',
        label: t('resources:audit.details'),
        icon: <EyeOutlined />,
        onClick: () => onRepositoryClick?.(record),
      },
      { type: 'divider' as const },
      {
        key: 'repository_up',
        label: t('functions:functions.repository_up.name'),
        icon: <PlayCircleOutlined />,
        onClick: () => onQuickAction(record, 'repository_up', 4, 'mount'),
      },
      ...(record.mounted
        ? [
            {
              key: 'repository_down',
              label: t('functions:functions.repository_down.name'),
              icon: <PauseCircleOutlined />,
              onClick: () => onQuickAction(record, 'repository_down', 4),
            },
          ]
        : []),
      {
        key: 'function',
        label: t('machines:runFunction'),
        icon: <FunctionOutlined />,
        onClick: () => onRunFunction(record),
      },
      { type: 'divider' as const },
      {
        key: 'delete',
        label: t('common:actions.delete'),
        icon: <DeleteOutlined />,
        danger: true,
        onClick: () =>
          isRepoFork ? onConfirmForkDeletion(record) : onConfirmRepositoryDeletion(record),
      },
    ],
    [
      record,
      isRepoFork,
      t,
      onNavigateToContainers,
      onRepositoryClick,
      onQuickAction,
      onRunFunction,
      onConfirmForkDeletion,
      onConfirmRepositoryDeletion,
    ]
  );

  const actions = <ResourceActionsDropdown menuItems={menuItems} />;

  return (
    <MobileCard className={isRepoFork ? 'ml-4' : undefined} actions={actions}>
      <Space>
        <InboxOutlined />
        <Typography.Text strong className="truncate">
          {record.name}
        </Typography.Text>
        {record.repositoryTag && <Tag>{record.repositoryTag}</Tag>}
      </Space>
      <Flex wrap>
        {record.mounted ? (
          <Tag icon={<CheckCircleOutlined />} color="success">
            {t('resources:repositories.mounted')}
          </Tag>
        ) : (
          <Tag icon={<DisconnectOutlined />}>{t('resources:repositories.unmounted')}</Tag>
        )}
        {record.mounted && record.docker_running && (
          <Tag color="processing">{t('resources:repositories.dockerRunning')}</Tag>
        )}
        {isRepoFork && <Tag color="purple">{t('resources:repositories.fork')}</Tag>}
      </Flex>
    </MobileCard>
  );
};
