import type { TypedTFunction } from '@rediacc/shared/i18n/types';
import type { GetOrganizationPermissionGroups_ResultSet1 } from '@rediacc/shared/types';
import { Button, Popconfirm, Space, Tooltip, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { ActionButtonGroup } from '@/components/common/ActionButtonGroup';
import {
  DeleteOutlined,
  HistoryOutlined,
  KeyOutlined,
  SafetyOutlined,
  UserOutlined,
} from '@/utils/optimizedIcons';
import { RESPONSIVE_HIDE_XS } from '..';
import { createActionColumn } from '../factories/action';

interface BuildPermissionColumnsParams {
  t: TypedTFunction;
  onManagePermissions: (group: GetOrganizationPermissionGroups_ResultSet1) => void;
  onAssignUser: (group: GetOrganizationPermissionGroups_ResultSet1) => void;
  onTrace: (group: GetOrganizationPermissionGroups_ResultSet1) => void;
  onDeleteGroup: (groupName: string) => void;
  isDeleting: boolean;
}

export const buildPermissionColumns = ({
  t,
  onManagePermissions,
  onAssignUser,
  onTrace,
  onDeleteGroup,
  isDeleting,
}: BuildPermissionColumnsParams): ColumnsType<GetOrganizationPermissionGroups_ResultSet1> => [
  {
    title: t('system:tables.permissionGroups.groupName'),
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
    title: t('system:tables.permissionGroups.users'),
    dataIndex: 'userCount',
    key: 'userCount',
    width: 120,
    responsive: RESPONSIVE_HIDE_XS,
    render: (count: number) => (
      <Space>
        <UserOutlined />
        <Typography.Text>{count}</Typography.Text>
      </Space>
    ),
  },
  {
    title: t('system:tables.permissionGroups.permissions'),
    dataIndex: 'permissionCount',
    key: 'permissionCount',
    width: 140,
    responsive: RESPONSIVE_HIDE_XS,
    render: (count: number) => (
      <Space>
        <KeyOutlined />
        <Typography.Text>{count}</Typography.Text>
      </Space>
    ),
  },
  createActionColumn<GetOrganizationPermissionGroups_ResultSet1>({
    title: t('system:tables.permissionGroups.actions'),
    width: 360,
    renderActions: (record) => (
      <ActionButtonGroup
        buttons={[
          {
            type: 'permissions',
            icon: <KeyOutlined />,
            tooltip: 'system:actions.permissions',
            onClick: () => onManagePermissions(record),
            variant: 'primary',
            testId: `system-permission-group-manage-button-${record.permissionGroupName}`,
          },
          {
            type: 'assign',
            icon: <UserOutlined />,
            tooltip: 'system:actions.assignUser',
            onClick: () => onAssignUser(record),
            variant: 'primary',
            testId: `system-permission-group-assign-user-button-${record.permissionGroupName}`,
          },
          {
            type: 'trace',
            icon: <HistoryOutlined />,
            tooltip: 'system:actions.trace',
            onClick: () => onTrace(record),
            variant: 'primary',
            testId: `system-permission-group-trace-button-${record.permissionGroupName}`,
          },
          {
            type: 'custom',
            render: (rec) => (
              <Popconfirm
                title={t('access.modals.deleteGroupTitle')}
                description={t('access.modals.deleteGroupDescription', {
                  group: rec.permissionGroupName,
                })}
                onConfirm={() => onDeleteGroup(rec.permissionGroupName ?? '')}
                okText={t('common:general.yes')}
                cancelText={t('common:general.no')}
                okButtonProps={{ danger: true }}
              >
                <Tooltip title={t('common:actions.delete')}>
                  <Button
                    type="primary"
                    shape="circle"
                    danger
                    icon={<DeleteOutlined />}
                    loading={isDeleting}
                    data-testid={`system-permission-group-delete-button-${rec.permissionGroupName}`}
                    aria-label={t('common:actions.delete')}
                  />
                </Tooltip>
              </Popconfirm>
            ),
          },
        ]}
        record={record}
        idField="permissionGroupName"
        testIdPrefix="system-permission-group"
        t={t}
      />
    ),
  }),
];
