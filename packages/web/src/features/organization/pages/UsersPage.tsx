import React, { useCallback, useMemo, useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import {
  Button,
  Flex,
  Form,
  Modal,
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
import { buildUserColumns } from '@/components/common/columns/builders/userColumns';
import { buildDivider, buildTraceMenuItem } from '@/components/common/menuBuilders';
import { MobileCard } from '@/components/common/MobileCard';
import { ResourceActionsDropdown } from '@/components/common/ResourceActionsDropdown';
import ResourceListView from '@/components/common/ResourceListView';
import ResourceForm from '@/features/organization/components/ResourceForm';
import { useDialogState, useTraceModal } from '@/hooks/useDialogState';
import { CreateUserForm, createUserSchema } from '@/platform/utils/validation';
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
    (record: User) => {
      assignPermissionModal.open(record);
      setSelectedUserGroup(record.permissionsName || '');
    },
    [assignPermissionModal]
  );

  const userColumns = useMemo(
    () =>
      buildUserColumns({
        t,
        tSystem,
        tCommon,
        onAssignPermissions: handleOpenPermissionsModal,
        onTrace: (record) =>
          auditTrace.open({
            entityType: 'User',
            entityIdentifier: record.userEmail,
            entityName: record.userEmail,
          }),
        onDeactivate: handleDeactivateUser,
        onReactivate: handleReactivateUser,
        isDeactivating: deactivateUserMutation.isPending,
        isReactivating: reactivateUserMutation.isPending,
      }),
    [
      t,
      tSystem,
      tCommon,
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
        buildTraceMenuItem(tCommon, () =>
          auditTrace.open({
            entityType: 'User',
            entityIdentifier: record.userEmail,
            entityName: record.userEmail,
          })
        ),
        buildDivider(),
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
        <MobileCard actions={<ResourceActionsDropdown menuItems={menuItems} />}>
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
        centered
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
        centered
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
