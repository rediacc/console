import React, { useState } from 'react'
import { Card, Tabs, Modal, Form, Input, Button, Space, Popconfirm, Tag, Select, Badge, List, Typography, Row, Col, Table, Empty, Spin } from 'antd'
import { 
  UserOutlined, 
  SafetyOutlined, 
  PlusOutlined, 
  DeleteOutlined,
  KeyOutlined,
  CheckCircleOutlined,
  StopOutlined,
  SettingOutlined,
  BankOutlined,
  EnvironmentOutlined,
  ApiOutlined,
  EditOutlined,
  DesktopOutlined
} from '@ant-design/icons'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useSelector } from 'react-redux'
import { RootState } from '@/store/store'
import { useTranslation } from 'react-i18next'
import ResourceListView from '@/components/common/ResourceListView'
import ResourceForm from '@/components/forms/ResourceForm'
import VaultEditorModal from '@/components/common/VaultEditorModal'
import { useDropdownData } from '@/api/queries/useDropdownData'
import { useUpdateCompanyVault, useCompanyVault } from '@/api/queries/company'
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

// Region queries
import { 
  useRegions, 
  useCreateRegion, 
  useUpdateRegionName,
  useDeleteRegion, 
  useUpdateRegionVault, 
  Region 
} from '@/api/queries/regions'

// Bridge queries
import { 
  useBridges, 
  useCreateBridge, 
  useUpdateBridgeName,
  useDeleteBridge, 
  useUpdateBridgeVault, 
  Bridge 
} from '@/api/queries/bridges'

import { 
  createUserSchema, 
  CreateUserForm,
  createRegionSchema, 
  CreateRegionForm,
  createBridgeSchema, 
  CreateBridgeForm,
  EditRegionForm,
  editBridgeSchema,
  EditBridgeForm
} from '@/utils/validation'

const { Title, Text } = Typography

