import React, { useCallback, useMemo, useState } from 'react';
import {
  Badge,
  Card,
  Flex,
  Input,
  List,
  Modal,
  Result,
  Select,
  Select as AntSelect,
  Space,
  Tabs,
  Typography,
  type MenuProps,
} from 'antd';
import { useTranslation } from 'react-i18next';
import { useSelector } from 'react-redux';
import {
  useCreatePermissionInGroup,
  useUpdateUserAssignedPermissions as useAssignUserToGroup,
  useCreatePermissionGroup,
  useDeletePermissionGroup,
  useGetPermissionGroupDetails,
  useGetOrganizationPermissionGroups as usePermissionGroupsQuery,
  useDeletePermissionFromGroup,
} from '@/api/api-hooks.generated';
import { useDropdownData } from '@/api/queries/useDropdownData';
import AuditTraceModal from '@/components/common/AuditTraceModal';
import { TooltipButton } from '@/components/common/buttons';
import { buildPermissionColumns } from '@/components/common/columns/builders/accessColumns';
import {
  buildDeleteMenuItem,
  buildDivider,
  buildTraceMenuItem,
} from '@/components/common/menuBuilders';
import { MobileCard } from '@/components/common/MobileCard';
import { PageHeader } from '@/components/common/PageHeader';
import { ResourceActionsDropdown } from '@/components/common/ResourceActionsDropdown';
import ResourceListView from '@/components/common/ResourceListView';
import UserSessionsTab from '@/features/organization/components/UserSessionsTab';
import { useDialogState, useTraceModal } from '@/hooks/useDialogState';
import { RootState } from '@/store/store';
import { ModalSize } from '@/types/modal';
import { showMessage } from '@/utils/messages';
import { KeyOutlined, PlusOutlined, SafetyOutlined, UserOutlined } from '@/utils/optimizedIcons';
import type { GetOrganizationPermissionGroups_ResultSet1 } from '@rediacc/shared/types';

