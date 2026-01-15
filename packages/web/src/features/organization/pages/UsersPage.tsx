import type {
  GetOrganizationPermissionGroups_ResultSet1,
  GetOrganizationUsers_ResultSet1,
} from '@rediacc/shared/types';
import { Flex, Form, type MenuProps, Modal, Select, Space, Tag, Typography } from 'antd';
import React, { useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  useCreateNewUser,
  useGetOrganizationUsers,
  useGetOrganizationPermissionGroups as usePermissionGroupsQuery,
  useUpdateUserAssignedPermissions,
  useUpdateUserToActivated,
  useUpdateUserToDeactivated,
} from '@/api/api-hooks.generated';
import type { CreateUserInput } from '@/api/mutation-transforms';
import AuditTraceModal from '@/components/common/AuditTraceModal';
import { TooltipButton } from '@/components/common/buttons';
import { buildUserColumns } from '@/components/common/columns/builders/userColumns';
import { MobileCard } from '@/components/common/MobileCard';
import {
  buildDivider,
  buildPermissionsMenuItem,
  buildTraceMenuItem,
} from '@/components/common/menuBuilders';
import { PageHeader } from '@/components/common/PageHeader';
import { ResourceActionsDropdown } from '@/components/common/ResourceActionsDropdown';
import ResourceListView from '@/components/common/ResourceListView';
import ResourceForm from '@/features/organization/components/ResourceForm';
import type { FormFieldConfig } from '@/features/organization/components/ResourceForm/types';
import { useDialogState, useTraceModal } from '@/hooks/useDialogState';
import {
  CheckCircleOutlined,
  CheckOutlined,
  PlusOutlined,
  SafetyOutlined,
  StopOutlined,
  UserOutlined,
} from '@/utils/optimizedIcons';