const SystemPage: React.FC = () => {
  const { t } = useTranslation('settings')
  const { t: tUsers } = useTranslation('system')
  const { t: tOrg } = useTranslation('resources')
  const uiMode = useSelector((state: RootState) => state.ui.uiMode)
  const [activeTab, setActiveTab] = useState('users')
  
  // Set initial tab based on UI mode
  React.useEffect(() => {
    setActiveTab(uiMode === 'simple' ? 'users' : 'permissions')
  }, [uiMode])
  
  // Settings state
  const [companyVaultModalOpen, setCompanyVaultModalOpen] = useState(false)
  const [userVaultModalOpen, setUserVaultModalOpen] = useState(false)
  
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

  // Region state
  const [isCreateRegionModalOpen, setIsCreateRegionModalOpen] = useState(false)
  const [editingRegion, setEditingRegion] = useState<Region | null>(null)
  const [selectedRegion, setSelectedRegion] = useState<string | null>(null)
  const [regionVaultModalConfig, setRegionVaultModalConfig] = useState<{
    open: boolean
    region?: Region
  }>({ open: false })

  // Bridge state
  const [isCreateBridgeModalOpen, setIsCreateBridgeModalOpen] = useState(false)
  const [editingBridge, setEditingBridge] = useState<Bridge | null>(null)
  const [bridgeVaultModalConfig, setBridgeVaultModalConfig] = useState<{
    open: boolean
    bridge?: Bridge
  }>({ open: false })

  // Common hooks
  const { data: dropdownData } = useDropdownData()
  
  // Settings hooks
  const { data: companyVault } = useCompanyVault()
  const updateVaultMutation = useUpdateCompanyVault()
  
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

  // Region hooks - always fetch regions since they're always visible at the bottom
  const { data: regions, isLoading: regionsLoading } = useRegions(true)
  const regionsList: Region[] = regions || []
  const createRegionMutation = useCreateRegion()
  const updateRegionNameMutation = useUpdateRegionName()
  const deleteRegionMutation = useDeleteRegion()
  const updateRegionVaultMutation = useUpdateRegionVault()

  // Bridge hooks - fetch when a region is selected
  const { data: bridges, isLoading: bridgesLoading } = useBridges(selectedRegion || undefined)
  const bridgesList: Bridge[] = bridges || []
  const createBridgeMutation = useCreateBridge()
  const updateBridgeNameMutation = useUpdateBridgeName()
  const deleteBridgeMutation = useDeleteBridge()
  const updateBridgeVaultMutation = useUpdateBridgeVault()

  // User form
  const userForm = useForm<CreateUserForm>({
    resolver: zodResolver(createUserSchema),
    defaultValues: {
      newUserEmail: '',
      newUserPassword: '',
    },
  })

  // Region form
  const regionForm = useForm<CreateRegionForm>({
    resolver: zodResolver(createRegionSchema) as any,
    defaultValues: {
      regionName: '',
      regionVault: '{}',
    },
  })

  // Bridge forms
  const bridgeForm = useForm<CreateBridgeForm>({
    resolver: zodResolver(createBridgeSchema) as any,
    defaultValues: {
      regionName: '',
      bridgeName: '',
      bridgeVault: '{}',
    },
  })

  const editBridgeForm = useForm<EditBridgeForm>({
    resolver: zodResolver(editBridgeSchema) as any,
    defaultValues: {
      bridgeName: '',
    },
  })

  // Settings handlers
  const handleUpdateCompanyVault = async (vault: string, version: number) => {
    await updateVaultMutation.mutateAsync({
      companyVault: vault,
      vaultVersion: version,
    })
    setCompanyVaultModalOpen(false)
  }

  const handleUpdateUserVault = async (vault: string, version: number) => {
    // TODO: Implement user vault update when API is available
    console.log('User vault update:', { vault, version })
    setUserVaultModalOpen(false)
  }

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

  // Region handlers
  const handleCreateRegion = async (data: CreateRegionForm) => {
    try {
      await createRegionMutation.mutateAsync(data)
      setIsCreateRegionModalOpen(false)
      regionForm.reset()
    } catch (error) {
      // Error handled by mutation
    }
  }

  const handleEditRegion = async (values: EditRegionForm) => {
    if (!editingRegion) return
    try {
      await updateRegionNameMutation.mutateAsync({
        currentRegionName: editingRegion.regionName,
        newRegionName: values.regionName,
      })
      setEditingRegion(null)
      regionForm.reset()
    } catch (error) {
      // Error handled by mutation
    }
  }

  const handleDeleteRegion = async (regionName: string) => {
    try {
      await deleteRegionMutation.mutateAsync(regionName)
      if (selectedRegion === regionName) {
        setSelectedRegion(null)
      }
    } catch (error) {
      // Error handled by mutation
    }
  }

  const handleUpdateRegionVault = async (vault: string, version: number) => {
    if (!regionVaultModalConfig.region) return

    await updateRegionVaultMutation.mutateAsync({
      regionName: regionVaultModalConfig.region.regionName,
      regionVault: vault,
      vaultVersion: version,
    })
    setRegionVaultModalConfig({ open: false })
  }

  // Bridge handlers
  const handleCreateBridge = async (data: CreateBridgeForm) => {
    try {
      await createBridgeMutation.mutateAsync(data)
      setIsCreateBridgeModalOpen(false)
      bridgeForm.reset()
    } catch (error) {
      // Error handled by mutation
    }
  }

  const handleEditBridge = async (values: EditBridgeForm) => {
    if (!editingBridge) return
    try {
      await updateBridgeNameMutation.mutateAsync({
        regionName: editingBridge.regionName,
        currentBridgeName: editingBridge.bridgeName,
        newBridgeName: values.bridgeName,
      })
      setEditingBridge(null)
      editBridgeForm.reset()
    } catch (error) {
      // Error handled by mutation
    }
  }

  const handleDeleteBridge = async (bridge: Bridge) => {
    try {
      await deleteBridgeMutation.mutateAsync({
        regionName: bridge.regionName,
        bridgeName: bridge.bridgeName,
      })
    } catch (error) {
      // Error handled by mutation
    }
  }

  const handleUpdateBridgeVault = async (vault: string, version: number) => {
    if (!bridgeVaultModalConfig.bridge) return

    await updateBridgeVaultMutation.mutateAsync({
      regionName: bridgeVaultModalConfig.bridge.regionName,
      bridgeName: bridgeVaultModalConfig.bridge.bridgeName,
      bridgeVault: vault,
      vaultVersion: version,
    })
    setBridgeVaultModalConfig({ open: false })
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

  // Get available permissions from dropdown data
  const availablePermissions = dropdownData?.permissions || []

  // Region columns
  const regionColumns = [
    {
      title: tOrg('regions.regionName'),
      dataIndex: 'regionName',
      key: 'regionName',
      render: (text: string) => (
        <Space>
          <EnvironmentOutlined style={{ color: '#556b2f' }} />
          <strong>{text}</strong>
        </Space>
      ),
    },
    {
      title: tOrg('regions.bridges'),
      dataIndex: 'bridgeCount',
      key: 'bridgeCount',
      width: 120,
      render: (count: number) => (
        <Space>
          <ApiOutlined />
          <span>{count}</span>
        </Space>
      ),
    },
    ...(uiMode === 'expert' ? [{
      title: tOrg('general.vaultVersion'),
      dataIndex: 'vaultVersion',
      key: 'vaultVersion',
      width: 120,
      render: (version: number) => <Tag>{t('common:general.versionFormat', { version })}</Tag>,
    }] : []),
    {
      title: tOrg('general.actions'),
      key: 'actions',
      width: 200,
      render: (_: any, record: Region) => (
        <Space>
          <Button
            type="link"
            icon={<SettingOutlined />}
            onClick={() => setRegionVaultModalConfig({ open: true, region: record })}
          >
            {tOrg('general.vault')}
          </Button>
          <Button 
            type="link" 
            icon={<EditOutlined />}
            onClick={() => {
              setEditingRegion(record)
              regionForm.setValue('regionName', record.regionName)
            }}
          >
            {tOrg('general.edit')}
          </Button>
          <Popconfirm
            title={tOrg('regions.deleteRegion')}
            description={tOrg('regions.confirmDelete', { regionName: record.regionName })}
            onConfirm={() => handleDeleteRegion(record.regionName)}
            okText={tOrg('general.yes')}
            cancelText={tOrg('general.no')}
            okButtonProps={{ danger: true }}
          >
            <Button 
              type="link" 
              danger 
              icon={<DeleteOutlined />}
              loading={deleteRegionMutation.isPending}
            >
              {tOrg('general.delete')}
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  // Bridge columns
  const bridgeColumns = [
    {
      title: tOrg('bridges.bridgeName'),
      dataIndex: 'bridgeName',
      key: 'bridgeName',
      render: (text: string) => (
        <Space>
          <ApiOutlined style={{ color: '#556b2f' }} />
          <strong>{text}</strong>
        </Space>
      ),
    },
    {
      title: tOrg('teams.machines'),
      dataIndex: 'machineCount',
      key: 'machineCount',
      width: 120,
      render: (count: number) => (
        <Space>
          <DesktopOutlined />
          <span>{count}</span>
        </Space>
      ),
    },
    ...(uiMode === 'expert' ? [{
      title: tOrg('general.vaultVersion'),
      dataIndex: 'vaultVersion',
      key: 'vaultVersion',
      width: 120,
      render: (version: number) => <Tag>{t('common:general.versionFormat', { version })}</Tag>,
    }] : []),
    {
      title: tOrg('general.actions'),
      key: 'actions',
      width: 200,
      render: (_: any, record: Bridge) => (
        <Space>
          <Button
            type="link"
            icon={<SettingOutlined />}
            onClick={() => setBridgeVaultModalConfig({ open: true, bridge: record })}
          >
            {tOrg('general.vault')}
          </Button>
          <Button 
            type="link" 
            icon={<EditOutlined />}
            onClick={() => {
              setEditingBridge(record)
              editBridgeForm.setValue('bridgeName', record.bridgeName)
            }}
          >
            {tOrg('general.edit')}
          </Button>
          <Popconfirm
            title={tOrg('bridges.deleteBridge')}
            description={tOrg('bridges.confirmDelete', { bridgeName: record.bridgeName })}
            onConfirm={() => handleDeleteBridge(record)}
            okText={tOrg('general.yes')}
            cancelText={tOrg('general.no')}
            okButtonProps={{ danger: true }}
          >
            <Button 
              type="link" 
              danger 
              icon={<DeleteOutlined />}
              loading={deleteBridgeMutation.isPending}
            >
              {tOrg('general.delete')}
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

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

  // Form fields
  const regionFormFields = [
    {
      name: 'regionName',
      label: tOrg('regions.regionName'),
      placeholder: tOrg('regions.placeholders.enterRegionName'),
      required: true,
    },
  ]

  const bridgeFormFields = uiMode === 'simple'
    ? [
        {
          name: 'bridgeName',
          label: tOrg('bridges.bridgeName'),
          placeholder: tOrg('bridges.placeholders.enterBridgeName'),
          required: true,
        },
      ]
    : [
        {
          name: 'regionName',
          label: tOrg('general.region'),
          placeholder: tOrg('regions.placeholders.selectRegion'),
          required: true,
          type: 'select' as const,
          options: dropdownData?.regions?.map((r: any) => ({ value: r.value, label: r.label })) || [],
        },
        {
          name: 'bridgeName',
          label: tOrg('bridges.bridgeName'),
          placeholder: tOrg('bridges.placeholders.enterBridgeName'),
          required: true,
        },
      ]

  // Define tab configurations
  const usersTab = {
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
  }

  const permissionsTab = {
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
  }

  // Compose tabs based on UI mode
  const tabItems = uiMode === 'simple' 
    ? [usersTab]
    : [usersTab, permissionsTab]

  return (
    <>
      {/* Settings Section */}
      <Space direction="vertical" size={24} style={{ width: '100%', marginBottom: 24 }}>
        <Title level={3}>{t('title')}</Title>

        <Row gutter={[16, 16]}>
          {/* Company Settings Card */}
          <Col xs={24} lg={12}>
            <Card style={{ height: '100%' }}>
              <Space direction="vertical" size={16} style={{ width: '100%' }}>
                <Space>
                  <BankOutlined style={{ fontSize: 24, color: '#556b2f' }} />
                  <Title level={4} style={{ margin: 0 }}>{t('company.title')}</Title>
                </Space>
                
                <Text type="secondary">
                  {t('company.description')}
                </Text>

                <Button
                  type="primary"
                  icon={<SettingOutlined />}
                  onClick={() => setCompanyVaultModalOpen(true)}
                  size="large"
                  style={{ marginTop: 16 }}
                >
                  {t('company.configureVault')}
                </Button>
              </Space>
            </Card>
          </Col>

          {/* User Settings Card */}
          <Col xs={24} lg={12}>
            <Card style={{ height: '100%' }}>
              <Space direction="vertical" size={16} style={{ width: '100%' }}>
                <Space>
                  <UserOutlined style={{ fontSize: 24, color: '#556b2f' }} />
                  <Title level={4} style={{ margin: 0 }}>{t('personal.title')}</Title>
                </Space>
                
                <Text type="secondary">
                  {t('personal.description')}
                </Text>

                <Button
                  type="primary"
                  icon={<SettingOutlined />}
                  onClick={() => setUserVaultModalOpen(true)}
                  size="large"
                  style={{ marginTop: 16 }}
                >
                  {t('personal.configureVault')}
                </Button>
              </Space>
            </Card>
          </Col>
        </Row>
      </Space>

      {/* New Title Between Settings and Users */}
      <Title level={3} style={{ marginBottom: 24 }}>{tUsers('title')}</Title>

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

      {/* Company Vault Modal */}
      <VaultEditorModal
        open={companyVaultModalOpen}
        onCancel={() => setCompanyVaultModalOpen(false)}
        onSave={handleUpdateCompanyVault}
        entityType="COMPANY"
        title={t('company.modalTitle')}
        initialVault={companyVault?.vault || '{}'}
        initialVersion={companyVault?.vaultVersion || 1}
        loading={updateVaultMutation.isPending}
      />

      {/* User Vault Modal */}
      <VaultEditorModal
        open={userVaultModalOpen}
        onCancel={() => setUserVaultModalOpen(false)}
        onSave={handleUpdateUserVault}
        entityType="USER"
        title={t('personal.modalTitle')}
        initialVault={'{}'}
        initialVersion={1}
        loading={false}
      />

      {/* Regions & Infrastructure Section */}
      {uiMode === 'expert' && (
        <>
          <Title level={3} style={{ marginTop: 48, marginBottom: 24 }}>{tUsers('regionsInfrastructure.title')}</Title>
          
          <Card>
        <Row gutter={[24, 24]}>
          <Col span={24}>
            <ResourceListView
              title={
                <Space>
                  <span style={{ fontSize: 16, fontWeight: 500 }}>{tOrg('regions.title')}</span>
                  <span style={{ fontSize: 14, color: '#666' }}>{tOrg('regions.selectRegionPrompt')}</span>
                </Space>
              }
              loading={regionsLoading}
              data={regionsList}
              columns={regionColumns}
              rowKey="regionName"
              searchPlaceholder={tOrg('regions.searchRegions')}
              actions={
                <Button 
                  type="primary" 
                  icon={<PlusOutlined />}
                  onClick={() => setIsCreateRegionModalOpen(true)}
                  style={{ background: '#556b2f', borderColor: '#556b2f' }}
                >
                  {tOrg('regions.createRegion')}
                </Button>
              }
              rowSelection={{
                type: 'radio',
                selectedRowKeys: selectedRegion ? [selectedRegion] : [],
                onChange: (selectedRowKeys: React.Key[]) => {
                  setSelectedRegion(selectedRowKeys[0] as string || null)
                },
              }}
              onRow={(record) => ({
                onClick: () => setSelectedRegion(record.regionName),
                className: selectedRegion === record.regionName ? 'selected-row' : '',
                style: { cursor: 'pointer' },
              })}
            />
          </Col>
          
          <Col span={24}>
            <Card>
              <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <Title level={4} style={{ margin: 0 }}>
                    {selectedRegion ? tOrg('regions.bridgesInRegion', { region: selectedRegion }) : tOrg('bridges.title')}
                  </Title>
                  {!selectedRegion && (
                    <Text type="secondary" style={{ fontSize: 14 }}>
                      {tOrg('regions.selectRegionToView')}
                    </Text>
                  )}
                </div>
                {selectedRegion && (
                  <Button 
                    type="primary" 
                    icon={<PlusOutlined />}
                    onClick={() => {
                      bridgeForm.setValue('regionName', selectedRegion)
                      setIsCreateBridgeModalOpen(true)
                    }}
                    style={{ background: '#556b2f', borderColor: '#556b2f' }}
                  >
                    {tOrg('bridges.createBridge')}
                  </Button>
                )}
              </div>
              
              {!selectedRegion ? (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={tOrg('regions.selectRegionPrompt')}
                  style={{ padding: '40px 0' }}
                />
              ) : bridgesLoading ? (
                <div style={{ textAlign: 'center', padding: '100px 0' }}>
                  <Spin size="large" tip={t('common:general.loading')} />
                </div>
              ) : (
                <Table
                  columns={bridgeColumns}
                  dataSource={bridgesList}
                  rowKey="bridgeName"
                  pagination={{
                    total: bridgesList.length || 0,
                    pageSize: 10,
                    showSizeChanger: true,
                    showTotal: (total) => tOrg('bridges.totalBridges', { total }),
                  }}
                  locale={{
                    emptyText: tOrg('bridges.noBridges'),
                  }}
                />
              )}
            </Card>
          </Col>
        </Row>
      </Card>
        </>
      )}

      {/* Region Modals */}
      <Modal
        title={tOrg('regions.createRegion')}
        open={isCreateRegionModalOpen}
        onCancel={() => {
          setIsCreateRegionModalOpen(false)
          regionForm.reset()
        }}
        footer={null}
      >
        <ResourceForm
          form={regionForm}
          fields={regionFormFields}
          onSubmit={handleCreateRegion}
          submitText={tOrg('general.create')}
          cancelText={tOrg('general.cancel')}
          onCancel={() => {
            setIsCreateRegionModalOpen(false)
            regionForm.reset()
          }}
          loading={createRegionMutation.isPending}
        />
      </Modal>

      <VaultEditorModal
        open={regionVaultModalConfig.open}
        onCancel={() => setRegionVaultModalConfig({ open: false })}
        onSave={handleUpdateRegionVault}
        entityType="REGION"
        title={tOrg('general.configureVault', { name: regionVaultModalConfig.region?.regionName || '' })}
        initialVault={regionVaultModalConfig.region?.vaultContent || "{}"}
        initialVersion={regionVaultModalConfig.region?.vaultVersion || 1}
        loading={updateRegionVaultMutation.isPending}
      />

      {/* Edit Region Modal */}
      <Modal
        title={tOrg('regions.editRegion')}
        open={!!editingRegion}
        onCancel={() => {
          setEditingRegion(null)
          regionForm.reset()
        }}
        footer={null}
      >
        <ResourceForm
          form={regionForm}
          fields={[{
            name: 'regionName',
            label: tOrg('regions.regionName'),
            placeholder: tOrg('regions.placeholders.enterRegionName'),
            required: true,
          }]}
          onSubmit={handleEditRegion}
          submitText={tOrg('general.save')}
          cancelText={tOrg('general.cancel')}
          onCancel={() => {
            setEditingRegion(null)
            regionForm.reset()
          }}
          loading={updateRegionNameMutation.isPending}
        />
      </Modal>

      {/* Bridge Modals */}
      <Modal
        title={tOrg('bridges.createBridge')}
        open={isCreateBridgeModalOpen}
        onCancel={() => {
          setIsCreateBridgeModalOpen(false)
          bridgeForm.reset()
        }}
        footer={null}
      >
        <ResourceForm
          form={bridgeForm}
          fields={bridgeFormFields}
          onSubmit={handleCreateBridge}
          submitText={tOrg('general.create')}
          cancelText={tOrg('general.cancel')}
          onCancel={() => {
            setIsCreateBridgeModalOpen(false)
            bridgeForm.reset()
          }}
          loading={createBridgeMutation.isPending}
        />
      </Modal>

      <VaultEditorModal
        open={bridgeVaultModalConfig.open}
        onCancel={() => setBridgeVaultModalConfig({ open: false })}
        onSave={handleUpdateBridgeVault}
        entityType="BRIDGE"
        title={tOrg('general.configureVault', { name: bridgeVaultModalConfig.bridge?.bridgeName || '' })}
        initialVault={bridgeVaultModalConfig.bridge?.vaultContent || "{}"}
        initialVersion={bridgeVaultModalConfig.bridge?.vaultVersion || 1}
        loading={updateBridgeVaultMutation.isPending}
      />

      {/* Edit Bridge Modal */}
      <Modal
        title={tOrg('bridges.editBridge')}
        open={!!editingBridge}
        onCancel={() => {
          setEditingBridge(null)
          editBridgeForm.reset()
        }}
        footer={null}
      >
        <ResourceForm
          form={editBridgeForm}
          fields={[{
            name: 'bridgeName',
            label: tOrg('bridges.bridgeName'),
            placeholder: tOrg('bridges.placeholders.enterBridgeName'),
            required: true,
          }]}
          onSubmit={handleEditBridge}
          submitText={tOrg('general.save')}
          cancelText={tOrg('general.cancel')}
          onCancel={() => {
            setEditingBridge(null)
            editBridgeForm.reset()
          }}
          loading={updateBridgeNameMutation.isPending}
        />
      </Modal>
    </>
  )
}

export default SystemPage