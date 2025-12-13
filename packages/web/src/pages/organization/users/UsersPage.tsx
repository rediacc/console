import React, { useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { Form, Modal, Popconfirm, Space, Tag, Tooltip } from 'antd';
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
import ResourceListView from '@/components/common/ResourceListView';
import {
  ListTitleRow as UsersListHeader,
  ListSubtitle as UsersListSubtitle,
  ListTitle as UsersListTitle,
  PageWrapper as UsersPageWrapper,
  RediaccButton,
  RediaccSelect,
  SectionHeading as UsersSectionHeading,
  SectionStack as UsersSectionStack,
} from '@/components/ui';
import { useDialogState, useTraceModal } from '@/hooks/useDialogState';
import ResourceForm from '@/pages/organization/users/components/ResourceForm';
import {
  CheckCircleOutlined,
  CheckOutlined,
  HistoryOutlined,
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
      label: t('users.form.emailLabel', { defaultValue: 'Email' }),
      type: 'email' as const,
      placeholder: 'user@example.com',
      required: true,
    },
    {
      name: 'newUserPassword',
      label: t('users.form.passwordLabel', { defaultValue: 'Password' }),
      type: 'password' as const,
      placeholder: t('users.form.passwordPlaceholder', { defaultValue: 'Enter password' }),
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
          <Tag icon={<CheckCircleOutlined />} color="success">
            {t('users.status.active', { defaultValue: 'Active' })}
          </Tag>
        ) : (
          <Tag icon={<StopOutlined />} color="default">
            {t('users.status.inactive', { defaultValue: 'Inactive' })}
          </Tag>
        ),
    },
    {
      title: tSystem('tables.users.permissionGroup'),
      dataIndex: 'permissionGroupName',
      key: 'permissionGroupName',
      render: (group: string) =>
        group ? (
          <Tag icon={<SafetyOutlined />} color="blue">
            {group}
          </Tag>
        ) : (
          <Tag color="default">
            {t('users.permissionGroups.none', { defaultValue: 'No Group' })}
          </Tag>
        ),
    },
    {
      title: tSystem('tables.users.lastActive'),
      dataIndex: 'lastActive',
      key: 'lastActive',
      render: (date: string) =>
        date
          ? new Date(date).toLocaleDateString()
          : t('users.lastActive.never', { defaultValue: 'Never' }),
    },
    {
      title: tSystem('tables.users.actions'),
      key: 'actions',
      width: 300,
      render: (_: unknown, record: User) => (
        <Space>
          <Tooltip title={tSystem('actions.permissions')}>
            <RediaccButton
              variant="primary"
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
            <RediaccButton
              variant="primary"
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
              title={tSystem('users.deactivate.confirmTitle', { defaultValue: 'Deactivate User' })}
              description={tSystem('users.deactivate.confirmDescription', {
                defaultValue: 'Are you sure you want to deactivate "{{email}}"?',
                email: record.userEmail,
              })}
              onConfirm={() => handleDeactivateUser(record.userEmail)}
              okText={tCommon('general.yes')}
              cancelText={tCommon('general.no')}
              okButtonProps={{ danger: true }}
            >
              <Tooltip title={tSystem('actions.deactivate')}>
                <RediaccButton
                  variant="danger"
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
              title={tSystem('users.activate.confirmTitle', { defaultValue: 'Activate User' })}
              description={tSystem('users.activate.confirmDescription', {
                defaultValue: 'Are you sure you want to activate "{{email}}"?',
                email: record.userEmail,
              })}
              onConfirm={() => handleReactivateUser(record.userEmail)}
              okText={tCommon('general.yes')}
              cancelText={tCommon('general.no')}
            >
              <Tooltip title={tSystem('actions.activate')}>
                <RediaccButton
                  variant="primary"
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

  return (
    <UsersPageWrapper>
      <UsersSectionStack>
        <UsersSectionHeading level={3}>
          {t('users.heading', { defaultValue: 'Users' })}
        </UsersSectionHeading>
        <ResourceListView
          title={
            <UsersListHeader>
              <UsersListTitle>{t('users.title', { defaultValue: 'Users' })}</UsersListTitle>
              <UsersListSubtitle>
                {t('users.subtitle', { defaultValue: 'Manage users and their permissions' })}
              </UsersListSubtitle>
            </UsersListHeader>
          }
          loading={usersLoading}
          data={users}
          columns={userColumns}
          rowKey="userEmail"
          searchPlaceholder={t('users.searchPlaceholder', { defaultValue: 'Search users...' })}
          data-testid="system-user-table"
          actions={
            <Tooltip title={tSystem('actions.createUser')}>
              <RediaccButton
                variant="primary"
                icon={<PlusOutlined />}
                onClick={() => createUserModal.open()}
                data-testid="system-create-user-button"
                aria-label={tSystem('actions.createUser')}
              />
            </Tooltip>
          }
        />
      </UsersSectionStack>

      <Modal
        title={t('users.modals.createTitle', { defaultValue: 'Create User' })}
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
          submitText={tCommon('actions.create', { defaultValue: 'Create' })}
          cancelText={tCommon('actions.cancel', { defaultValue: 'Cancel' })}
          onCancel={() => {
            createUserModal.close();
            userForm.reset();
          }}
          loading={createUserMutation.isPending}
        />
      </Modal>

      <Modal
        title={`${t('users.modals.assignTitle', { defaultValue: 'Assign Permissions' })} - ${assignPermissionModal.state.data?.userEmail || ''}`}
        open={assignPermissionModal.isOpen}
        onCancel={() => {
          assignPermissionModal.close();
          setSelectedUserGroup('');
        }}
        onOk={handleAssignUserPermissions}
        okText={tCommon('actions.assign', { defaultValue: 'Assign' })}
        confirmLoading={assignUserPermissionsMutation.isPending}
        okButtonProps={{ 'data-testid': 'modal-assign-permissions-ok' }}
        cancelButtonProps={{ 'data-testid': 'modal-assign-permissions-cancel' }}
      >
        <Form layout="vertical">
          <Form.Item
            label={t('users.modals.permissionGroupLabel', { defaultValue: 'Permission Group' })}
          >
            <RediaccSelect
              value={selectedUserGroup}
              onChange={(value) => setSelectedUserGroup((value as string) || '')}
              placeholder={t('users.modals.permissionGroupPlaceholder', {
                defaultValue: 'Select permission group',
              })}
              options={permissionGroups?.map((group: PermissionGroup) => ({
                value: group.permissionGroupName,
                label: `${group.permissionGroupName} (${group.userCount} ${t('users.modals.usersLabel', { defaultValue: 'users' })}, ${group.permissionCount} ${t('users.modals.permissionsLabel', { defaultValue: 'permissions' })})`,
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
    </UsersPageWrapper>
  );
};

export default UsersPage;