const UsersPage: React.FC = () => {
  const { t } = useTranslation('organization');
  const { t: tSystem } = useTranslation('system');
  const { t: tCommon } = useTranslation('common');

  const createUserModal = useDialogState();
  const assignPermissionModal = useDialogState<GetOrganizationUsers_ResultSet1>();
  const [selectedUserGroup, setSelectedUserGroup] = useState('');
  const auditTrace = useTraceModal();

  const [userForm] = Form.useForm<CreateUserInput>();

  const { data: users = [], isLoading: usersLoading } = useGetOrganizationUsers();
  const [searchQuery, setSearchQuery] = useState('');
  const createUserMutation = useCreateNewUser();
  const deactivateUserMutation = useUpdateUserToDeactivated();
  const reactivateUserMutation = useUpdateUserToActivated();
  const assignUserPermissionsMutation = useUpdateUserAssignedPermissions();
  const { data: permissionGroups = [] } = usePermissionGroupsQuery();

  const userFormFields: FormFieldConfig[] = [
    {
      name: 'email',
      label: t('users.form.emailLabel'),
      type: 'email',
      placeholder: 'user@example.com',
      required: true,
      rules: [
        { required: true, message: `${t('users.form.emailLabel')} is required` },
        { type: 'email', message: 'Invalid email address' },
      ],
    },
    {
      name: 'password',
      label: t('users.form.passwordLabel'),
      type: 'password',
      placeholder: t('users.form.passwordPlaceholder'),
      required: true,
      rules: [
        { required: true, message: `${t('users.form.passwordLabel')} is required` },
        { min: 8, message: 'Password must be at least 8 characters' },
      ],
    },
  ];

  const handleCreateUser = async (data: Record<string, unknown>) => {
    try {
      await createUserMutation.mutateAsync(data as unknown as CreateUserInput);
      createUserModal.close();
      userForm.resetFields();
    } catch {
      // handled by mutation
    }
  };

  const handleDeactivateUser = useCallback(
    async (userEmail: string) => {
      try {
        await deactivateUserMutation.mutateAsync({ userEmail });
      } catch {
        // handled by mutation
      }
    },
    [deactivateUserMutation]
  );

  const handleReactivateUser = useCallback(
    async (userEmail: string) => {
      try {
        await reactivateUserMutation.mutateAsync({ userEmail });
      } catch {
        // handled by mutation
      }
    },
    [reactivateUserMutation]
  );

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

  const handleOpenPermissionsModal = useCallback(
    (record: GetOrganizationUsers_ResultSet1) => {
      assignPermissionModal.open(record);
      setSelectedUserGroup(record.permissionsName ?? '');
    },
    [assignPermissionModal]
  );

  const filteredUsers = useMemo(() => {
    if (!searchQuery) return users;
    const query = searchQuery.toLowerCase();
    return users.filter((user) => {
      const email = (user.userEmail ?? '').toLowerCase();
      const group = (user.permissionsName ?? '').toLowerCase();
      return email.includes(query) || group.includes(query);
    });
  }, [searchQuery, users]);

  const userColumns = useMemo(
    () =>
      buildUserColumns({
        t,
        onAssignPermissions: handleOpenPermissionsModal,
        onTrace: (record) =>
          auditTrace.open({
            entityType: 'User',
            entityIdentifier: record.userEmail ?? '',
            entityName: record.userEmail ?? undefined,
          }),
        onDeactivate: handleDeactivateUser,
        onReactivate: handleReactivateUser,
        isDeactivating: deactivateUserMutation.isPending,
        isReactivating: reactivateUserMutation.isPending,
      }),
    [
      t,
      handleOpenPermissionsModal,
      auditTrace,
      handleDeactivateUser,
      handleReactivateUser,
      deactivateUserMutation.isPending,
      reactivateUserMutation.isPending,
    ]
  );

  const mobileRender = useMemo(
    // eslint-disable-next-line react/display-name
    () => (record: GetOrganizationUsers_ResultSet1) => {
      const menuItems: MenuProps['items'] = [
        buildPermissionsMenuItem(tCommon, () => {
          assignPermissionModal.open(record);
          setSelectedUserGroup(record.permissionsName ?? '');
        }),
        buildTraceMenuItem(tCommon, () =>
          auditTrace.open({
            entityType: 'User',
            entityIdentifier: record.userEmail ?? '',
            entityName: record.userEmail ?? undefined,
          })
        ),
        buildDivider(),
        record.activated
          ? {
              key: 'deactivate',
              label: tSystem('actions.deactivate'),
              icon: <StopOutlined />,
              danger: true,
              onClick: () => handleDeactivateUser(record.userEmail ?? ''),
            }
          : {
              key: 'activate',
              label: tSystem('actions.activate'),
              icon: <CheckOutlined />,
              onClick: () => handleReactivateUser(record.userEmail ?? ''),
            },
      ];

      return (
        <MobileCard actions={<ResourceActionsDropdown menuItems={menuItems} />}>
          <Space>
            <UserOutlined />
            <Typography.Text strong className="truncate">
              {record.userEmail}
            </Typography.Text>
          </Space>
          <Flex className="gap-sm" wrap>
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

    [
      t,
      tSystem,
      tCommon,
      assignPermissionModal,
      auditTrace,
      handleDeactivateUser,
      handleReactivateUser,
    ]
  );

  return (
    <Flex vertical>
      <Flex vertical>
        <ResourceListView
          title={<PageHeader title={t('users.title')} subtitle={t('users.subtitle')} />}
          loading={usersLoading}
          data={filteredUsers}
          columns={userColumns}
          mobileRender={mobileRender}
          rowKey="userEmail"
          searchPlaceholder={t('users.searchPlaceholder')}
          onSearch={(value) => setSearchQuery(value)}
          data-testid="system-user-table"
          actions={
            <TooltipButton
              tooltip={tSystem('actions.createUser')}
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => createUserModal.open()}
              data-testid="system-create-user-button"
            />
          }
        />
      </Flex>

      <Modal
        title={t('users.modals.createTitle')}
        open={createUserModal.isOpen}
        onCancel={() => {
          createUserModal.close();
          userForm.resetFields();
        }}
        footer={null}
        centered
        data-testid="users-create-modal"
      >
        <ResourceForm
          form={userForm}
          fields={userFormFields}
          onSubmit={handleCreateUser}
          submitText={tCommon('actions.create')}
          cancelText={tCommon('actions.cancel')}
          onCancel={() => {
            createUserModal.close();
            userForm.resetFields();
          }}
          loading={createUserMutation.isPending}
        />
      </Modal>

      <Modal
        title={`${t('users.modals.assignTitle')} - ${assignPermissionModal.state.data?.userEmail ?? ''}`}
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
        centered
        data-testid="users-assign-permissions-modal"
      >
        <Form layout="vertical">
          <Form.Item label={t('users.modals.permissionGroupLabel')}>
            <Select
              value={selectedUserGroup}
              onChange={(value) => setSelectedUserGroup(value || '')}
              placeholder={t('users.modals.permissionGroupPlaceholder')}
              options={permissionGroups.map(
                (group: GetOrganizationPermissionGroups_ResultSet1) => ({
                  value: group.permissionGroupName,
                  label: `${group.permissionGroupName} (${group.userCount} ${t('users.modals.usersLabel')}, ${group.permissionCount} ${t('users.modals.permissionsLabel')})`,
                })
              )}
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
