import { Space, Badge, Tag, Tooltip, Button, Popconfirm } from 'antd'
import type { TableProps } from 'antd'
import {
  TeamOutlined,
  UserOutlined,
  DesktopOutlined,
  DatabaseOutlined,
  CloudServerOutlined,
  EditOutlined,
  HistoryOutlined,
  DeleteOutlined,
} from '@/utils/optimizedIcons'
import { featureFlags } from '@/config/featureFlags'
import type { Team } from '@/api/queries/teams'
import type { TFunction } from 'i18next'

interface GetTeamColumnsParams {
  tSystem: TFunction<'system'>
  tCommon: TFunction<'common'>
  onEdit: (team: Team) => void
  onManageMembers: (team: Team) => void
  onTrace: (team: Team) => void
  onDelete: (teamName: string) => void
  isDeleting: boolean
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
      render: (text: string) => (
        <Space>
          <TeamOutlined />
          <strong>{text}</strong>
        </Space>
      ),
    },
    {
      title: tSystem('tables.teams.members'),
      dataIndex: 'memberCount',
      key: 'memberCount',
      width: 100,
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
      render: (count: number) => (
        <Space>
          <DesktopOutlined />
          <span>{count}</span>
        </Space>
      ),
    },
    {
      title: tSystem('tables.teams.repositories'),
      dataIndex: 'repoCount',
      key: 'repoCount',
      width: 120,
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
      render: (count: number) => (
        <Space>
          <CloudServerOutlined />
          <span>{count || 0}</span>
        </Space>
      ),
    },
  ]

  if (featureFlags.isEnabled('vaultVersionColumns')) {
    columns.push({
      title: tSystem('tables.teams.vaultVersion'),
      dataIndex: 'vaultVersion',
      key: 'vaultVersion',
      width: 120,
      render: (version: number) => (
        <Tag>{tCommon('general.versionFormat', { defaultValue: 'v{{version}}', version })}</Tag>
      ),
    })
  }

  columns.push({
    title: tSystem('tables.teams.actions'),
    key: 'actions',
    width: 350,
    render: (_, record: Team) => (
      <Space>
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
  })

  return columns
}
