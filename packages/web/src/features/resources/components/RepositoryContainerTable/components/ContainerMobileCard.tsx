import React, { useMemo } from 'react';
import { Flex, Space, Tag, Typography, type MenuProps } from 'antd';
import { MobileCard } from '@/components/common/MobileCard';
import { ResourceActionsDropdown } from '@/components/common/ResourceActionsDropdown';
import { PluginContainer } from '@/types';
import {
  ContainerOutlined,
  DeleteOutlined,
  EyeOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  StopOutlined,
} from '@/utils/optimizedIcons';
import type { Container } from '../types';
import type { TFunction } from 'i18next';

interface ContainerMobileCardProps {
  record: Container;
  onContainerClick?: (container: Container | PluginContainer) => void;
  onContainerAction: (container: Container, action: string) => void;
  isExecuting: boolean;
  t: TFunction;
}

const getStateColor = (state: string) => {
  switch (state) {
    case 'running':
      return 'success';
    case 'paused':
      return 'warning';
    case 'restarting':
      return 'processing';
    default:
      return 'default';
  }
};

export const ContainerMobileCard: React.FC<ContainerMobileCardProps> = ({
  record,
  onContainerClick,
  onContainerAction,
  isExecuting,
  t,
}) => {
  const getStateLabel = (state: string) => {
    switch (state) {
      case 'running':
        return t('resources:containers.containerStatusRunning');
      case 'paused':
        return t('resources:containers.containerStatusPaused');
      case 'restarting':
        return t('resources:containers.containerStatusRestarting');
      default:
        return t('resources:containers.containerStatusStopped');
    }
  };

  const menuItems: MenuProps['items'] = useMemo(() => {
    const items: MenuProps['items'] = [];

    if (onContainerClick) {
      items.push({
        key: 'view',
        label: t('common:viewDetails'),
        icon: <EyeOutlined />,
        onClick: () => onContainerClick(record),
      });
    }

    if (record.state === 'running') {
      items.push(
        { type: 'divider' as const },
        {
          key: 'stop',
          label: t('functions:functions.container_stop.name'),
          icon: <StopOutlined />,
          onClick: () => onContainerAction(record, 'container_stop'),
        },
        {
          key: 'restart',
          label: t('functions:functions.container_restart.name'),
          icon: <ReloadOutlined />,
          onClick: () => onContainerAction(record, 'container_restart'),
        },
        {
          key: 'pause',
          label: t('functions:functions.container_pause.name'),
          icon: <PauseCircleOutlined />,
          onClick: () => onContainerAction(record, 'container_pause'),
        }
      );
    } else if (record.state === 'paused') {
      items.push(
        { type: 'divider' as const },
        {
          key: 'unpause',
          label: t('functions:functions.container_unpause.name'),
          icon: <PlayCircleOutlined />,
          onClick: () => onContainerAction(record, 'container_unpause'),
        }
      );
    } else {
      items.push(
        { type: 'divider' as const },
        {
          key: 'start',
          label: t('functions:functions.container_start.name'),
          icon: <PlayCircleOutlined />,
          onClick: () => onContainerAction(record, 'container_start'),
        },
        {
          key: 'remove',
          label: t('functions:functions.container_remove.name'),
          icon: <DeleteOutlined />,
          danger: true,
          onClick: () => onContainerAction(record, 'container_remove'),
        }
      );
    }

    return items;
  }, [record, onContainerClick, onContainerAction, t]);

  const handleCardClick = () => {
    if (onContainerClick) {
      onContainerClick(record);
    }
  };

  const actions = <ResourceActionsDropdown menuItems={menuItems} isLoading={isExecuting} />;

  return (
    <MobileCard onClick={onContainerClick ? handleCardClick : undefined} actions={actions}>
      <Space>
        <ContainerOutlined />
        <Typography.Text strong className="truncate">
          {record.name}
        </Typography.Text>
      </Space>
      <Flex gap={8} wrap>
        <Tag color={getStateColor(record.state)}>{getStateLabel(record.state)}</Tag>
        {record.status && (
          <Typography.Text type="secondary" className="text-xs">
            {record.status}
          </Typography.Text>
        )}
      </Flex>
      {record.image && (
        <Typography.Text type="secondary" className="text-xs truncate">
          {record.image}
        </Typography.Text>
      )}
      {record.port_mappings && record.port_mappings.length > 0 && (
        <Typography.Text type="secondary" className="text-xs">
          {record.port_mappings
            .slice(0, 2)
            .map((pm) => `${pm.host_port}:${pm.container_port}`)
            .join(', ')}
          {record.port_mappings.length > 2 && ` +${record.port_mappings.length - 2}`}
        </Typography.Text>
      )}
    </MobileCard>
  );
};
