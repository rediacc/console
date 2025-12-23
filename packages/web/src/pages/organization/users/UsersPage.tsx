import React, { useMemo, useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import {
  Button,
  Dropdown,
  Flex,
  Form,
  Modal,
  Popconfirm,
  Select,
  Space,
  Tag,
  Tooltip,
  Typography,
  type MenuProps,
} from 'antd';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import {
  PermissionGroup,
  usePermissionGroups as usePermissionGroupsQuery,
} from '@/api/queries/permissions';
import {
  User,
  useAssignUserPermissions,
  useCreateUser,
  useDeactivateUser,
  useReactivateUser,
  useUsers,
} from '@/api/queries/users';
import AuditTraceModal from '@/components/common/AuditTraceModal';
import { MobileCard } from '@/components/common/MobileCard';
import ResourceListView from '@/components/common/ResourceListView';
import { useDialogState, useTraceModal } from '@/hooks/useDialogState';
import ResourceForm from '@/pages/organization/users/components/ResourceForm';
import {
  CheckCircleOutlined,
  CheckOutlined,
  HistoryOutlined,
  MoreOutlined,
  PlusOutlined,
  SafetyOutlined,
  StopOutlined,
  UserOutlined,
} from '@/utils/optimizedIcons';
import { CreateUserForm, createUserSchema } from '@/utils/validation';

const UsersPage: React.FC = () => {
  const { t } = useTranslation('organization');
  const { t: tSystem } = useTranslation('system');
  const { t: tCommon } = useTranslation('common');

  const createUserModal = useDialogState();
  const assignPermissionModal = useDialogState<User>();
  const [selectedUserGroup, setSelectedUserGroup] = useState('');
  const auditTrace = useTraceModal();

  const userForm = useForm<CreateUserForm>({
    resolver: zodResolver(createUserSchema),
    defaultValues: {
      newUserEmail: '',
      newUserPassword: '',
    },
  });

  const { data: users = [], isLoading: usersLoading } = useUsers();
  const createUserMutation = useCreateUser();
  const deactivateUserMutation = useDeactivateUser();
  const reactivateUserMutation = useReactivateUser();
  const assignUserPermissionsMutation = useAssignUserPermissions();
  const { data: permissionGroups = [] } = usePermissionGroupsQuery();

  const userFormFields: Array<{
    name: keyof CreateUserForm;
    label: string;
    type: 'text' | 'select' | 'password' | 'email' | 'number';
    placeholder: string;
    required: boolean;
  }> = [
    {
      name: 'newUserEmail',
      label: t('users.form.emailLabel'),
      type: 'email' as const,
      placeholder: 'user@example.com',
      required: true,
    },
    {
      name: 'newUserPassword',
      label: t('users.form.passwordLabel'),
      type: 'password' as const,
      placeholder: t('users.form.passwordPlaceholder'),
      required: true,
    },
  ];

  const handleCreateUser = async (data: CreateUserForm) => {
    try {
      await createUserMutation.mutateAsync({
        email: data.newUserEmail,
        password: data.newUserPassword,
      });
      createUserModal.close();
      userForm.reset();
    } catch {
      // handled by mutation
    }
  };

  const handleDeactivateUser = async (userEmail: string) => {
    try {
      await deactivateUserMutation.mutateAsync({ userEmail });
    } catch {
      // handled by mutation
    }
  };

  const handleReactivateUser = async (userEmail: string) => {
    try {
      await reactivateUserMutation.mutateAsync({ userEmail });
    } catch {
      // handled by mutation
    }
  };

  const handleAssignUserPermissions = async () => {
    if (!assignPermissionModal.state.data || !selectedUserGroup) return;

    try {
      await assignUserPermissionsMutation.mutateAsync({
        userEmail: assignPermissionModal.state.data.userEmail,
        permissionGroupName: selectedUserGroup,
      });
      assignPermissionModal.close();
      setSelectedUserGroup('');
    } catch {
      // handled by mutation
    }
  };

  const userColumns = [
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
              onClick={() => {
                assignPermissionModal.open(record);
                setSelectedUserGroup(record.permissionsName || '');
              }}
              data-testid={`system-user-permissions-button-${record.userEmail}`}
              aria-label={tSystem('actions.permissions')}
            />
          </Tooltip>
          <Tooltip title={tSystem('actions.trace')}>
            <Button
              type="text"
              icon={<HistoryOutlined />}
              onClick={() =>
                auditTrace.open({
                  entityType: 'User',
                  entityIdentifier: record.userEmail,
                  entityName: record.userEmail,
                })
              }
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
              onConfirm={() => handleDeactivateUser(record.userEmail)}
              okText={tCommon('general.yes')}
              cancelText={tCommon('general.no')}
              okButtonProps={{ danger: true }}
            >
              <Tooltip title={tSystem('actions.deactivate')}>
                <Button
                  type="text"
                  danger
                  icon={<StopOutlined />}
                  loading={deactivateUserMutation.isPending}
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
              onConfirm={() => handleReactivateUser(record.userEmail)}
              okText={tCommon('general.yes')}
              cancelText={tCommon('general.no')}
            >
              <Tooltip title={tSystem('actions.activate')}>
                <Button
                  type="text"
                  icon={<CheckOutlined />}
                  loading={reactivateUserMutation.isPending}
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

  const mobileRender = useMemo(
    // eslint-disable-next-line react/display-name
    () => (record: User) => {
      const menuItems: MenuProps['items'] = [
        {
          key: 'permissions',
          label: tSystem('actions.permissions'),
          icon: <SafetyOutlined />,
          onClick: () => {
            assignPermissionModal.open(record);
            setSelectedUserGroup(record.permissionsName || '');
          },
        },
        {
          key: 'trace',
          label: tSystem('actions.trace'),
          icon: <HistoryOutlined />,
          onClick: () =>
            auditTrace.open({
              entityType: 'User',
              entityIdentifier: record.userEmail,
              entityName: record.userEmail,
            }),
        },
        record.activated
          ? {
              key: 'deactivate',
              label: tSystem('actions.deactivate'),
              icon: <StopOutlined />,
              danger: true,
              onClick: () => handleDeactivateUser(record.userEmail),
            }
          : {
              key: 'activate',
              label: tSystem('actions.activate'),
              icon: <CheckOutlined />,
              onClick: () => handleReactivateUser(record.userEmail),
            },
      ];

      return (
        <MobileCard
          actions={
            <Dropdown menu={{ items: menuItems }} trigger={['click']} placement="bottomRight">
              <Button
                type="text"
                size="small"
                icon={<MoreOutlined />}
                onClick={(e) => e.stopPropagation()}
                aria-label="Actions"
              />
            </Dropdown>
          }
        >
          <Space>
            <UserOutlined />
            <Typography.Text strong className="truncate">
              {record.userEmail}
            </Typography.Text>
          </Space>
          <Flex gap={8} wrap>
            {record.activated ? (
              <Tag icon={<CheckCircleOutlined />}>{t('users.status.active')}</Tag>
            ) : (
              <Tag icon={<StopOutlined />}>{t('users.status.inactive')}</Tag>
            )}
            {record.permissionsName && (
              <Tag icon={<SafetyOutlined />}>{record.permissionsName}</Tag>
            )}
          </Flex>
        </MobileCard>
      );
    },
    [t, tSystem, assignPermissionModal, auditTrace, handleDeactivateUser, handleReactivateUser]
  );

  return (
    <Flex vertical>
      <Flex vertical gap={16}>
        <ResourceListView
          title={
            <Flex vertical>
              <Typography.Title level={4}>{t('users.title')}</Typography.Title>
              <Typography.Text>{t('users.subtitle')}</Typography.Text>
            </Flex>
          }
          loading={usersLoading}
          data={users}
          columns={userColumns}
          mobileRender={mobileRender}
          rowKey="userEmail"
          searchPlaceholder={t('users.searchPlaceholder')}
          data-testid="system-user-table"
          actions={
            <Tooltip title={tSystem('actions.createUser')}>
              <Button
                type="primary"
                icon={<PlusOutlined />}
                onClick={() => createUserModal.open()}
                data-testid="system-create-user-button"
                aria-label={tSystem('actions.createUser')}
              />
            </Tooltip>
          }
        />
      </Flex>

      <Modal
        title={t('users.modals.createTitle')}
        open={createUserModal.isOpen}
        onCancel={() => {
          createUserModal.close();
          userForm.reset();
        }}
        footer={null}
      >
        <ResourceForm
          form={userForm}
          fields={userFormFields}
          onSubmit={handleCreateUser}
          submitText={tCommon('actions.create')}
          cancelText={tCommon('actions.cancel')}
          onCancel={() => {
            createUserModal.close();
            userForm.reset();
          }}
          loading={createUserMutation.isPending}
        />
      </Modal>

      <Modal
        title={`${t('users.modals.assignTitle')} - ${assignPermissionModal.state.data?.userEmail || ''}`}
        open={assignPermissionModal.isOpen}
        onCancel={() => {
          assignPermissionModal.close();
          setSelectedUserGroup('');
        }}
        onOk={handleAssignUserPermissions}
        okText={tCommon('actions.assign')}
        confirmLoading={assignUserPermissionsMutation.isPending}
        okButtonProps={{ 'data-testid': 'modal-assign-permissions-ok' }}
        cancelButtonProps={{ 'data-testid': 'modal-assign-permissions-cancel' }}
      >
        <Form layout="vertical">
          <Form.Item label={t('users.modals.permissionGroupLabel')}>
            <Select
              value={selectedUserGroup}
              onChange={(value) => setSelectedUserGroup((value as string) || '')}
              placeholder={t('users.modals.permissionGroupPlaceholder')}
              options={permissionGroups?.map((group: PermissionGroup) => ({
                value: group.permissionGroupName,
                label: `${group.permissionGroupName} (${group.userCount} ${t('users.modals.usersLabel')}, ${group.permissionCount} ${t('users.modals.permissionsLabel')})`,
              }))}
              allowClear
              data-testid="user-permission-group-select"
            />
          </Form.Item>
        </Form>
      </Modal>

      <AuditTraceModal
        open={auditTrace.isOpen}
        onCancel={auditTrace.close}
        entityType={auditTrace.entityType}
        entityIdentifier={auditTrace.entityIdentifier}
        entityName={auditTrace.entityName}
      />
    </Flex>
  );
};

export default UsersPage;
