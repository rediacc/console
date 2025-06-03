import React, { useState } from 'react'
import { Typography, Button, Space, Modal, Popconfirm, List, Card, Input, Select, Badge, Tabs } from 'antd'
import { 
  PlusOutlined, 
  DeleteOutlined, 
  SafetyOutlined, 
  UserOutlined,
  KeyOutlined
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
      render: (_: any, record: PermissionGroup) => {
        // Check if this is a protected system group
        const isProtectedGroup = record.permissionGroupName === 'Administrators' || 
                                record.permissionGroupName === 'Machines'
        
        if (isProtectedGroup) {
          return (
            <Space>
              <Button
                type="link"
                icon={<KeyOutlined />}
                onClick={() => {
                  toast.error(`The ${record.permissionGroupName} group is a protected system group and cannot be modified`)
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
              <Button 
                type="link" 
                danger 
                icon={<DeleteOutlined />}
                disabled
                title={`The ${record.permissionGroupName} group is a protected system group and cannot be deleted`}
              >
                Delete
              </Button>
            </Space>
          )
        }
        
        return (
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
        )
      },
    },
  ]

  // Get available permissions from dropdown data
  const availablePermissions = dropdownData?.permissions || []

  return (
    <Space direction="vertical" size={24} style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Title level={3}>Permission Management</Title>
      </div>
      
      <ResourceListView
        title={<Title level={4} style={{ margin: 0 }}>Permission Groups</Title>}
        loading={isLoading}
        data={permissionGroups || []}
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
                      placeholder={availablePermissions.length > 0 ? "Select permission to add" : "No permissions available (admin access required)"}
                      style={{ width: 400 }}
                      value={selectedPermission}
                      onChange={setSelectedPermission}
                      showSearch
                      disabled={availablePermissions.length === 0}
                      filterOption={(input, option) =>
                        (String(option?.label ?? '')).toLowerCase().includes(input.toLowerCase())
                      }
                    >
                      {availablePermissions.map(perm => (
                        <Select.Option 
                          key={perm.name} 
                          value={perm.name}
                          label={perm.name}
                          disabled={groupDetails?.permissions?.includes(perm.name)}
                        >
                          {perm.name}
                        </Select.Option>
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
                  {availablePermissions.length === 0 && (
                    <Text type="secondary">
                      Note: Only administrators can view and manage permissions. 
                      If you need to manage permissions, please contact your system administrator.
                    </Text>
                  )}
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
            (String(option?.label ?? '')).toLowerCase().includes(input.toLowerCase())
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