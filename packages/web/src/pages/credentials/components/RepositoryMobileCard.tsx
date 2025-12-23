import React from 'react';
import { Space, Tag, Typography, type MenuProps } from 'antd';
import type { Repository } from '@/api/queries/repositories';
import {
  buildDeleteMenuItem,
  buildDivider,
  buildEditMenuItem,
  buildTraceMenuItem,
} from '@/components/common/menuBuilders';
import { MobileCard } from '@/components/common/MobileCard';
import { ResourceActionsDropdown } from '@/components/common/ResourceActionsDropdown';
import { InboxOutlined } from '@/utils/optimizedIcons';
import type { TFunction } from 'i18next';

interface RepositoryMobileCardProps {
  record: Repository;
  t: TFunction<'resources' | 'machines' | 'common'>;
  onEdit: (repository: Repository) => void;
  onTrace: (repository: Repository) => void;
  onDelete: (repository: Repository) => void;
}

export const RepositoryMobileCard: React.FC<RepositoryMobileCardProps> = ({
  record,
  t,
  onEdit,
  onTrace,
  onDelete,
}) => {
  const menuItems: MenuProps['items'] = [
    buildEditMenuItem(t, () => onEdit(record)),
    buildTraceMenuItem(t, () => onTrace(record)),
    buildDivider(),
    buildDeleteMenuItem(t, () => onDelete(record)),
  ];

  return (
    <MobileCard actions={<ResourceActionsDropdown menuItems={menuItems} />}>
      <Space>
        <InboxOutlined />
        <Typography.Text strong className="truncate">
          {record.repositoryName}
        </Typography.Text>
      </Space>
      <Tag>{record.teamName}</Tag>
    </MobileCard>
  );
};
