import { Button, Popconfirm, Space, Tag, Tooltip } from 'antd';
import { ActionButtonGroup } from '@/components/common/ActionButtonGroup';
import {
  CheckCircleOutlined,
  CheckOutlined,
  HistoryOutlined,
  SafetyOutlined,
  StopOutlined,
  UserOutlined,
} from '@/utils/optimizedIcons';
import type { TypedTFunction } from '@rediacc/shared/i18n/types';
import type { GetOrganizationUsers_ResultSet1 } from '@rediacc/shared/types';
import { RESPONSIVE_HIDE_XS } from '..';
import { createActionColumn } from '../factories/action';
import type { ColumnsType } from 'antd/es/table';

interface BuildUserColumnsParams {
  t: TypedTFunction;
  onAssignPermissions: (user: GetOrganizationUsers_ResultSet1) => void;
  onTrace: (user: GetOrganizationUsers_ResultSet1) => void;
  onDeactivate: (userEmail: string) => void;
  onReactivate: (userEmail: string) => void;
  isDeactivating: boolean;
  isReactivating: boolean;
}

export const buildUserColumns = ({
  t,
  onAssignPermissions,
  onTrace,
  onDeactivate,
  onReactivate,
  isDeactivating,
  isReactivating,
}: BuildUserColumnsParams): ColumnsType<GetOrganizationUsers_ResultSet1> => [
  {
    title: t('system:tables.users.email'),
    dataIndex: 'userEmail',
    key: 'userEmail',
    render: (email: string) => (
      <Space>
        <UserOutlined />
        <strong>{email}</strong>
      </Space>
    ),
  },
  {
    title: t('system:tables.users.status'),
    dataIndex: 'activated',
    key: 'activated',
    width: 120,
    responsive: RESPONSIVE_HIDE_XS,
    render: (activated: boolean) =>
      activated ? (
        <Tag icon={<CheckCircleOutlined />}>{t('users.status.active')}</Tag>
      ) : (
        <Tag icon={<StopOutlined />}>{t('users.status.inactive')}</Tag>
      ),
  },
  {
    title: t('system:tables.users.permissionGroup'),
    dataIndex: 'permissionsName',
    key: 'permissionsName',
    responsive: RESPONSIVE_HIDE_XS,
    render: (group: string) =>
      group ? (
        <Tag icon={<SafetyOutlined />}>{group}</Tag>
      ) : (
        <Tag>{t('users.permissionGroups.none')}</Tag>
      ),
  },
  {
    title: t('system:tables.users.lastActive'),
    dataIndex: 'lastActive',
    key: 'lastActive',
    responsive: RESPONSIVE_HIDE_XS,
    render: (date: string) =>
      date ? new Date(date).toLocaleString() : t('users.lastActive.never'),
  },
  createActionColumn<GetOrganizationUsers_ResultSet1>({
    title: t('system:tables.users.actions'),
    width: 300,
    renderActions: (record) => (
      <ActionButtonGroup
        buttons={[
          {
            type: 'permissions',
            icon: <SafetyOutlined />,
            tooltip: 'system:actions.permissions',
            onClick: () => onAssignPermissions(record),
            testId: `system-user-permissions-button-${record.userEmail}`,
          },
          {
            type: 'trace',
            icon: <HistoryOutlined />,
            tooltip: 'system:actions.trace',
            onClick: () => onTrace(record),
            testId: `system-user-trace-button-${record.userEmail}`,
          },
          {
            type: 'custom',
            visible: (rec) => rec.activated ?? false,
            render: (rec) => (
              <Popconfirm
                title={t('system:users.deactivate.confirmTitle')}
                description={t('system:users.deactivate.confirmDescription', {
                  email: rec.userEmail ?? '',
                })}
                onConfirm={() => onDeactivate(rec.userEmail ?? '')}
                okText={t('common:general.yes')}
                cancelText={t('common:general.no')}
                okButtonProps={{ danger: true }}
              >
                <Tooltip title={t('system:actions.deactivate')}>
                  <Button
                    type="default"
                    shape="circle"
                    danger
                    icon={<StopOutlined />}
                    loading={isDeactivating}
                    data-testid={`system-user-deactivate-button-${rec.userEmail}`}
                    aria-label={t('system:actions.deactivate')}
                  />
                </Tooltip>
              </Popconfirm>
            ),
          },
          {
            type: 'custom',
            visible: (rec) => !(rec.activated ?? false),
            render: (rec) => (
              <Popconfirm
                title={t('system:users.activate.confirmTitle')}
                description={t('system:users.activate.confirmDescription', {
                  email: rec.userEmail ?? '',
                })}
                onConfirm={() => onReactivate(rec.userEmail ?? '')}
                okText={t('common:general.yes')}
                cancelText={t('common:general.no')}
              >
                <Tooltip title={t('system:actions.activate')}>
                  <Button
                    type="default"
                    shape="circle"
                    icon={<CheckOutlined />}
                    loading={isReactivating}
                    data-testid={`system-user-activate-button-${rec.userEmail}`}
                    aria-label={t('system:actions.activate')}
                  />
                </Tooltip>
              </Popconfirm>
            ),
          },
        ]}
        record={record}
        idField="userEmail"
        testIdPrefix="system-user"
        t={t}
      />
    ),
  }),
];
