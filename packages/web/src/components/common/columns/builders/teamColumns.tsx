import { Badge, Button, Flex, Popconfirm, Space, Tooltip, Typography, type TableProps } from 'antd';
import { ActionButtonGroup } from '@/components/common/ActionButtonGroup';
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
import type { TypedTFunction } from '@rediacc/shared/i18n/types';
import type { GetOrganizationTeams_ResultSet1 } from '@rediacc/shared/types';
import { createActionColumn } from '../factories/action';
import {
  createCountColumn,
  createTruncatedColumn,
  createVersionColumn,
} from '../factories/advanced';

interface BuildTeamColumnsParams {
  t: TypedTFunction;
  onEdit: (team: GetOrganizationTeams_ResultSet1) => void;
  onManageMembers: (team: GetOrganizationTeams_ResultSet1) => void;
  onTrace: (team: GetOrganizationTeams_ResultSet1) => void;
  onDelete: (teamName: string) => void;
  isDeleting: boolean;
}

export const buildTeamColumns = ({
  t,
  onEdit,
  onManageMembers,
  onTrace,
  onDelete,
  isDeleting,
}: BuildTeamColumnsParams): TableProps<GetOrganizationTeams_ResultSet1>['columns'] => {
  const teamNameColumn = createTruncatedColumn<GetOrganizationTeams_ResultSet1>({
    title: t('system:tables.teams.teamName'),
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

  const memberCountColumn = createCountColumn<GetOrganizationTeams_ResultSet1>({
    title: t('system:tables.teams.members'),
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

  const machineCountColumn = createCountColumn<GetOrganizationTeams_ResultSet1>({
    title: t('system:tables.teams.machines'),
    dataIndex: 'machineCount',
    key: 'machineCount',
    width: 100,
    icon: <DesktopOutlined />,
    sorter: true,
  });

  const repositoryCountColumn = createCountColumn<GetOrganizationTeams_ResultSet1>({
    title: t('system:tables.teams.repositories'),
    dataIndex: 'repositoryCount',
    key: 'repositoryCount',
    width: 120,
    icon: <DatabaseOutlined />,
    sorter: true,
  });

  const storageCountColumn = createCountColumn<GetOrganizationTeams_ResultSet1>({
    title: t('system:tables.teams.storage'),
    dataIndex: 'storageCount',
    key: 'storageCount',
    width: 120,
    icon: <CloudServerOutlined />,
    sorter: true,
  });

  const columns: TableProps<GetOrganizationTeams_ResultSet1>['columns'] = [
    teamNameColumn,
    // Combined Stats column for mobile (show only on xs, hide on sm)
    {
      title: t('system:tables.teams.stats'),
      key: 'stats',
      width: 140,
      responsive: ['xs'],
      render: (_, record: GetOrganizationTeams_ResultSet1) => (
        <Flex className="w-full">
          <Space direction="vertical" size={4}>
            <Tooltip title={`${record.memberCount} ${t('system:tables.teams.members')}`}>
              <Space size="small">
                <Badge count={record.memberCount} showZero size="small">
                  <UserOutlined />
                </Badge>
              </Space>
            </Tooltip>
            <Tooltip title={`${record.machineCount} ${t('system:tables.teams.machines')}`}>
              <Space size="small">
                <DesktopOutlined />
                <Typography.Text>{record.machineCount}</Typography.Text>
              </Space>
            </Tooltip>
            <Tooltip
              title={`${record.repositoryCount ?? 0} ${t('system:tables.teams.repositories')}`}
            >
              <Space size="small">
                <DatabaseOutlined />
                <Typography.Text>{record.repositoryCount ?? 0}</Typography.Text>
              </Space>
            </Tooltip>
            <Tooltip title={`${record.storageCount ?? 0} ${t('system:tables.teams.storage')}`}>
              <Space size="small">
                <CloudServerOutlined />
                <Typography.Text>{record.storageCount ?? 0}</Typography.Text>
              </Space>
            </Tooltip>
          </Space>
        </Flex>
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
      createVersionColumn<GetOrganizationTeams_ResultSet1>({
        title: t('system:tables.teams.vaultVersion'),
        dataIndex: 'vaultVersion',
        key: 'vaultVersion',
        width: 120,
        sorter: true,
        formatVersion: (version: number) => t('common:general.versionFormat', { version }),
      })
    );
  }

  columns.push(
    createActionColumn<GetOrganizationTeams_ResultSet1>({
      title: t('system:tables.teams.actions'),
      width: 160,
      renderActions: (record) => (
        <ActionButtonGroup
          buttons={[
            {
              type: 'edit',
              icon: <EditOutlined />,
              tooltip: 'system:actions.edit',
              onClick: () => onEdit(record),
              testId: `system-team-edit-button-${record.teamName}`,
            },
            {
              type: 'members',
              icon: <UserOutlined />,
              tooltip: 'system:actions.members',
              onClick: () => onManageMembers(record),
              testId: `system-team-members-button-${record.teamName}`,
            },
            {
              type: 'trace',
              icon: <HistoryOutlined />,
              tooltip: 'system:actions.trace',
              onClick: () => onTrace(record),
              testId: `system-team-trace-button-${record.teamName}`,
            },
            {
              type: 'custom',
              render: (rec) => (
                <Popconfirm
                  title={t('system:teams.delete.confirmTitle')}
                  description={t('system:teams.delete.confirmDescription', {
                    teamName: rec.teamName ?? '',
                  })}
                  onConfirm={() => onDelete(rec.teamName ?? '')}
                  okText={t('common:general.yes')}
                  cancelText={t('common:general.no')}
                  okButtonProps={{ danger: true }}
                >
                  <Tooltip title={t('common:actions.delete')}>
                    <Button
                      type="default"
                      shape="circle"
                      danger
                      icon={<DeleteOutlined />}
                      loading={isDeleting}
                      data-testid={`system-team-delete-button-${rec.teamName}`}
                      aria-label={t('common:actions.delete')}
                    />
                  </Tooltip>
                </Popconfirm>
              ),
            },
          ]}
          record={record}
          idField="teamName"
          testIdPrefix="system-team"
          t={t}
        />
      ),
    })
  );

  return columns;
};
