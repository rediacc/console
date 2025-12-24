import { Button, Popconfirm, Space, Tooltip, Typography } from 'antd';
import type { PermissionGroup } from '@/api/queries/permissions';
import {
  DeleteOutlined,
  HistoryOutlined,
  KeyOutlined,
  SafetyOutlined,
  UserOutlined,
} from '@/utils/optimizedIcons';
import type { ColumnsType } from 'antd/es/table';
import type { TFunction } from 'i18next';

interface BuildPermissionColumnsParams {
  t: TFunction<'organization'>;
  tSystem: TFunction<'system'>;
  tCommon: TFunction<'common'>;
  onManagePermissions: (group: PermissionGroup) => void;
  onAssignUser: (group: PermissionGroup) => void;
  onTrace: (group: PermissionGroup) => void;
  onDeleteGroup: (groupName: string) => void;
  isDeleting: boolean;
}

export const buildPermissionColumns = ({
  t,
  tSystem,
  tCommon,
  onManagePermissions,
  onAssignUser,
  onTrace,
  onDeleteGroup,
  isDeleting,
}: BuildPermissionColumnsParams): ColumnsType<PermissionGroup> => [
  {
    title: tSystem('tables.permissionGroups.groupName'),
    dataIndex: 'permissionGroupName',
    key: 'permissionGroupName',
    render: (text: string) => (
      <Space>
        <SafetyOutlined />
        <strong>{text}</strong>
      </Space>
    ),
  },
  {
    title: tSystem('tables.permissionGroups.users'),
    dataIndex: 'userCount',
    key: 'userCount',
    width: 120,
    render: (count: number) => (
      <Space>
        <UserOutlined />
        <Typography.Text>{count}</Typography.Text>
      </Space>
    ),
  },
  {
    title: tSystem('tables.permissionGroups.permissions'),
    dataIndex: 'permissionCount',
    key: 'permissionCount',
    width: 140,
    render: (count: number) => (
      <Space>
        <KeyOutlined />
        <Typography.Text>{count}</Typography.Text>
      </Space>
    ),
  },
  {
    title: tSystem('tables.permissionGroups.actions'),
    key: 'actions',
    width: 360,
    render: (_: unknown, record: PermissionGroup) => (
      <Space>
        <Tooltip title={tSystem('actions.permissions')}>
          <Button
            type="primary"
            size="small"
            icon={<KeyOutlined />}
            onClick={() => onManagePermissions(record)}
            data-testid={`system-permission-group-manage-button-${record.permissionGroupName}`}
            aria-label={tSystem('actions.permissions')}
          />
        </Tooltip>
        <Tooltip title={tSystem('actions.assignUser')}>
          <Button
            type="primary"
            size="small"
            icon={<UserOutlined />}
            onClick={() => onAssignUser(record)}
            data-testid={`system-permission-group-assign-user-button-${record.permissionGroupName}`}
            aria-label={tSystem('actions.assignUser')}
          />
        </Tooltip>
        <Tooltip title={tSystem('actions.trace')}>
          <Button
            type="primary"
            size="small"
            icon={<HistoryOutlined />}
            onClick={() => onTrace(record)}
            data-testid={`system-permission-group-trace-button-${record.permissionGroupName}`}
            aria-label={tSystem('actions.trace')}
          />
        </Tooltip>
        <Popconfirm
          title={t('access.modals.deleteGroupTitle')}
          description={t('access.modals.deleteGroupDescription', {
            group: record.permissionGroupName,
          })}
          onConfirm={() => onDeleteGroup(record.permissionGroupName)}
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
              data-testid={`system-permission-group-delete-button-${record.permissionGroupName}`}
              aria-label={tCommon('actions.delete')}
            />
          </Tooltip>
        </Popconfirm>
      </Space>
    ),
  },
];
