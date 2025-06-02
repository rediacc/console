import React, { useState } from 'react'
import { Typography, Button, Space, Modal, Popconfirm, Tag, List, Card, Input, Select, Badge, Tabs } from 'antd'
import { 
  PlusOutlined, 
  DeleteOutlined, 
  SafetyOutlined, 
  UserOutlined,
  KeyOutlined,
  TeamOutlined
} from '@ant-design/icons'
import ResourceListView from '@/components/common/ResourceListView'
import { 
  usePermissionGroups, 
  usePermissionGroupDetails,
  useCreatePermissionGroup, 
  useDeletePermissionGroup,
  useAddPermissionToGroup,
  useRemovePermissionFromGroup,
  useAssignUserToGroup,
  PermissionGroup 
} from '@/api/queries/permissions'
import { useDropdownData } from '@/api/queries/useDropdownData'
import toast from 'react-hot-toast'

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

const PermissionsPage: React.FC = () => {
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false)
  const [isManageModalOpen, setIsManageModalOpen] = useState(false)
  const [isAssignModalOpen, setIsAssignModalOpen] = useState(false)
  const [selectedGroup, setSelectedGroup] = useState<PermissionGroup | null>(null)
  const [newGroupName, setNewGroupName] = useState('')
  const [selectedPermission, setSelectedPermission] = useState<string>('')
  const [selectedUser, setSelectedUser] = useState<string>('')

  const { data: dropdownData } = useDropdownData()
  const { data: permissionGroups, isLoading } = usePermissionGroups()
  const { data: groupDetails } = usePermissionGroupDetails(selectedGroup?.permissionGroupName || '')
  
  const createGroupMutation = useCreatePermissionGroup()
  const deleteGroupMutation = useDeletePermissionGroup()
  const addPermissionMutation = useAddPermissionToGroup()
  const removePermissionMutation = useRemovePermissionFromGroup()
  const assignUserMutation = useAssignUserToGroup()

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

  const columns = [
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

  // Group permissions by category
  const permissionsByCategory = AVAILABLE_PERMISSIONS.reduce((acc, perm) => {
    if (!acc[perm.category]) acc[perm.category] = []
    acc[perm.category].push(perm)
    return acc
  }, {} as Record<string, typeof AVAILABLE_PERMISSIONS>)

  return (
    <Space direction="vertical" size={24} style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Title level={3}>Permission Management</Title>
      </div>
      
      <ResourceListView
        title={<Title level={4} style={{ margin: 0 }}>Permission Groups</Title>}
        loading={isLoading}
        data={permissionGroups}
        columns={columns}
        rowKey="permissionGroupName"
        searchPlaceholder="Search permission groups..."
        actions={
          <Button 
            type="primary" 
            icon={<PlusOutlined />}
            onClick={() => setIsCreateModalOpen(true)}
            style={{ background: '#556b2f', borderColor: '#556b2f' }}
          >
            Create Group
          </Button>
        }
      />

      {/* Create Group Modal */}
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

      {/* Manage Permissions Modal */}
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
                      style={{ background: '#556b2f', borderColor: '#556b2f' }}
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

      {/* Assign User Modal */}
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
    </Space>
  )
}

export default PermissionsPage