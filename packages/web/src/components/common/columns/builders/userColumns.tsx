import { Button, Popconfirm, Space, Tag, Tooltip } from 'antd';
import type { User } from '@/api/queries/users';
import {
  CheckCircleOutlined,
  CheckOutlined,
  HistoryOutlined,
  SafetyOutlined,
  StopOutlined,
  UserOutlined,
} from '@/utils/optimizedIcons';
import type { ColumnsType } from 'antd/es/table';
import type { TFunction } from 'i18next';

interface BuildUserColumnsParams {
  t: TFunction<'organization'>;
  tSystem: TFunction<'system'>;
  tCommon: TFunction<'common'>;
  onAssignPermissions: (user: User) => void;
  onTrace: (user: User) => void;
  onDeactivate: (userEmail: string) => void;
  onReactivate: (userEmail: string) => void;
  isDeactivating: boolean;
  isReactivating: boolean;
}

export const buildUserColumns = ({
  t,
  tSystem,
  tCommon,
  onAssignPermissions,
  onTrace,
  onDeactivate,
  onReactivate,
  isDeactivating,
  isReactivating,
}: BuildUserColumnsParams): ColumnsType<User> => [
  {
    title: tSystem('tables.users.email'),
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
    title: tSystem('tables.users.status'),
    dataIndex: 'activated',
    key: 'activated',
    width: 120,
    render: (activated: boolean) =>
      activated ? (
        <Tag icon={<CheckCircleOutlined />}>{t('users.status.active')}</Tag>
      ) : (
        <Tag icon={<StopOutlined />}>{t('users.status.inactive')}</Tag>
      ),
  },
  {
    title: tSystem('tables.users.permissionGroup'),
    dataIndex: 'permissionGroupName',
    key: 'permissionGroupName',
    render: (group: string) =>
      group ? (
        <Tag icon={<SafetyOutlined />}>{group}</Tag>
      ) : (
        <Tag>{t('users.permissionGroups.none')}</Tag>
      ),
  },
  {
    title: tSystem('tables.users.lastActive'),
    dataIndex: 'lastActive',
    key: 'lastActive',
    render: (date: string) =>
      date ? new Date(date).toLocaleDateString() : t('users.lastActive.never'),
  },
  {
    title: tSystem('tables.users.actions'),
    key: 'actions',
    width: 300,
    render: (_: unknown, record: User) => (
      <Space>
        <Tooltip title={tSystem('actions.permissions')}>
          <Button
            type="text"
            icon={<SafetyOutlined />}
            onClick={() => onAssignPermissions(record)}
            data-testid={`system-user-permissions-button-${record.userEmail}`}
            aria-label={tSystem('actions.permissions')}
          />
        </Tooltip>
        <Tooltip title={tSystem('actions.trace')}>
          <Button
            type="text"
            icon={<HistoryOutlined />}
            onClick={() => onTrace(record)}
            data-testid={`system-user-trace-button-${record.userEmail}`}
            aria-label={tSystem('actions.trace')}
          />
        </Tooltip>
        {record.activated && (
          <Popconfirm
            title={tSystem('users.deactivate.confirmTitle')}
            description={tSystem('users.deactivate.confirmDescription', {
              email: record.userEmail,
            })}
            onConfirm={() => onDeactivate(record.userEmail)}
            okText={tCommon('general.yes')}
            cancelText={tCommon('general.no')}
            okButtonProps={{ danger: true }}
          >
            <Tooltip title={tSystem('actions.deactivate')}>
              <Button
                type="text"
                danger
                icon={<StopOutlined />}
                loading={isDeactivating}
                data-testid={`system-user-deactivate-button-${record.userEmail}`}
                aria-label={tSystem('actions.deactivate')}
              />
            </Tooltip>
          </Popconfirm>
        )}
        {!record.activated && (
          <Popconfirm
            title={tSystem('users.activate.confirmTitle')}
            description={tSystem('users.activate.confirmDescription', {
              email: record.userEmail,
            })}
            onConfirm={() => onReactivate(record.userEmail)}
            okText={tCommon('general.yes')}
            cancelText={tCommon('general.no')}
          >
            <Tooltip title={tSystem('actions.activate')}>
              <Button
                type="text"
                icon={<CheckOutlined />}
                loading={isReactivating}
                data-testid={`system-user-activate-button-${record.userEmail}`}
                aria-label={tSystem('actions.activate')}
              />
            </Tooltip>
          </Popconfirm>
        )}
      </Space>
    ),
  },
];
