import React, { useState } from 'react'
import { Typography, Button, Space, Modal, Form, Input, Popconfirm, Tag, Select } from 'antd'
import { PlusOutlined, UserOutlined, CheckCircleOutlined, StopOutlined, MailOutlined, SafetyOutlined } from '@ant-design/icons'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import ResourceListView from '@/components/common/ResourceListView'
import ResourceForm from '@/components/forms/ResourceForm'
import { useUsers, useCreateUser, useDeactivateUser, useAssignUserPermissions, User } from '@/api/queries/users'
import { usePermissionGroups } from '@/api/queries/users'
import { createUserSchema, CreateUserForm } from '@/utils/validation'

const { Title } = Typography

const UsersPage: React.FC = () => {
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false)
  const [assignPermissionModal, setAssignPermissionModal] = useState<{
    open: boolean
    user?: User
  }>({ open: false })
  const [selectedGroup, setSelectedGroup] = useState<string>('')

  const { data: users, isLoading } = useUsers()
  const { data: permissionGroups } = usePermissionGroups()
  const createUserMutation = useCreateUser()
  const deactivateUserMutation = useDeactivateUser()
  const assignPermissionsMutation = useAssignUserPermissions()

  const form = useForm<CreateUserForm>({
    resolver: zodResolver(createUserSchema),
    defaultValues: {
      newUserEmail: '',
      newUserPassword: '',
    },
  })

  const handleCreateUser = async (data: CreateUserForm) => {
    try {
      await createUserMutation.mutateAsync({
        email: data.newUserEmail,
        password: data.newUserPassword,
      })
      setIsCreateModalOpen(false)
      form.reset()
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

  const handleAssignPermissions = async () => {
    if (!assignPermissionModal.user || !selectedGroup) return

    try {
      await assignPermissionsMutation.mutateAsync({
        userEmail: assignPermissionModal.user.userEmail,
        permissionGroupName: selectedGroup,
      })
      setAssignPermissionModal({ open: false })
      setSelectedGroup('')
    } catch (error) {
      // Error handled by mutation
    }
  }

  const columns = [
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
              setSelectedGroup(record.permissionGroupName || '')
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

  const formFields = [
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

  return (
    <Space direction="vertical" size={24} style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Title level={3}>User Management</Title>
      </div>
      
      <ResourceListView
        title={<Title level={4} style={{ margin: 0 }}>Users</Title>}
        loading={isLoading}
        data={users}
        columns={columns}
        rowKey="userEmail"
        searchPlaceholder="Search users..."
        actions={
          <Button 
            type="primary" 
            icon={<PlusOutlined />}
            onClick={() => setIsCreateModalOpen(true)}
            style={{ background: '#556b2f', borderColor: '#556b2f' }}
          >
            Create User
          </Button>
        }
      />

      <Modal
        title="Create User"
        open={isCreateModalOpen}
        onCancel={() => {
          setIsCreateModalOpen(false)
          form.reset()
        }}
        footer={null}
      >
        <ResourceForm
          form={form}
          fields={formFields}
          onSubmit={handleCreateUser}
          submitText="Create"
          cancelText="Cancel"
          onCancel={() => {
            setIsCreateModalOpen(false)
            form.reset()
          }}
          loading={createUserMutation.isPending}
        />
      </Modal>

      <Modal
        title={`Assign Permissions - ${assignPermissionModal.user?.userEmail}`}
        open={assignPermissionModal.open}
        onCancel={() => {
          setAssignPermissionModal({ open: false })
          setSelectedGroup('')
        }}
        onOk={handleAssignPermissions}
        okText="Assign"
        confirmLoading={assignPermissionsMutation.isPending}
        okButtonProps={{
          style: { background: '#556b2f', borderColor: '#556b2f' }
        }}
      >
        <Form layout="vertical">
          <Form.Item label="Permission Group">
            <Select
              value={selectedGroup}
              onChange={setSelectedGroup}
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
    </Space>
  )
}

export default UsersPage