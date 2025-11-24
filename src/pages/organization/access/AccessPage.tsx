import React, { useState } from 'react'
import { Button, Tooltip, Space, Modal, Input, Tabs, Card, List, Select, Popconfirm, Result } from 'antd'
import {
  SafetyOutlined,
  KeyOutlined,
  UserOutlined,
  HistoryOutlined,
  PlusOutlined,
  DeleteOutlined,
} from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { useSelector } from 'react-redux'
import ResourceListView from '@/components/common/ResourceListView'
import AuditTraceModal from '@/components/common/AuditTraceModal'
import { useDialogState, useTraceModal } from '@/hooks/useDialogState'
import UserSessionsTab from '@/components/system/UserSessionsTab'
import { useDropdownData } from '@/api/queries/useDropdownData'
import {
  usePermissionGroups as usePermissionGroupsQuery,
  usePermissionGroupDetails,
  useCreatePermissionGroup,
  useDeletePermissionGroup,
  useAddPermissionToGroup,
  useRemovePermissionFromGroup,
  useAssignUserToGroup,
  PermissionGroup,
} from '@/api/queries/permissions'
import {
  AccessPageWrapper,
  AccessSectionStack,
  AccessSectionHeading,
  AccessListHeader,
  AccessListTitle,
  AccessListSubtitle,
} from './styles'
import { ModalSize } from '@/types/modal'
import { ModalStack, InlineFormRow } from '@/components/ui'
import { FullWidthSelect } from '@/pages/system/styles'
import { showMessage } from '@/utils/messages'
import { RootState } from '@/store/store'

