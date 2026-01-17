import { type MenuProps, Space, Tag, Typography } from 'antd';
import {
  buildDeleteMenuItem,
  buildDivider,
  buildEditMenuItem,
  buildTraceMenuItem,
} from '@/components/common/menuBuilders';
import { MobileCard } from '@/components/common/MobileCard';
import { ResourceActionsDropdown } from '@/components/common/ResourceActionsDropdown';
import { InboxOutlined } from '@/utils/optimizedIcons';
import type { GetTeamRepositories_ResultSet1 } from '@rediacc/shared/types';

// Generic translation function type that accepts any namespace configuration
type TranslateFn = (key: string, options?: Record<string, unknown>) => string;

interface RepositoryMobileCardProps {
  record: GetTeamRepositories_ResultSet1;
  t: TranslateFn;
  onEdit: (record: GetTeamRepositories_ResultSet1 & Record<string, unknown>) => void;
  onTrace: (params: { entityType: string; entityIdentifier: string; entityName: string }) => void;
  onDelete: (record: GetTeamRepositories_ResultSet1) => void;
}

export const RepositoryMobileCard: React.FC<RepositoryMobileCardProps> = ({
  record,
  t,
  onEdit,
  onTrace,
  onDelete,
}) => {
  const menuItems: MenuProps['items'] = [
    buildEditMenuItem(t, () =>
      onEdit(record as GetTeamRepositories_ResultSet1 & Record<string, unknown>)
    ),
    buildTraceMenuItem(t, () =>
      onTrace({
        entityType: 'Repository',
        entityIdentifier: record.repositoryName ?? '',
        entityName: record.repositoryName ?? '',
      })
    ),
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
