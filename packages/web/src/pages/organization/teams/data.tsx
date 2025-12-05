import { Space, Badge, Tag, Tooltip, Button, Popconfirm } from 'antd';
import type { TableProps } from 'antd';
import {
  TeamOutlined,
  UserOutlined,
  DesktopOutlined,
  DatabaseOutlined,
  CloudServerOutlined,
  EditOutlined,
  HistoryOutlined,
  DeleteOutlined,
} from '@/utils/optimizedIcons';
import { featureFlags } from '@/config/featureFlags';
import type { Team } from '@/api/queries/teams';
import type { TFunction } from 'i18next';

interface GetTeamColumnsParams {
  tSystem: TFunction<'system'>;
  tCommon: TFunction<'common'>;
  onEdit: (team: Team) => void;
  onManageMembers: (team: Team) => void;
  onTrace: (team: Team) => void;
  onDelete: (teamName: string) => void;
  isDeleting: boolean;
}

export const getTeamColumns = ({
  tSystem,
  tCommon,
  onEdit,
  onManageMembers,
  onTrace,
  onDelete,
  isDeleting,
}: GetTeamColumnsParams): TableProps<Team>['columns'] => {
  const columns: TableProps<Team>['columns'] = [
    {
      title: tSystem('tables.teams.teamName'),
      dataIndex: 'teamName',
      key: 'teamName',
      width: 150,
      render: (text: string) => (
        <Space>
          <TeamOutlined />
          <strong>{text}</strong>
        </Space>
      ),
    },
    // Combined Stats column for mobile (show only on xs, hide on sm)
    {
      title: tSystem('tables.teams.stats', { defaultValue: 'Stats' }),
      key: 'stats',
      width: 140,
      responsive: ['xs'],
      render: (_, record: Team) => (
        <Space orientation="vertical" size={4} style={{ width: '100%' }}>
          <Tooltip title={`${record.memberCount} ${tSystem('tables.teams.members')}`}>
            <Space size="small">
              <Badge count={record.memberCount} showZero size="small">
                <UserOutlined />
              </Badge>
            </Space>
          </Tooltip>
          <Tooltip title={`${record.machineCount} ${tSystem('tables.teams.machines')}`}>
            <Space size="small">
              <DesktopOutlined />
              <span>{record.machineCount}</span>
            </Space>
          </Tooltip>
          <Tooltip title={`${record.repoCount || 0} ${tSystem('tables.teams.repos')}`}>
            <Space size="small">
              <DatabaseOutlined />
              <span>{record.repoCount || 0}</span>
            </Space>
          </Tooltip>
          <Tooltip title={`${record.storageCount || 0} ${tSystem('tables.teams.storage')}`}>
            <Space size="small">
              <CloudServerOutlined />
              <span>{record.storageCount || 0}</span>
            </Space>
          </Tooltip>
        </Space>
      ),
    },
    // Separate columns for desktop (show on sm and above)
    {
      title: tSystem('tables.teams.members'),
      dataIndex: 'memberCount',
      key: 'memberCount',
      width: 100,
      responsive: ['sm'],
      render: (count: number) => (
        <Badge count={count} showZero>
          <UserOutlined />
        </Badge>
      ),
    },
    {
      title: tSystem('tables.teams.machines'),
      dataIndex: 'machineCount',
      key: 'machineCount',
      width: 100,
      responsive: ['sm'],
      render: (count: number) => (
        <Space>
          <DesktopOutlined />
          <span>{count}</span>
        </Space>
      ),
    },
    {
      title: tSystem('tables.teams.repos'),
      dataIndex: 'repoCount',
      key: 'repoCount',
      width: 120,
      responsive: ['sm'],
      render: (count: number) => (
        <Space>
          <DatabaseOutlined />
          <span>{count || 0}</span>
        </Space>
      ),
    },
    {
      title: tSystem('tables.teams.storage'),
      dataIndex: 'storageCount',
      key: 'storageCount',
      width: 120,
      responsive: ['sm'],
      render: (count: number) => (
        <Space>
          <CloudServerOutlined />
          <span>{count || 0}</span>
        </Space>
      ),
    },
  ];

  if (featureFlags.isEnabled('vaultVersionColumns')) {
    columns.push({
      title: tSystem('tables.teams.vaultVersion'),
      dataIndex: 'vaultVersion',
      key: 'vaultVersion',
      width: 120,
      render: (version: number) => (
        <Tag>{tCommon('general.versionFormat', { defaultValue: 'v{{version}}', version })}</Tag>
      ),
    });
  }

  columns.push({
    title: tSystem('tables.teams.actions'),
    key: 'actions',
    width: 160,
    render: (_, record: Team) => (
      <Space size={4} wrap>
        <Tooltip title={tSystem('actions.edit')}>
          <Button
            type="primary"
            size="small"
            icon={<EditOutlined />}
            onClick={() => onEdit(record)}
            data-testid={`system-team-edit-button-${record.teamName}`}
            aria-label={tSystem('actions.edit')}
          />
        </Tooltip>
        <Tooltip title={tSystem('actions.members')}>
          <Button
            type="primary"
            size="small"
            icon={<UserOutlined />}
            onClick={() => onManageMembers(record)}
            data-testid={`system-team-members-button-${record.teamName}`}
            aria-label={tSystem('actions.members')}
          />
        </Tooltip>
        <Tooltip title={tSystem('actions.trace')}>
          <Button
            type="primary"
            size="small"
            icon={<HistoryOutlined />}
            onClick={() => onTrace(record)}
            data-testid={`system-team-trace-button-${record.teamName}`}
            aria-label={tSystem('actions.trace')}
          />
        </Tooltip>
        <Popconfirm
          title={tSystem('teams.delete.confirmTitle', { defaultValue: 'Delete Team' })}
          description={tSystem('teams.delete.confirmDescription', {
            defaultValue: 'Are you sure you want to delete team "{{teamName}}"?',
            teamName: record.teamName,
          })}
          onConfirm={() => onDelete(record.teamName)}
          okText={tCommon('general.yes')}
          cancelText={tCommon('general.no')}
          okButtonProps={{ danger: true }}
        >
          <Tooltip title={tCommon('actions.delete')}>
            <Button
              type="primary"
              danger
              size="small"
              icon={<DeleteOutlined />}
              loading={isDeleting}
              data-testid={`system-team-delete-button-${record.teamName}`}
              aria-label={tCommon('actions.delete')}
            />
          </Tooltip>
        </Popconfirm>
      </Space>
    ),
  });

  return columns;
};