const AccessPage: React.FC = () => {
  const { t } = useTranslation('organization')
  const { t: tSystem } = useTranslation('system')
  const { t: tCommon } = useTranslation('common')
  const uiMode = useSelector((state: RootState) => state.ui.uiMode)

  const [activeTab, setActiveTab] = useState<'permissions' | 'sessions'>('permissions')
  const createModal = useDialogState()
  const manageModal = useDialogState<PermissionGroup>()
  const assignModal = useDialogState<PermissionGroup>()
  const [newGroupName, setNewGroupName] = useState('')
  const [selectedPermission, setSelectedPermission] = useState('')
  const [selectedUser, setSelectedUser] = useState('')
  const auditTrace = useTraceModal()

  const { data: dropdownData } = useDropdownData()
  const availablePermissions = dropdownData?.permissions || []
  const { data: permissionGroups = [], isLoading: permissionsLoading } = usePermissionGroupsQuery()
  const { data: groupDetails } = usePermissionGroupDetails(manageModal.state.data?.permissionGroupName || '')
  const createGroupMutation = useCreatePermissionGroup()
  const deleteGroupMutation = useDeletePermissionGroup()
  const addPermissionMutation = useAddPermissionToGroup()
  const removePermissionMutation = useRemovePermissionFromGroup()
  const assignUserMutation = useAssignUserToGroup()

  const handleCreateGroup = async () => {
    if (!newGroupName.trim()) {
      showMessage('error', t('access.modals.groupNameRequired', { defaultValue: 'Please enter a group name' }))
      return
    }

    try {
      await createGroupMutation.mutateAsync({ permissionGroupName: newGroupName.trim() })
      createModal.close()
      setNewGroupName('')
    } catch {
      // handled by mutation
    }
  }

  const handleDeleteGroup = async (groupName: string) => {
    try {
      await deleteGroupMutation.mutateAsync(groupName)
    } catch {
      // handled by mutation
    }
  }

  const handleAddPermission = async () => {
    if (!manageModal.state.data || !selectedPermission) return

    try {
      await addPermissionMutation.mutateAsync({
        permissionGroupName: manageModal.state.data.permissionGroupName,
        permissionName: selectedPermission,
      })
      setSelectedPermission('')
    } catch {
      // handled by mutation
    }
  }

  const handleRemovePermission = async (permission: string) => {
    if (!manageModal.state.data) return

    try {
      await removePermissionMutation.mutateAsync({
        permissionGroupName: manageModal.state.data.permissionGroupName,
        permissionName: permission,
      })
    } catch {
      // handled by mutation
    }
  }

  const handleAssignUser = async () => {
    if (!assignModal.state.data || !selectedUser) return

    try {
      await assignUserMutation.mutateAsync({
        userEmail: selectedUser,
        permissionGroupName: assignModal.state.data.permissionGroupName,
      })
      assignModal.close()
      setSelectedUser('')
    } catch {
      // handled by mutation
    }
  }

  const permissionColumns = [
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
          <span>{count}</span>
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
          <span>{count}</span>
        </Space>
      ),
    },
    {
      title: tSystem('tables.permissionGroups.actions'),
      key: 'actions',
      width: 360,
      render: (_: any, record: PermissionGroup) => (
        <Space>
          <Tooltip title={tSystem('actions.permissions')}>
            <Button
              type="primary"
              size="small"
              icon={<KeyOutlined />}
              onClick={() => manageModal.open(record)}
              data-testid={`system-permission-group-manage-button-${record.permissionGroupName}`}
              aria-label={tSystem('actions.permissions')}
            />
          </Tooltip>
          <Tooltip title={tSystem('actions.assignUser')}>
            <Button
              type="primary"
              size="small"
              icon={<UserOutlined />}
              onClick={() => assignModal.open(record)}
              data-testid={`system-permission-group-assign-user-button-${record.permissionGroupName}`}
              aria-label={tSystem('actions.assignUser')}
            />
          </Tooltip>
          <Tooltip title={tSystem('actions.trace')}>
            <Button
              type="primary"
              size="small"
              icon={<HistoryOutlined />}
              onClick={() =>
                auditTrace.open({
                  entityType: 'Permissions',
                  entityIdentifier: record.permissionGroupName,
                  entityName: record.permissionGroupName,
                })
              }
              data-testid={`system-permission-group-trace-button-${record.permissionGroupName}`}
              aria-label={tSystem('actions.trace')}
            />
          </Tooltip>
          <Popconfirm
            title={t('access.modals.deleteGroupTitle', { defaultValue: 'Delete Permission Group' })}
            description={t('access.modals.deleteGroupDescription', {
              defaultValue: 'Are you sure you want to delete group "{{group}}"?',
              group: record.permissionGroupName,
            })}
            onConfirm={() => handleDeleteGroup(record.permissionGroupName)}
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
                loading={deleteGroupMutation.isPending}
                data-testid={`system-permission-group-delete-button-${record.permissionGroupName}`}
                aria-label={tCommon('actions.delete')}
              />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const permissionsContent = (
    <ResourceListView
      title={
        <AccessListHeader>
          <AccessListTitle>{t('access.permissions.title', { defaultValue: 'Permission Groups' })}</AccessListTitle>
          <AccessListSubtitle>
            {t('access.permissions.subtitle', { defaultValue: 'Manage permission groups and their assignments' })}
          </AccessListSubtitle>
        </AccessListHeader>
      }
      loading={permissionsLoading}
      data={permissionGroups as any}
      columns={permissionColumns as any}
      rowKey="permissionGroupName"
      searchPlaceholder={t('access.permissions.searchPlaceholder', { defaultValue: 'Search permission groups...' })}
      data-testid="system-permission-group-table"
      actions={
        <Tooltip title={tSystem('actions.createGroup')}>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => createModal.open()}
            data-testid="system-create-permission-group-button"
            aria-label={tSystem('actions.createGroup')}
          />
        </Tooltip>
      }
    />
  )

  const sessionsContent = (
    <Card>
      <UserSessionsTab />
    </Card>
  )

  if (uiMode === 'simple') {
    return (
      <AccessPageWrapper>
        <Result
          status="403"
          title={tSystem('accessControl.expertOnlyTitle', { defaultValue: 'Expert Mode Required' })}
          subTitle={tSystem('accessControl.expertOnlyMessage', { defaultValue: 'Switch to expert mode to manage access control.' })}
        />
      </AccessPageWrapper>
    )
  }

  return (
    <AccessPageWrapper>
      <AccessSectionStack>
        <AccessSectionHeading level={3}>{t('access.heading', { defaultValue: 'Access Control' })}</AccessSectionHeading>
        <Card>
          <Tabs
            activeKey={activeTab}
            onChange={(key) => setActiveTab(key as 'permissions' | 'sessions')}
            items={[
              {
                key: 'permissions',
                label: t('access.tabs.permissions', { defaultValue: 'Permissions' }),
                children: permissionsContent,
              },
              {
                key: 'sessions',
                label: t('access.tabs.sessions', { defaultValue: 'Sessions' }),
                children: sessionsContent,
              },
            ]}
          />
        </Card>
      </AccessSectionStack>

      <Modal
        title={t('access.modals.createGroupTitle', { defaultValue: 'Create Permission Group' })}
        open={createModal.isOpen}
        onCancel={() => {
          createModal.close()
          setNewGroupName('')
        }}
        onOk={handleCreateGroup}
        confirmLoading={createGroupMutation.isPending}
        okButtonProps={{ 'data-testid': 'modal-create-permission-group-ok' }}
        cancelButtonProps={{ 'data-testid': 'modal-create-permission-group-cancel' }}
      >
        <Input
          placeholder={t('access.modals.groupPlaceholder', { defaultValue: 'Enter group name' })}
          value={newGroupName}
          onChange={(e) => setNewGroupName(e.target.value)}
          data-testid="system-permission-group-name-input"
          onPressEnter={handleCreateGroup}
          autoComplete="off"
        />
      </Modal>

      <Modal
        title={`${t('access.modals.managePermissionsTitle', { defaultValue: 'Manage Permissions' })} - ${
          manageModal.state.data?.permissionGroupName || ''
        }`}
        open={manageModal.isOpen}
        onCancel={() => {
          manageModal.close()
          setSelectedPermission('')
        }}
        footer={null}
        className={ModalSize.Large}
      >
        <Tabs
          items={[
            {
              key: 'current',
              label: t('access.modals.currentPermissionsTab', { defaultValue: 'Current Permissions' }),
              children: (
                <Card>
                  <List
                    dataSource={groupDetails?.permissions || []}
                    locale={{ emptyText: t('access.modals.noPermissions', { defaultValue: 'No permissions assigned' }) }}
                    renderItem={(permission: string) => (
                      <List.Item
                        actions={[
                          <Tooltip key="remove" title={tCommon('actions.remove')}>
                            <Button
                              type="primary"
                              danger
                              size="small"
                              onClick={() => handleRemovePermission(permission)}
                              loading={removePermissionMutation.isPending}
                              data-testid={`permission-remove-button-${permission}`}
                              aria-label={tCommon('actions.remove')}
                            />
                          </Tooltip>,
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
              label: t('access.modals.addPermissionsTab', { defaultValue: 'Add Permissions' }),
              children: (
                <ModalStack>
                  <InlineFormRow>
                    <FullWidthSelect
                      placeholder={t('access.modals.permissionPlaceholder', { defaultValue: 'Select permission to add' })}
                      value={selectedPermission}
                      onChange={(value) => setSelectedPermission((value as string) || '')}
                      showSearch
                      filterOption={(input, option) =>
                        String(option?.label ?? '').toLowerCase().includes(input.toLowerCase())
                      }
                      data-testid="permission-select-add"
                    >
                      {availablePermissions.map((perm) => (
                        <Select.Option
                          key={perm.name}
                          value={perm.name}
                          label={perm.name}
                          disabled={groupDetails?.permissions?.includes(perm.name)}
                          data-testid={`permission-option-${perm.name}`}
                        >
                          {perm.name}
                        </Select.Option>
                      ))}
                    </FullWidthSelect>
                    <Tooltip title={tSystem('actions.addPermission')}>
                      <Button
                        type="primary"
                        onClick={handleAddPermission}
                        loading={addPermissionMutation.isPending}
                        disabled={!selectedPermission}
                        data-testid="permission-add-button"
                        aria-label={tSystem('actions.addPermission')}
                        icon={<PlusOutlined />}
                      />
                    </Tooltip>
                  </InlineFormRow>
                </ModalStack>
              ),
            },
          ]}
        />
      </Modal>

      <Modal
        title={`${t('access.modals.assignUserTitle', { defaultValue: 'Assign User' })} ${
          assignModal.state.data ? t('access.modals.assignUserTo', { defaultValue: 'to {{group}}', group: assignModal.state.data.permissionGroupName }) : ''
        }`}
        open={assignModal.isOpen}
        onCancel={() => {
          assignModal.close()
          setSelectedUser('')
        }}
        onOk={handleAssignUser}
        confirmLoading={assignUserMutation.isPending}
        okButtonProps={{ 'data-testid': 'modal-assign-user-ok' }}
        cancelButtonProps={{ 'data-testid': 'modal-assign-user-cancel' }}
      >
        <FullWidthSelect
          placeholder={t('access.modals.userPlaceholder', { defaultValue: 'Select user' })}
          value={selectedUser}
          onChange={(value) => setSelectedUser((value as string) || '')}
          showSearch
          filterOption={(input, option) => (option?.label ?? '').toLowerCase().includes(input.toLowerCase())}
          options={
            dropdownData?.users?.map((user) => ({
              value: user.value,
              label: user.label,
              disabled: user.status !== 'active',
            })) || []
          }
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
    </AccessPageWrapper>
  )
}

export default AccessPage
