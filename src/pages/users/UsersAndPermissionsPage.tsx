import React, { useState } from 'react'
import { Card, Tabs, Modal, Form, Input, Button, Space, Popconfirm, Tag, Select, Badge, List, Typography } from 'antd'
import { 
  UserOutlined, 
  SafetyOutlined, 
  PlusOutlined, 
  DeleteOutlined,
  KeyOutlined,
  CheckCircleOutlined,
  StopOutlined,
  MailOutlined,
  TeamOutlined
} from '@ant-design/icons'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import ResourceListView from '@/components/common/ResourceListView'
import ResourceForm from '@/components/forms/ResourceForm'
import { useDropdownData } from '@/api/queries/useDropdownData'
import toast from 'react-hot-toast'

// User queries
import { 
  useUsers, 
  useCreateUser, 
  useDeactivateUser, 
  useAssignUserPermissions, 
  User 
} from '@/api/queries/users'

// Permission queries
import { 
  usePermissionGroups as usePermissionGroupsQuery, 
  usePermissionGroupDetails,
  useCreatePermissionGroup, 
  useDeletePermissionGroup,
  useAddPermissionToGroup,
  useRemovePermissionFromGroup,
  useAssignUserToGroup,
  PermissionGroup 
} from '@/api/queries/permissions'
import { usePermissionGroups } from '@/api/queries/users'

import { createUserSchema, CreateUserForm } from '@/utils/validation'

const { Title, Text } = Typography

// Available permissions in the system
const AVAILABLE_PERMISSIONS = [
  // Company Management
  { name: 'company.view', category: 'Company', description: 'View company details' },
  { name: 'company.update', category: 'Company', description: 'Update company settings' },
  { name: 'company.vault', category: 'Company', description: 'Manage company vault' },
  
  // User Management
  { name: 'users.view', category: 'Users', description: 'View users' },
  { name: 'users.create', category: 'Users', description: 'Create new users' },
  { name: 'users.update', category: 'Users', description: 'Update user details' },
  { name: 'users.delete', category: 'Users', description: 'Delete users' },
  { name: 'users.activate', category: 'Users', description: 'Activate/deactivate users' },
  
  // Team Management
  { name: 'teams.view', category: 'Teams', description: 'View teams' },
  { name: 'teams.create', category: 'Teams', description: 'Create teams' },
  { name: 'teams.update', category: 'Teams', description: 'Update team details' },
  { name: 'teams.delete', category: 'Teams', description: 'Delete teams' },
  { name: 'teams.members', category: 'Teams', description: 'Manage team members' },
  
  // Infrastructure
  { name: 'regions.view', category: 'Infrastructure', description: 'View regions' },
  { name: 'regions.create', category: 'Infrastructure', description: 'Create regions' },
  { name: 'regions.update', category: 'Infrastructure', description: 'Update regions' },
  { name: 'regions.delete', category: 'Infrastructure', description: 'Delete regions' },
  { name: 'bridges.all', category: 'Infrastructure', description: 'All bridge permissions' },
  { name: 'machines.all', category: 'Infrastructure', description: 'All machine permissions' },
  
  // Resources
  { name: 'repositories.all', category: 'Resources', description: 'All repository permissions' },
  { name: 'storage.all', category: 'Resources', description: 'All storage permissions' },
  { name: 'schedules.all', category: 'Resources', description: 'All schedule permissions' },
  
  // Queue Management
  { name: 'queue.view', category: 'Queue', description: 'View queue items' },
  { name: 'queue.create', category: 'Queue', description: 'Create queue items' },
  { name: 'queue.update', category: 'Queue', description: 'Update queue items' },
  { name: 'queue.delete', category: 'Queue', description: 'Delete queue items' },
  
  // Permissions
  { name: 'permissions.view', category: 'Permissions', description: 'View permission groups' },
  { name: 'permissions.create', category: 'Permissions', description: 'Create permission groups' },
  { name: 'permissions.update', category: 'Permissions', description: 'Update permission groups' },
  { name: 'permissions.delete', category: 'Permissions', description: 'Delete permission groups' },
  { name: 'permissions.assign', category: 'Permissions', description: 'Assign users to groups' },
]

const UsersAndPermissionsPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState('permissions')
  
  // User state
  const [isCreateUserModalOpen, setIsCreateUserModalOpen] = useState(false)
  const [assignPermissionModal, setAssignPermissionModal] = useState<{
    open: boolean
    user?: User
  }>({ open: false })
  const [selectedUserGroup, setSelectedUserGroup] = useState<string>('')

  // Permission state
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false)
  const [isManageModalOpen, setIsManageModalOpen] = useState(false)
  const [isAssignModalOpen, setIsAssignModalOpen] = useState(false)
  const [selectedGroup, setSelectedGroup] = useState<PermissionGroup | null>(null)
  const [newGroupName, setNewGroupName] = useState('')
  const [selectedPermission, setSelectedPermission] = useState<string>('')
  const [selectedUser, setSelectedUser] = useState<string>('')

  // Common hooks
  const { data: dropdownData } = useDropdownData()
  
  // User hooks
  const { data: users = [], isLoading: usersLoading } = useUsers()
  const createUserMutation = useCreateUser()
  const deactivateUserMutation = useDeactivateUser()
  const assignUserPermissionsMutation = useAssignUserPermissions()

  // Permission hooks
  const { data: permissionGroups = [], isLoading: permissionsLoading } = usePermissionGroupsQuery()
  const { data: groupDetails } = usePermissionGroupDetails(selectedGroup?.permissionGroupName || '')
  const createGroupMutation = useCreatePermissionGroup()
  const deleteGroupMutation = useDeletePermissionGroup()
  const addPermissionMutation = useAddPermissionToGroup()
  const removePermissionMutation = useRemovePermissionFromGroup()
  const assignUserMutation = useAssignUserToGroup()

  // User form
  const userForm = useForm<CreateUserForm>({
    resolver: zodResolver(createUserSchema),
    defaultValues: {
      newUserEmail: '',
      newUserPassword: '',
    },
  })

  // User handlers
  const handleCreateUser = async (data: CreateUserForm) => {
    try {
      await createUserMutation.mutateAsync({
        email: data.newUserEmail,
        password: data.newUserPassword,
      })
      setIsCreateUserModalOpen(false)
      userForm.reset()
    } catch (error) {
      // Error handled by mutation
    }
  }

  const handleDeactivateUser = async (userEmail: string) => {
    try {
      await deactivateUserMutation.mutateAsync(userEmail)
    } catch (error) {
      // Error handled by mutation
    }
  }

  const handleAssignUserPermissions = async () => {
    if (!assignPermissionModal.user || !selectedUserGroup) return

    try {
      await assignUserPermissionsMutation.mutateAsync({
        userEmail: assignPermissionModal.user.userEmail,
        permissionGroupName: selectedUserGroup,
      })
      setAssignPermissionModal({ open: false })
      setSelectedUserGroup('')
    } catch (error) {
      // Error handled by mutation
    }
  }

  // Permission handlers
  const handleCreateGroup = async () => {
    if (!newGroupName.trim()) {
      toast.error('Please enter a group name')
      return
    }

    try {
      await createGroupMutation.mutateAsync({ permissionGroupName: newGroupName })
      setIsCreateModalOpen(false)
      setNewGroupName('')
    } catch (error) {
      // Error handled by mutation
    }
  }

  const handleDeleteGroup = async (groupName: string) => {
    try {
      await deleteGroupMutation.mutateAsync(groupName)
    } catch (error) {
      // Error handled by mutation
    }
  }

  const handleAddPermission = async () => {
    if (!selectedGroup || !selectedPermission) return

    try {
      await addPermissionMutation.mutateAsync({
        permissionGroupName: selectedGroup.permissionGroupName,
        permissionName: selectedPermission,
      })
      setSelectedPermission('')
    } catch (error) {
      // Error handled by mutation
    }
  }

  const handleRemovePermission = async (permission: string) => {
    if (!selectedGroup) return

    try {
      await removePermissionMutation.mutateAsync({
        permissionGroupName: selectedGroup.permissionGroupName,
        permissionName: permission,
      })
    } catch (error) {
      // Error handled by mutation
    }
  }

  const handleAssignUser = async () => {
    if (!selectedGroup || !selectedUser) return

    try {
      await assignUserMutation.mutateAsync({
        userEmail: selectedUser,
        permissionGroupName: selectedGroup.permissionGroupName,
      })
      setIsAssignModalOpen(false)
      setSelectedUser('')
    } catch (error) {
      // Error handled by mutation
    }
  }

  // Permission columns
  const permissionColumns = [
    {
      title: 'Group Name',
      dataIndex: 'permissionGroupName',
      key: 'permissionGroupName',
      render: (text: string) => (
        <Space>
          <SafetyOutlined style={{ color: '#556b2f' }} />
          <strong>{text}</strong>
        </Space>
      ),
    },
    {
      title: 'Users',
      dataIndex: 'userCount',
      key: 'userCount',
      width: 100,
      render: (count: number) => (
        <Badge count={count} showZero>
          <UserOutlined style={{ fontSize: 16 }} />
        </Badge>
      ),
    },
    {
      title: 'Permissions',
      dataIndex: 'permissionCount',
      key: 'permissionCount',
      width: 120,
      render: (count: number) => (
        <Badge count={count} showZero style={{ backgroundColor: '#556b2f' }}>
          <KeyOutlined style={{ fontSize: 16 }} />
        </Badge>
      ),
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 250,
      render: (_: any, record: PermissionGroup) => (
        <Space>
          <Button
            type="link"
            icon={<KeyOutlined />}
            onClick={() => {
              setSelectedGroup(record)
              setIsManageModalOpen(true)
            }}
          >
            Permissions
          </Button>
          <Button
            type="link"
            icon={<UserOutlined />}
            onClick={() => {
              setSelectedGroup(record)
              setIsAssignModalOpen(true)
            }}
          >
            Assign User
          </Button>
          <Popconfirm
            title="Delete Permission Group"
            description={`Are you sure you want to delete group "${record.permissionGroupName}"?`}
            onConfirm={() => handleDeleteGroup(record.permissionGroupName)}
            okText="Yes"
            cancelText="No"
            okButtonProps={{ danger: true }}
          >
            <Button 
              type="link" 
              danger 
              icon={<DeleteOutlined />}
              loading={deleteGroupMutation.isPending}
            >
              Delete
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  // User columns
  const userColumns = [
    {
      title: 'Email',
      dataIndex: 'userEmail',
      key: 'userEmail',
      render: (email: string) => (
        <Space>
          <UserOutlined style={{ color: '#556b2f' }} />
          <strong>{email}</strong>
        </Space>
      ),
    },
    {
      title: 'Status',
      dataIndex: 'activated',
      key: 'activated',
      width: 120,
      render: (activated: boolean) => (
        activated ? (
          <Tag icon={<CheckCircleOutlined />} color="success">Active</Tag>
        ) : (
          <Tag icon={<StopOutlined />} color="default">Inactive</Tag>
        )
      ),
    },
    {
      title: 'Permission Group',
      dataIndex: 'permissionGroupName',
      key: 'permissionGroupName',
      render: (group: string) => group ? (
        <Tag icon={<SafetyOutlined />} color="blue">{group}</Tag>
      ) : (
        <Tag color="default">No Group</Tag>
      ),
    },
    {
      title: 'Last Active',
      dataIndex: 'lastActive',
      key: 'lastActive',
      render: (date: string) => date ? new Date(date).toLocaleDateString() : 'Never',
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 250,
      render: (_: any, record: User) => (
        <Space>
          <Button
            type="link"
            icon={<SafetyOutlined />}
            onClick={() => {
              setAssignPermissionModal({ open: true, user: record })
              setSelectedUserGroup(record.permissionGroupName || '')
            }}
          >
            Permissions
          </Button>
          {record.activated && (
            <Popconfirm
              title="Deactivate User"
              description={`Are you sure you want to deactivate "${record.userEmail}"?`}
              onConfirm={() => handleDeactivateUser(record.userEmail)}
              okText="Yes"
              cancelText="No"
              okButtonProps={{ danger: true }}
            >
              <Button 
                type="link" 
                danger
                loading={deactivateUserMutation.isPending}
              >
                Deactivate
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  // Group permissions by category
  const permissionsByCategory = AVAILABLE_PERMISSIONS.reduce((acc, perm) => {
    if (!acc[perm.category]) acc[perm.category] = []
    acc[perm.category].push(perm)
    return acc
  }, {} as Record<string, typeof AVAILABLE_PERMISSIONS>)

  const userFormFields = [
    {
      name: 'newUserEmail',
      label: 'Email',
      type: 'email' as const,
      placeholder: 'user@example.com',
      required: true,
    },
    {
      name: 'newUserPassword',
      label: 'Password',
      type: 'password' as const,
      placeholder: 'Enter password',
      required: true,
    },
  ]

  const tabItems = [
    {
      key: 'permissions',
      label: (
        <span>
          <SafetyOutlined />
          Permissions
        </span>
      ),
      children: (
        <ResourceListView
          title={
            <Space>
              <span style={{ fontSize: 16, fontWeight: 500 }}>Permission Groups</span>
              <span style={{ fontSize: 14, color: '#666' }}>Manage permission groups and their assignments</span>
            </Space>
          }
          loading={permissionsLoading}
          data={permissionGroups}
          columns={permissionColumns}
          rowKey="permissionGroupName"
          searchPlaceholder="Search permission groups..."
          actions={
            <Button 
              type="primary" 
              icon={<PlusOutlined />}
              onClick={() => setIsCreateModalOpen(true)}
            >
              Create Group
            </Button>
          }
        />
      ),
    },
    {
      key: 'users',
      label: (
        <span>
          <UserOutlined />
          Users
        </span>
      ),
      children: (
        <ResourceListView
          title={
            <Space>
              <span style={{ fontSize: 16, fontWeight: 500 }}>Users</span>
              <span style={{ fontSize: 14, color: '#666' }}>Manage users and their permissions</span>
            </Space>
          }
          loading={usersLoading}
          data={users}
          columns={userColumns}
          rowKey="userEmail"
          searchPlaceholder="Search users..."
          actions={
            <Button 
              type="primary" 
              icon={<PlusOutlined />}
              onClick={() => setIsCreateUserModalOpen(true)}
            >
              Create User
            </Button>
          }
        />
      ),
    },
  ]

  return (
    <>
      <Card>
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={tabItems}
        />
      </Card>

      {/* Permission Modals */}
      <Modal
        title="Create Permission Group"
        open={isCreateModalOpen}
        onCancel={() => {
          setIsCreateModalOpen(false)
          setNewGroupName('')
        }}
        onOk={handleCreateGroup}
        confirmLoading={createGroupMutation.isPending}
      >
        <Input
          placeholder="Enter group name"
          value={newGroupName}
          onChange={(e) => setNewGroupName(e.target.value)}
          onPressEnter={handleCreateGroup}
        />
      </Modal>

      <Modal
        title={`Manage Permissions - ${selectedGroup?.permissionGroupName}`}
        open={isManageModalOpen}
        onCancel={() => {
          setIsManageModalOpen(false)
          setSelectedGroup(null)
          setSelectedPermission('')
        }}
        footer={null}
        width={800}
      >
        <Tabs
          items={[
            {
              key: 'current',
              label: 'Current Permissions',
              children: (
                <Card>
                  <List
                    dataSource={groupDetails?.permissions || []}
                    renderItem={(permission: string) => (
                      <List.Item
                        actions={[
                          <Button
                            type="link"
                            danger
                            size="small"
                            onClick={() => handleRemovePermission(permission)}
                            loading={removePermissionMutation.isPending}
                          >
                            Remove
                          </Button>
                        ]}
                      >
                        <List.Item.Meta
                          avatar={<KeyOutlined />}
                          title={permission}
                          description={AVAILABLE_PERMISSIONS.find(p => p.name === permission)?.description}
                        />
                      </List.Item>
                    )}
                    locale={{ emptyText: 'No permissions assigned' }}
                  />
                </Card>
              ),
            },
            {
              key: 'add',
              label: 'Add Permissions',
              children: (
                <Space direction="vertical" style={{ width: '100%' }} size={16}>
                  <Space style={{ width: '100%' }}>
                    <Select
                      placeholder="Select permission to add"
                      style={{ width: 400 }}
                      value={selectedPermission}
                      onChange={setSelectedPermission}
                      showSearch
                      filterOption={(input, option) =>
                        (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
                      }
                    >
                      {Object.entries(permissionsByCategory).map(([category, perms]) => (
                        <Select.OptGroup key={category} label={category}>
                          {perms.map(perm => (
                            <Select.Option 
                              key={perm.name} 
                              value={perm.name}
                              label={perm.name}
                              disabled={groupDetails?.permissions?.includes(perm.name)}
                            >
                              <div>
                                <div>{perm.name}</div>
                                <Text type="secondary" style={{ fontSize: 12 }}>
                                  {perm.description}
                                </Text>
                              </div>
                            </Select.Option>
                          ))}
                        </Select.OptGroup>
                      ))}
                    </Select>
                    <Button
                      type="primary"
                      onClick={handleAddPermission}
                      loading={addPermissionMutation.isPending}
                      disabled={!selectedPermission}
                    >
                      Add Permission
                    </Button>
                  </Space>
                </Space>
              ),
            },
          ]}
        />
      </Modal>

      <Modal
        title={`Assign User to ${selectedGroup?.permissionGroupName}`}
        open={isAssignModalOpen}
        onCancel={() => {
          setIsAssignModalOpen(false)
          setSelectedGroup(null)
          setSelectedUser('')
        }}
        onOk={handleAssignUser}
        confirmLoading={assignUserMutation.isPending}
      >
        <Select
          placeholder="Select user"
          style={{ width: '100%' }}
          value={selectedUser}
          onChange={setSelectedUser}
          showSearch
          filterOption={(input, option) =>
            (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
          }
          options={dropdownData?.users?.map(u => ({ 
            value: u.value, 
            label: u.label,
            disabled: u.status !== 'active'
          })) || []}
        />
      </Modal>

      {/* User Modals */}
      <Modal
        title="Create User"
        open={isCreateUserModalOpen}
        onCancel={() => {
          setIsCreateUserModalOpen(false)
          userForm.reset()
        }}
        footer={null}
      >
        <ResourceForm
          form={userForm}
          fields={userFormFields}
          onSubmit={handleCreateUser}
          submitText="Create"
          cancelText="Cancel"
          onCancel={() => {
            setIsCreateUserModalOpen(false)
            userForm.reset()
          }}
          loading={createUserMutation.isPending}
        />
      </Modal>

      <Modal
        title={`Assign Permissions - ${assignPermissionModal.user?.userEmail}`}
        open={assignPermissionModal.open}
        onCancel={() => {
          setAssignPermissionModal({ open: false })
          setSelectedUserGroup('')
        }}
        onOk={handleAssignUserPermissions}
        okText="Assign"
        confirmLoading={assignUserPermissionsMutation.isPending}
      >
        <Form layout="vertical">
          <Form.Item label="Permission Group">
            <Select
              value={selectedUserGroup}
              onChange={setSelectedUserGroup}
              placeholder="Select permission group"
              options={permissionGroups?.map(group => ({
                value: group.permissionGroupName,
                label: `${group.permissionGroupName} (${group.userCount} users, ${group.permissionCount} permissions)`,
              }))}
              allowClear
            />
          </Form.Item>
        </Form>
      </Modal>
    </>
  )
}

export default UsersAndPermissionsPage