const AccessPage: React.FC = () => {
  const { t } = useTranslation('organization');
  const { t: tSystem } = useTranslation('system');
  const { t: tCommon } = useTranslation('common');
  const uiMode = useSelector((state: RootState) => state.ui.uiMode);

  const [activeTab, setActiveTab] = useState<'permissions' | 'sessions'>('permissions');
  const createModal = useDialogState();
  const manageModal = useDialogState<GetOrganizationPermissionGroups_ResultSet1>();
  const assignModal = useDialogState<GetOrganizationPermissionGroups_ResultSet1>();
  const [newGroupName, setNewGroupName] = useState('');
  const [selectedPermission, setSelectedPermission] = useState('');
  const [selectedUser, setSelectedUser] = useState('');
  const auditTrace = useTraceModal();

  const { data: dropdownData } = useDropdownData();
  const availablePermissions = dropdownData?.permissions ?? [];
  const { data: permissionGroups = [], isLoading: permissionsLoading } = usePermissionGroupsQuery();
  const { data: groupDetails } = useGetPermissionGroupDetails(
    manageModal.state.data?.permissionGroupName ?? ''
  );
  const createGroupMutation = useCreatePermissionGroup();
  const deleteGroupMutation = useDeletePermissionGroup();
  const addPermissionMutation = useCreatePermissionInGroup();
  const removePermissionMutation = useDeletePermissionFromGroup();
  const assignUserMutation = useAssignUserToGroup();

  const handleCreateGroup = async () => {
    if (!newGroupName.trim()) {
      showMessage('error', t('access.modals.groupNameRequired'));
      return;
    }

    try {
      await createGroupMutation.mutateAsync({ permissionGroupName: newGroupName.trim() });
      createModal.close();
      setNewGroupName('');
    } catch {
      // handled by mutation
    }
  };

  const handleDeleteGroup = useCallback(
    async (groupName: string) => {
      try {
        await deleteGroupMutation.mutateAsync({ permissionGroupName: groupName });
      } catch {
        // handled by mutation
      }
    },
    [deleteGroupMutation]
  );

  const handleAddPermission = async () => {
    if (!manageModal.state.data || !selectedPermission) return;

    try {
      await addPermissionMutation.mutateAsync({
        permissionGroupName: manageModal.state.data.permissionGroupName,
        permissionName: selectedPermission,
      });
      setSelectedPermission('');
    } catch {
      // handled by mutation
    }
  };

  const handleRemovePermission = async (permission: string) => {
    if (!manageModal.state.data) return;

    try {
      await removePermissionMutation.mutateAsync({
        permissionGroupName: manageModal.state.data.permissionGroupName,
        permissionName: permission,
      });
    } catch {
      // handled by mutation
    }
  };

  const handleAssignUser = async () => {
    if (!assignModal.state.data || !selectedUser) return;

    try {
      await assignUserMutation.mutateAsync({
        userEmail: selectedUser,
        permissionGroupName: assignModal.state.data.permissionGroupName,
      });
      assignModal.close();
      setSelectedUser('');
    } catch {
      // handled by mutation
    }
  };

  const permissionColumns = useMemo(
    () =>
      buildPermissionColumns({
        t,
        onManagePermissions: manageModal.open,
        onAssignUser: assignModal.open,
        onTrace: (record) =>
          auditTrace.open({
            entityType: 'Permissions',
            entityIdentifier: record.permissionGroupName ?? '',
            entityName: record.permissionGroupName ?? undefined,
          }),
        onDeleteGroup: handleDeleteGroup,
        isDeleting: deleteGroupMutation.isPending,
      }),
    [
      t,
      manageModal.open,
      assignModal.open,
      auditTrace,
      handleDeleteGroup,
      deleteGroupMutation.isPending,
    ]
  );

  const mobileRender = useMemo(
    // eslint-disable-next-line react/display-name
    () => (record: GetOrganizationPermissionGroups_ResultSet1) => {
      const menuItems: MenuProps['items'] = [
        {
          key: 'permissions',
          label: tSystem('actions.permissions'),
          icon: <KeyOutlined />,
          onClick: () => manageModal.open(record),
        },
        {
          key: 'assign',
          label: tSystem('actions.assignUser'),
          icon: <UserOutlined />,
          onClick: () => assignModal.open(record),
        },
        buildTraceMenuItem(tCommon, () =>
          auditTrace.open({
            entityType: 'Permissions',
            entityIdentifier: record.permissionGroupName ?? '',
            entityName: record.permissionGroupName ?? undefined,
          })
        ),
        buildDivider(),
        buildDeleteMenuItem(tCommon, () => handleDeleteGroup(record.permissionGroupName ?? '')),
      ];

      return (
        <MobileCard actions={<ResourceActionsDropdown menuItems={menuItems} />}>
          <Space>
            <SafetyOutlined />
            <Typography.Text strong className="truncate">
              {record.permissionGroupName}
            </Typography.Text>
          </Space>
          <Flex className="gap-sm" wrap>
            <Space size="small">
              <Badge count={record.userCount} showZero size="small">
                <UserOutlined />
              </Badge>
            </Space>
            <Space size="small">
              <KeyOutlined />
              <Typography.Text>{record.permissionCount}</Typography.Text>
            </Space>
          </Flex>
        </MobileCard>
      );
    },
    [tSystem, tCommon, manageModal, assignModal, auditTrace, handleDeleteGroup]
  );

  const permissionsContent = (
    <ResourceListView
      title={
        <PageHeader
          title={t('access.permissions.title')}
          subtitle={t('access.permissions.subtitle')}
        />
      }
      loading={permissionsLoading}
      data={permissionGroups}
      columns={permissionColumns}
      mobileRender={mobileRender}
      rowKey="permissionGroupName"
      searchPlaceholder={t('access.permissions.searchPlaceholder')}
      data-testid="system-permission-group-table"
      actions={
        <TooltipButton
          tooltip={tSystem('actions.createGroup')}
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => createModal.open()}
          data-testid="system-create-permission-group-button"
        />
      }
    />
  );

  const sessionsContent = (
    <Card>
      <UserSessionsTab />
    </Card>
  );

  if (uiMode === 'simple') {
    return (
      <Flex vertical>
        <Result
          status="403"
          title={tSystem('accessControl.expertOnlyTitle')}
          subTitle={tSystem('accessControl.expertOnlyMessage')}
        />
      </Flex>
    );
  }

  return (
    <Flex vertical>
      <Card>
        <Tabs
          activeKey={activeTab}
          onChange={(key) => setActiveTab(key as 'permissions' | 'sessions')}
          items={[
            {
              key: 'permissions',
              label: t('access.tabs.permissions'),
              children: permissionsContent,
            },
            {
              key: 'sessions',
              label: t('access.tabs.sessions'),
              children: sessionsContent,
            },
          ]}
        />
      </Card>

      <Modal
        title={t('access.modals.createGroupTitle')}
        open={createModal.isOpen}
        onCancel={() => {
          createModal.close();
          setNewGroupName('');
        }}
        onOk={handleCreateGroup}
        confirmLoading={createGroupMutation.isPending}
        okButtonProps={{ 'data-testid': 'modal-create-permission-group-ok' }}
        cancelButtonProps={{ 'data-testid': 'modal-create-permission-group-cancel' }}
        centered
        data-testid="access-create-group-modal"
      >
        <Input
          placeholder={t('access.modals.groupPlaceholder')}
          value={newGroupName}
          onChange={(e) => setNewGroupName(e.target.value)}
          data-testid="system-permission-group-name-input"
          onPressEnter={handleCreateGroup}
          autoComplete="off"
        />
      </Modal>

      <Modal
        title={`${t('access.modals.managePermissionsTitle')} - ${manageModal.state.data?.permissionGroupName ?? ''}`}
        open={manageModal.isOpen}
        onCancel={() => {
          manageModal.close();
          setSelectedPermission('');
        }}
        footer={null}
        className={ModalSize.Large}
        centered
        data-testid="access-manage-permissions-modal"
      >
        <Tabs
          items={[
            {
              key: 'current',
              label: t('access.modals.currentPermissionsTab'),
              children: (
                <Card>
                  <List
                    dataSource={groupDetails?.map((d) => d.permissionName ?? '') ?? []}
                    locale={{
                      emptyText: t('access.modals.noPermissions'),
                    }}
                    renderItem={(permission: string) => (
                      <List.Item
                        actions={[
                          <TooltipButton
                            key="remove"
                            tooltip={tCommon('actions.remove')}
                            type="primary"
                            danger
                            size="small"
                            onClick={() => handleRemovePermission(permission)}
                            loading={removePermissionMutation.isPending}
                            data-testid={`permission-remove-button-${permission}`}
                          />,
                        ]}
                      >
                        <List.Item.Meta avatar={<KeyOutlined />} title={permission} />
                      </List.Item>
                    )}
                  />
                </Card>
              ),
            },
            {
              key: 'add',
              label: t('access.modals.addPermissionsTab'),
              children: (
                <Flex vertical>
                  <Flex align="center" wrap>
                    <Select
                      placeholder={t('access.modals.permissionPlaceholder')}
                      value={selectedPermission}
                      onChange={(value) => setSelectedPermission(value || '')}
                      showSearch
                      className="flex-1"
                      filterOption={(input, option) =>
                        String(option?.label ?? '')
                          .toLowerCase()
                          .includes(input.toLowerCase())
                      }
                      data-testid="permission-select-add"
                    >
                      {availablePermissions.map((perm) => (
                        <AntSelect.Option
                          key={perm.name}
                          value={perm.name}
                          label={perm.name}
                          disabled={groupDetails?.some((d) => d.permissionName === perm.name)}
                          data-testid={`permission-option-${perm.name}`}
                        >
                          {perm.name}
                        </AntSelect.Option>
                      ))}
                    </Select>
                    <TooltipButton
                      tooltip={tSystem('actions.addPermission')}
                      type="primary"
                      onClick={handleAddPermission}
                      loading={addPermissionMutation.isPending}
                      disabled={!selectedPermission}
                      data-testid="permission-add-button"
                      icon={<PlusOutlined />}
                    />
                  </Flex>
                </Flex>
              ),
            },
          ]}
        />
      </Modal>

      <Modal
        title={`${t('access.modals.assignUserTitle')} ${
          assignModal.state.data
            ? t('access.modals.assignUserTo', {
                group: assignModal.state.data.permissionGroupName,
              })
            : ''
        }`}
        open={assignModal.isOpen}
        onCancel={() => {
          assignModal.close();
          setSelectedUser('');
        }}
        onOk={handleAssignUser}
        confirmLoading={assignUserMutation.isPending}
        okButtonProps={{ 'data-testid': 'modal-assign-user-ok' }}
        data-testid="access-assign-user-modal"
        cancelButtonProps={{ 'data-testid': 'modal-assign-user-cancel' }}
        centered
      >
        <Select
          placeholder={t('access.modals.userPlaceholder')}
          value={selectedUser}
          onChange={(value) => setSelectedUser(value || '')}
          showSearch
          className="w-full"
          filterOption={(input, option) =>
            (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
          }
          options={(dropdownData?.users ?? []).map((user) => ({
            value: user.value,
            label: user.label,
            disabled: user.status !== 'active',
          }))}
          data-testid="assign-user-select"
        />
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

export default AccessPage;
