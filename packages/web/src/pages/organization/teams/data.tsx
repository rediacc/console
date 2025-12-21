import { Badge, Button, Popconfirm, Space, Tooltip, type TableProps } from 'antd';
import type { Team } from '@/api/queries/teams';
import {
  createCountColumn,
  createTruncatedColumn,
  createVersionColumn,
} from '@/components/common/columns';
import { featureFlags } from '@/config/featureFlags';
import {
  CloudServerOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  DesktopOutlined,
  EditOutlined,
  HistoryOutlined,
  TeamOutlined,
  UserOutlined,
} from '@/utils/optimizedIcons';
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
  const teamNameColumn = createTruncatedColumn<Team>({
    title: tSystem('tables.teams.teamName'),
    dataIndex: 'teamName',
    key: 'teamName',
    width: 150,
    maxLength: 20,
    renderWrapper: (content) => (
      <Space>
        <TeamOutlined />
        <strong>{content}</strong>
      </Space>
    ),
  });

  const memberCountColumn = createCountColumn<Team>({
    title: tSystem('tables.teams.members'),
    dataIndex: 'memberCount',
    key: 'memberCount',
    width: 100,
    sorter: true,
    renderValue: (count: number) => (
      <Badge count={count} showZero>
        <UserOutlined />
      </Badge>
    ),
  });

  const machineCountColumn = createCountColumn<Team>({
    title: tSystem('tables.teams.machines'),
    dataIndex: 'machineCount',
    key: 'machineCount',
    width: 100,
    icon: <DesktopOutlined />,
    sorter: true,
  });

  const repositoryCountColumn = createCountColumn<Team>({
    title: tSystem('tables.teams.repositories'),
    dataIndex: 'repositoryCount',
    key: 'repositoryCount',
    width: 120,
    icon: <DatabaseOutlined />,
    sorter: true,
  });

  const storageCountColumn = createCountColumn<Team>({
    title: tSystem('tables.teams.storage'),
    dataIndex: 'storageCount',
    key: 'storageCount',
    width: 120,
    icon: <CloudServerOutlined />,
    sorter: true,
  });

  const columns: TableProps<Team>['columns'] = [
    teamNameColumn,
    // Combined Stats column for mobile (show only on xs, hide on sm)
    {
      title: tSystem('tables.teams.stats', { defaultValue: 'Stats' }),
      key: 'stats',
      width: 140,
      responsive: ['xs'],
      render: (_, record: Team) => (
        <div style={{ width: '100%' }}>
          <Space direction="vertical" size={4}>
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
            <Tooltip
              title={`${record.repositoryCount || 0} ${tSystem('tables.teams.repositories')}`}
            >
              <Space size="small">
                <DatabaseOutlined />
                <span>{record.repositoryCount || 0}</span>
              </Space>
            </Tooltip>
            <Tooltip
              title={`${record.storageCount || 0} ${tSystem('tables.teams.storage')}`}
            >
              <Space size="small">
                <CloudServerOutlined />
                <span>{record.storageCount || 0}</span>
              </Space>
            </Tooltip>
          </Space>
        </div>
      ),
    },
    // Separate columns for desktop (show on sm and above)
    { ...memberCountColumn, responsive: ['sm'] },
    { ...machineCountColumn, responsive: ['sm'] },
    { ...repositoryCountColumn, responsive: ['sm'] },
    { ...storageCountColumn, responsive: ['sm'] },
  ];

  if (featureFlags.isEnabled('vaultVersionColumns')) {
    columns.push(
      createVersionColumn<Team>({
        title: tSystem('tables.teams.vaultVersion'),
        dataIndex: 'vaultVersion',
        key: 'vaultVersion',
        width: 120,
        sorter: true,
        formatVersion: (version: number) =>
          tCommon('general.versionFormat', { defaultValue: 'v{{version}}', version }),
      })
    );
  }

  columns.push({
    title: tSystem('tables.teams.actions'),
    key: 'actions',
    width: 160,
    render: (_, record: Team) => (
      <Space size={4} wrap>
        <Tooltip title={tSystem('actions.edit')}>
          <Button
            type="text"
            icon={<EditOutlined />}
            onClick={() => onEdit(record)}
            data-testid={`system-team-edit-button-${record.teamName}`}
            aria-label={tSystem('actions.edit')}
          />
        </Tooltip>
        <Tooltip title={tSystem('actions.members')}>
          <Button
            type="text"
            icon={<UserOutlined />}
            onClick={() => onManageMembers(record)}
            data-testid={`system-team-members-button-${record.teamName}`}
            aria-label={tSystem('actions.members')}
          />
        </Tooltip>
        <Tooltip title={tSystem('actions.trace')}>
          <Button
            type="text"
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
              type="text"
              danger
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
