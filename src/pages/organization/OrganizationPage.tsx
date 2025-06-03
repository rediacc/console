import React, { useState } from 'react'
import { Card, Tabs, Button, Space, Modal, Popconfirm, Tag, Typography, Form, Input, Table, Row, Col, Empty, Tooltip, Progress, Badge } from 'antd'
import { 
  TeamOutlined, 
  GlobalOutlined, 
  PlusOutlined, 
  EditOutlined, 
  DeleteOutlined, 
  UserOutlined,
  ApiOutlined,
  SettingOutlined,
  CloudServerOutlined,
  DatabaseOutlined,
  HddOutlined,
  ScheduleOutlined,
  InfoCircleOutlined,
  CheckCircleOutlined,
  StopOutlined,
  SyncOutlined,
  ThunderboltOutlined,
  FieldTimeOutlined,
  ClockCircleOutlined
} from '@ant-design/icons'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import ResourceListView from '@/components/common/ResourceListView'
import ResourceForm from '@/components/forms/ResourceForm'
import VaultConfigModal from '@/components/common/VaultConfigModal'

// Team queries
import { useTeams, useCreateTeam, useDeleteTeam, Team } from '@/api/queries/teams'

// Region queries
import { 
  useRegions, 
  useCreateRegion, 
  useDeleteRegion, 
  useUpdateRegionVault, 
  Region 
} from '@/api/queries/regions'

// Bridge queries
import { 
  useBridges, 
  useCreateBridge, 
  useDeleteBridge, 
  useUpdateBridgeVault, 
  Bridge 
} from '@/api/queries/bridges'

// Machine queries
import { 
  useMachines, 
  useCreateMachine, 
  useDeleteMachine, 
  useUpdateMachineVault, 
  Machine 
} from '@/api/queries/machines'

// Repository queries
import { 
  useRepositories, 
  useCreateRepository, 
  useDeleteRepository, 
  useUpdateRepositoryVault, 
  Repository 
} from '@/api/queries/repositories'

// Storage queries
import { 
  useStorage, 
  useCreateStorage, 
  useDeleteStorage, 
  useUpdateStorageVault, 
  Storage 
} from '@/api/queries/storage'

// Schedule queries
import { 
  useSchedules, 
  useCreateSchedule, 
  useDeleteSchedule, 
  useUpdateScheduleVault, 
  Schedule 
} from '@/api/queries/schedules'

import { useDropdownData } from '@/api/queries/useDropdownData'
import { 
  createRegionSchema, 
  CreateRegionForm, 
  createBridgeSchema, 
  CreateBridgeForm,
  createMachineSchema,
  CreateMachineForm,
  createRepositorySchema,
  CreateRepositoryForm,
  createStorageSchema,
  CreateStorageForm,
  createScheduleSchema,
  CreateScheduleForm
} from '@/utils/validation'

const { Title, Text } = Typography
const { TabPane } = Tabs

const OrganizationPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState('teams')
  const [selectedTeam, setSelectedTeam] = useState<string | null>(null)
  const [teamResourcesTab, setTeamResourcesTab] = useState('machines')
  
  // Team state
  const [isCreateTeamModalOpen, setIsCreateTeamModalOpen] = useState(false)
  const [teamForm] = Form.useForm()
  
  // Region state
  const [isCreateRegionModalOpen, setIsCreateRegionModalOpen] = useState(false)
  const [selectedRegion, setSelectedRegion] = useState<string | null>(null)
  const [regionVaultModalConfig, setRegionVaultModalConfig] = useState<{
    open: boolean
    region?: Region
  }>({ open: false })

  // Bridge state
  const [isCreateBridgeModalOpen, setIsCreateBridgeModalOpen] = useState(false)
  const [bridgeVaultModalConfig, setBridgeVaultModalConfig] = useState<{
    open: boolean
    bridge?: Bridge
  }>({ open: false })

  // Machine state
  const [isCreateMachineModalOpen, setIsCreateMachineModalOpen] = useState(false)
  const [machineVaultModalConfig, setMachineVaultModalConfig] = useState<{
    open: boolean
    machine?: Machine
  }>({ open: false })

  // Repository state
  const [isCreateRepositoryModalOpen, setIsCreateRepositoryModalOpen] = useState(false)
  const [repositoryVaultModalConfig, setRepositoryVaultModalConfig] = useState<{
    open: boolean
    repository?: Repository
  }>({ open: false })

  // Storage state
  const [isCreateStorageModalOpen, setIsCreateStorageModalOpen] = useState(false)
  const [storageVaultModalConfig, setStorageVaultModalConfig] = useState<{
    open: boolean
    storage?: Storage
  }>({ open: false })

  // Schedule state
  const [isCreateScheduleModalOpen, setIsCreateScheduleModalOpen] = useState(false)
  const [scheduleVaultModalConfig, setScheduleVaultModalConfig] = useState<{
    open: boolean
    schedule?: Schedule
  }>({ open: false })

  // Common hooks
  const { data: dropdownData } = useDropdownData()

  // Team hooks
  const { data: teams = [], isLoading: teamsLoading } = useTeams()
  const createTeamMutation = useCreateTeam()
  const deleteTeamMutation = useDeleteTeam()

  // Region hooks
  const { data: regions = [], isLoading: regionsLoading } = useRegions()
  const createRegionMutation = useCreateRegion()
  const deleteRegionMutation = useDeleteRegion()
  const updateRegionVaultMutation = useUpdateRegionVault()

  // Bridge hooks
  const { data: bridges = [], isLoading: bridgesLoading } = useBridges(selectedRegion || undefined)
  const createBridgeMutation = useCreateBridge()
  const deleteBridgeMutation = useDeleteBridge()
  const updateBridgeVaultMutation = useUpdateBridgeVault()

  // Machine hooks
  const { data: machines = [], isLoading: machinesLoading } = useMachines(selectedTeam || undefined)
  const createMachineMutation = useCreateMachine()
  const deleteMachineMutation = useDeleteMachine()
  const updateMachineVaultMutation = useUpdateMachineVault()

  // Repository hooks
  const { data: repositories = [], isLoading: repositoriesLoading } = useRepositories(selectedTeam || undefined)
  const createRepositoryMutation = useCreateRepository()
  const deleteRepositoryMutation = useDeleteRepository()
  const updateRepositoryVaultMutation = useUpdateRepositoryVault()

  // Storage hooks
  const { data: storages = [], isLoading: storagesLoading } = useStorage(selectedTeam || undefined)
  const createStorageMutation = useCreateStorage()
  const deleteStorageMutation = useDeleteStorage()
  const updateStorageVaultMutation = useUpdateStorageVault()

  // Schedule hooks
  const { data: schedules = [], isLoading: schedulesLoading } = useSchedules(selectedTeam || undefined)
  const createScheduleMutation = useCreateSchedule()
  const deleteScheduleMutation = useDeleteSchedule()
  const updateScheduleVaultMutation = useUpdateScheduleVault()

  // Forms
  const regionForm = useForm<CreateRegionForm>({
    resolver: zodResolver(createRegionSchema) as any,
    defaultValues: {
      regionName: '',
      regionVault: '{}',
    },
  })

  const bridgeForm = useForm<CreateBridgeForm>({
    resolver: zodResolver(createBridgeSchema) as any,
    defaultValues: {
      regionName: '',
      bridgeName: '',
      bridgeVault: '{}',
    },
  })

  const machineForm = useForm<CreateMachineForm>({
    resolver: zodResolver(createMachineSchema) as any,
    defaultValues: {
      teamName: '',
      machineName: '',
      regionName: '',
      bridgeName: '',
      machineVault: '{}',
    },
  })

  const repositoryForm = useForm<CreateRepositoryForm>({
    resolver: zodResolver(createRepositorySchema) as any,
    defaultValues: {
      teamName: '',
      repositoryName: '',
      repositoryVault: '{}',
    },
  })

  const storageForm = useForm<CreateStorageForm>({
    resolver: zodResolver(createStorageSchema) as any,
    defaultValues: {
      teamName: '',
      storageName: '',
      storageVault: '{}',
    },
  })

  const scheduleForm = useForm<CreateScheduleForm>({
    resolver: zodResolver(createScheduleSchema) as any,
    defaultValues: {
      teamName: '',
      scheduleName: '',
      scheduleDescription: '',
      cronExpression: '',
      scheduleVault: '{}',
    },
  })

  // Team handlers
  const handleCreateTeam = async (values: { teamName: string }) => {
    try {
      await createTeamMutation.mutateAsync(values)
      setIsCreateTeamModalOpen(false)
      teamForm.resetFields()
    } catch (error) {
      // Error handled by mutation
    }
  }

  const handleDeleteTeam = async (teamName: string) => {
    try {
      await deleteTeamMutation.mutateAsync(teamName)
      if (selectedTeam === teamName) {
        setSelectedTeam(null)
      }
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

  // Machine handlers
  const handleCreateMachine = async (data: CreateMachineForm) => {
    try {
      // Extract only the fields needed by the API (exclude regionName)
      const { teamName, bridgeName, machineName, machineVault } = data
      await createMachineMutation.mutateAsync({
        teamName,
        bridgeName,
        machineName,
        machineVault
      })
      setIsCreateMachineModalOpen(false)
      machineForm.reset()
    } catch (error) {
      // Error handled by mutation
    }
  }

  const handleDeleteMachine = async (machine: Machine) => {
    try {
      await deleteMachineMutation.mutateAsync({
        teamName: machine.teamName,
        machineName: machine.machineName,
      })
    } catch (error) {
      // Error handled by mutation
    }
  }

  const handleUpdateMachineVault = async (vault: string, version: number) => {
    if (!machineVaultModalConfig.machine) return

    await updateMachineVaultMutation.mutateAsync({
      teamName: machineVaultModalConfig.machine.teamName,
      machineName: machineVaultModalConfig.machine.machineName,
      machineVault: vault,
      vaultVersion: version,
    })
    setMachineVaultModalConfig({ open: false })
  }

  // Repository handlers
  const handleCreateRepository = async (data: CreateRepositoryForm) => {
    try {
      await createRepositoryMutation.mutateAsync(data)
      setIsCreateRepositoryModalOpen(false)
      repositoryForm.reset()
    } catch (error) {
      // Error handled by mutation
    }
  }

  const handleDeleteRepository = async (repository: Repository) => {
    try {
      await deleteRepositoryMutation.mutateAsync({
        teamName: repository.teamName,
        repositoryName: repository.repositoryName,
      })
    } catch (error) {
      // Error handled by mutation
    }
  }

  const handleUpdateRepositoryVault = async (vault: string, version: number) => {
    if (!repositoryVaultModalConfig.repository) return

    await updateRepositoryVaultMutation.mutateAsync({
      teamName: repositoryVaultModalConfig.repository.teamName,
      repositoryName: repositoryVaultModalConfig.repository.repositoryName,
      repositoryVault: vault,
      vaultVersion: version,
    })
    setRepositoryVaultModalConfig({ open: false })
  }

  // Storage handlers
  const handleCreateStorage = async (data: CreateStorageForm) => {
    try {
      await createStorageMutation.mutateAsync(data)
      setIsCreateStorageModalOpen(false)
      storageForm.reset()
    } catch (error) {
      // Error handled by mutation
    }
  }

  const handleDeleteStorage = async (storage: Storage) => {
    try {
      await deleteStorageMutation.mutateAsync({
        teamName: storage.teamName,
        storageName: storage.storageName,
      })
    } catch (error) {
      // Error handled by mutation
    }
  }

  const handleUpdateStorageVault = async (vault: string, version: number) => {
    if (!storageVaultModalConfig.storage) return

    await updateStorageVaultMutation.mutateAsync({
      teamName: storageVaultModalConfig.storage.teamName,
      storageName: storageVaultModalConfig.storage.storageName,
      storageVault: vault,
      vaultVersion: version,
    })
    setStorageVaultModalConfig({ open: false })
  }

  // Schedule handlers
  const handleCreateSchedule = async (data: CreateScheduleForm) => {
    try {
      await createScheduleMutation.mutateAsync(data)
      setIsCreateScheduleModalOpen(false)
      scheduleForm.reset()
    } catch (error) {
      // Error handled by mutation
    }
  }

  const handleDeleteSchedule = async (schedule: Schedule) => {
    try {
      await deleteScheduleMutation.mutateAsync({
        teamName: schedule.teamName,
        scheduleName: schedule.scheduleName,
      })
    } catch (error) {
      // Error handled by mutation
    }
  }

  const handleUpdateScheduleVault = async (vault: string, version: number) => {
    if (!scheduleVaultModalConfig.schedule) return

    await updateScheduleVaultMutation.mutateAsync({
      teamName: scheduleVaultModalConfig.schedule.teamName,
      scheduleName: scheduleVaultModalConfig.schedule.scheduleName,
      scheduleVault: vault,
      vaultVersion: version,
    })
    setScheduleVaultModalConfig({ open: false })
  }

  // Team columns
  const teamColumns = [
    {
      title: 'Team Name',
      dataIndex: 'teamName',
      key: 'teamName',
      render: (text: string) => (
        <Space>
          <TeamOutlined style={{ color: '#556b2f' }} />
          <strong>{text}</strong>
        </Space>
      ),
    },
    {
      title: 'Members',
      dataIndex: 'memberCount',
      key: 'memberCount',
      width: 100,
      render: (count: number) => (
        <Space>
          <UserOutlined />
          {count}
        </Space>
      ),
    },
    {
      title: 'Machines',
      dataIndex: 'machineCount',
      key: 'machineCount',
      width: 100,
    },
    {
      title: 'Repositories',
      dataIndex: 'repoCount',
      key: 'repoCount',
      width: 120,
    },
    {
      title: 'Storage',
      dataIndex: 'storageCount',
      key: 'storageCount',
      width: 100,
    },
    {
      title: 'Schedules',
      dataIndex: 'scheduleCount',
      key: 'scheduleCount',
      width: 100,
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 150,
      render: (_: any, record: Team) => (
        <Space>
          <Button 
            type="link" 
            icon={<EditOutlined />}
            onClick={() => {
              // TODO: Implement edit functionality
            }}
          >
            Edit
          </Button>
          <Popconfirm
            title="Delete Team"
            description={`Are you sure you want to delete team "${record.teamName}"? This will remove all resources in the team.`}
            onConfirm={() => handleDeleteTeam(record.teamName)}
            okText="Yes"
            cancelText="No"
            okButtonProps={{ danger: true }}
          >
            <Button 
              type="link" 
              danger 
              icon={<DeleteOutlined />}
              loading={deleteTeamMutation.isPending}
            >
              Delete
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  // Region columns
  const regionColumns = [
    {
      title: 'Region Name',
      dataIndex: 'regionName',
      key: 'regionName',
      render: (text: string, record: Region) => (
        <Space>
          <GlobalOutlined style={{ color: '#556b2f' }} />
          <strong>{text}</strong>
        </Space>
      ),
    },
    {
      title: 'Bridges',
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
    {
      title: 'Vault Version',
      dataIndex: 'vaultVersion',
      key: 'vaultVersion',
      width: 120,
      render: (version: number) => <Tag>{`v${version}`}</Tag>,
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 200,
      render: (_: any, record: Region) => (
        <Space>
          <Button
            type="link"
            icon={<SettingOutlined />}
            onClick={() => setRegionVaultModalConfig({ open: true, region: record })}
          >
            Vault
          </Button>
          <Button 
            type="link" 
            icon={<EditOutlined />}
            onClick={() => {
              // TODO: Implement edit functionality
            }}
          >
            Edit
          </Button>
          <Popconfirm
            title="Delete Region"
            description={`Are you sure you want to delete region "${record.regionName}"? This will remove all bridges in the region.`}
            onConfirm={() => handleDeleteRegion(record.regionName)}
            okText="Yes"
            cancelText="No"
            okButtonProps={{ danger: true }}
          >
            <Button 
              type="link" 
              danger 
              icon={<DeleteOutlined />}
              loading={deleteRegionMutation.isPending}
            >
              Delete
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  // Bridge columns
  const bridgeColumns = [
    {
      title: 'Bridge Name',
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
      title: 'Machines',
      dataIndex: 'machineCount',
      key: 'machineCount',
      width: 120,
      render: (count: number) => (
        <Space>
          <CloudServerOutlined />
          <span>{count}</span>
        </Space>
      ),
    },
    {
      title: 'Vault Version',
      dataIndex: 'vaultVersion',
      key: 'vaultVersion',
      width: 120,
      render: (version: number) => <Tag>{`v${version}`}</Tag>,
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 200,
      render: (_: any, record: Bridge) => (
        <Space>
          <Button
            type="link"
            icon={<SettingOutlined />}
            onClick={() => setBridgeVaultModalConfig({ open: true, bridge: record })}
          >
            Vault
          </Button>
          <Button 
            type="link" 
            icon={<EditOutlined />}
            onClick={() => {
              // TODO: Implement edit functionality
            }}
          >
            Edit
          </Button>
          <Popconfirm
            title="Delete Bridge"
            description={`Are you sure you want to delete bridge "${record.bridgeName}"? This will affect all machines using this bridge.`}
            onConfirm={() => handleDeleteBridge(record)}
            okText="Yes"
            cancelText="No"
            okButtonProps={{ danger: true }}
          >
            <Button 
              type="link" 
              danger 
              icon={<DeleteOutlined />}
              loading={deleteBridgeMutation.isPending}
            >
              Delete
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  // Machine columns
  const machineColumns = [
    {
      title: 'Machine Name',
      dataIndex: 'machineName',
      key: 'machineName',
      render: (text: string) => (
        <Space>
          <CloudServerOutlined style={{ color: '#556b2f' }} />
          <strong>{text}</strong>
        </Space>
      ),
    },
    {
      title: 'Bridge',
      dataIndex: 'bridgeName',
      key: 'bridgeName',
      render: (bridge: string) => <Tag color="blue">{bridge}</Tag>,
    },
    {
      title: 'Queue Items',
      dataIndex: 'queueItemCount',
      key: 'queueItemCount',
      width: 120,
      render: (count: number) => (
        <Badge count={count} showZero style={{ backgroundColor: count > 0 ? '#52c41a' : '#d9d9d9' }} />
      ),
    },
    {
      title: 'Vault Version',
      dataIndex: 'vaultVersion',
      key: 'vaultVersion',
      width: 120,
      render: (version: number) => <Tag>{`v${version}`}</Tag>,
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 200,
      render: (_: any, record: Machine) => (
        <Space>
          <Button
            type="link"
            icon={<SettingOutlined />}
            onClick={() => setMachineVaultModalConfig({ open: true, machine: record })}
          >
            Vault
          </Button>
          <Button 
            type="link" 
            icon={<EditOutlined />}
            onClick={() => {
              // TODO: Implement edit functionality
            }}
          >
            Edit
          </Button>
          <Popconfirm
            title="Delete Machine"
            description={`Are you sure you want to delete machine "${record.machineName}"?`}
            onConfirm={() => handleDeleteMachine(record)}
            okText="Yes"
            cancelText="No"
            okButtonProps={{ danger: true }}
          >
            <Button 
              type="link" 
              danger 
              icon={<DeleteOutlined />}
              loading={deleteMachineMutation.isPending}
            >
              Delete
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  // Repository columns
  const repositoryColumns = [
    {
      title: 'Repository Name',
      dataIndex: 'repositoryName',
      key: 'repositoryName',
      render: (text: string) => (
        <Space>
          <DatabaseOutlined style={{ color: '#556b2f' }} />
          <strong>{text}</strong>
        </Space>
      ),
    },
    {
      title: 'Size',
      dataIndex: 'size',
      key: 'size',
      width: 100,
      render: (size: number) => `${(size / (1024 * 1024)).toFixed(2)} MB`,
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (status: string) => {
        const color = status === 'active' ? 'success' : status === 'syncing' ? 'processing' : 'default'
        const icon = status === 'active' ? <CheckCircleOutlined /> : status === 'syncing' ? <SyncOutlined spin /> : <StopOutlined />
        return <Tag icon={icon} color={color}>{status}</Tag>
      },
    },
    {
      title: 'Vault Version',
      dataIndex: 'vaultVersion',
      key: 'vaultVersion',
      width: 120,
      render: (version: number) => <Tag>{`v${version}`}</Tag>,
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 200,
      render: (_: any, record: Repository) => (
        <Space>
          <Button
            type="link"
            icon={<SettingOutlined />}
            onClick={() => setRepositoryVaultModalConfig({ open: true, repository: record })}
          >
            Vault
          </Button>
          <Button 
            type="link" 
            icon={<EditOutlined />}
            onClick={() => {
              // TODO: Implement edit functionality
            }}
          >
            Edit
          </Button>
          <Popconfirm
            title="Delete Repository"
            description={`Are you sure you want to delete repository "${record.repositoryName}"?`}
            onConfirm={() => handleDeleteRepository(record)}
            okText="Yes"
            cancelText="No"
            okButtonProps={{ danger: true }}
          >
            <Button 
              type="link" 
              danger 
              icon={<DeleteOutlined />}
              loading={deleteRepositoryMutation.isPending}
            >
              Delete
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  // Storage columns
  const storageColumns = [
    {
      title: 'Storage Name',
      dataIndex: 'storageName',
      key: 'storageName',
      render: (text: string) => (
        <Space>
          <HddOutlined style={{ color: '#556b2f' }} />
          <strong>{text}</strong>
        </Space>
      ),
    },
    {
      title: 'Vault Version',
      dataIndex: 'vaultVersion',
      key: 'vaultVersion',
      width: 120,
      render: (version: number) => <Tag>{`v${version}`}</Tag>,
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 200,
      render: (_: any, record: Storage) => (
        <Space>
          <Button
            type="link"
            icon={<SettingOutlined />}
            onClick={() => setStorageVaultModalConfig({ open: true, storage: record })}
          >
            Vault
          </Button>
          <Button 
            type="link" 
            icon={<EditOutlined />}
            onClick={() => {
              // TODO: Implement edit functionality
            }}
          >
            Edit
          </Button>
          <Popconfirm
            title="Delete Storage"
            description={`Are you sure you want to delete storage "${record.storageName}"?`}
            onConfirm={() => handleDeleteStorage(record)}
            okText="Yes"
            cancelText="No"
            okButtonProps={{ danger: true }}
          >
            <Button 
              type="link" 
              danger 
              icon={<DeleteOutlined />}
              loading={deleteStorageMutation.isPending}
            >
              Delete
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  // Schedule columns
  const scheduleColumns = [
    {
      title: 'Schedule Name',
      dataIndex: 'scheduleName',
      key: 'scheduleName',
      render: (text: string, record: Schedule) => (
        <Space>
          <ScheduleOutlined style={{ color: '#556b2f' }} />
          <strong>{text}</strong>
          {record.scheduleDescription && (
            <Tooltip title={record.scheduleDescription}>
              <InfoCircleOutlined style={{ color: '#8c8c8c' }} />
            </Tooltip>
          )}
        </Space>
      ),
    },
    {
      title: 'Status',
      dataIndex: 'isActive',
      key: 'isActive',
      width: 100,
      render: (isActive: boolean) => (
        <Tag icon={isActive ? <CheckCircleOutlined /> : <StopOutlined />} color={isActive ? 'success' : 'default'}>
          {isActive ? 'Active' : 'Inactive'}
        </Tag>
      ),
    },
    {
      title: 'Cron',
      dataIndex: 'cronExpression',
      key: 'cronExpression',
      width: 150,
      render: (cron: string) => (
        <Tooltip title={`Cron expression: ${cron}`}>
          <Tag icon={<FieldTimeOutlined />}>{cron}</Tag>
        </Tooltip>
      ),
    },
    {
      title: 'Next Run',
      dataIndex: 'nextRun',
      key: 'nextRun',
      width: 180,
      render: (date: string) => (
        <Space>
          <ClockCircleOutlined />
          {date ? new Date(date).toLocaleString() : 'N/A'}
        </Space>
      ),
    },
    {
      title: 'Last Run',
      dataIndex: 'lastRun',
      key: 'lastRun',
      width: 180,
      render: (date: string) => date ? new Date(date).toLocaleString() : 'Never',
    },
    {
      title: 'Queue',
      dataIndex: 'queueCount',
      key: 'queueCount',
      width: 80,
      render: (count: number) => (
        <Badge count={count} showZero style={{ backgroundColor: count > 0 ? '#52c41a' : '#d9d9d9' }} />
      ),
    },
    {
      title: 'Vault',
      dataIndex: 'vaultVersion',
      key: 'vaultVersion',
      width: 80,
      render: (version: number) => <Tag>{`v${version}`}</Tag>,
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 200,
      render: (_: any, record: Schedule) => (
        <Space>
          <Button
            type="link"
            icon={<SettingOutlined />}
            onClick={() => setScheduleVaultModalConfig({ open: true, schedule: record })}
          >
            Vault
          </Button>
          <Button 
            type="link" 
            icon={<EditOutlined />}
            onClick={() => {
              // TODO: Implement edit functionality
            }}
          >
            Edit
          </Button>
          <Popconfirm
            title="Delete Schedule"
            description={`Are you sure you want to delete schedule "${record.scheduleName}"?`}
            onConfirm={() => handleDeleteSchedule(record)}
            okText="Yes"
            cancelText="No"
            okButtonProps={{ danger: true }}
          >
            <Button 
              type="link" 
              danger 
              icon={<DeleteOutlined />}
              loading={deleteScheduleMutation.isPending}
            >
              Delete
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  // Form fields
  const regionFormFields = [
    {
      name: 'regionName',
      label: 'Region Name',
      placeholder: 'Enter region name',
      required: true,
    },
  ]

  const bridgeFormFields = [
    {
      name: 'regionName',
      label: 'Region',
      placeholder: 'Select region',
      required: true,
      type: 'select' as const,
      options: dropdownData?.regions?.map(r => ({ value: r.value, label: r.label })) || [],
    },
    {
      name: 'bridgeName',
      label: 'Bridge Name',
      placeholder: 'Enter bridge name',
      required: true,
    },
  ]

  // Get filtered bridges based on selected region
  const selectedRegionForMachine = machineForm.watch('regionName')
  const filteredBridgesForMachine = React.useMemo(() => {
    if (!selectedRegionForMachine || !dropdownData?.bridgesByRegion) return []
    
    const regionData = dropdownData.bridgesByRegion.find(
      r => r.regionName === selectedRegionForMachine
    )
    return regionData?.bridges?.map(b => ({ 
      value: b.value, 
      label: b.label 
    })) || []
  }, [selectedRegionForMachine, dropdownData])

  // Clear bridge selection when region changes
  React.useEffect(() => {
    const currentBridge = machineForm.getValues('bridgeName')
    if (currentBridge && !filteredBridgesForMachine.find(b => b.value === currentBridge)) {
      machineForm.setValue('bridgeName', '')
    }
  }, [selectedRegionForMachine, filteredBridgesForMachine])

  const machineFormFields = [
    {
      name: 'teamName',
      label: 'Team',
      placeholder: 'Select team',
      required: true,
      type: 'select' as const,
      options: dropdownData?.teams?.map(t => ({ value: t.value, label: t.label })) || [],
    },
    {
      name: 'machineName',
      label: 'Machine Name',
      placeholder: 'Enter machine name',
      required: true,
    },
    {
      name: 'regionName',
      label: 'Region',
      placeholder: 'Select region',
      required: true,
      type: 'select' as const,
      options: dropdownData?.regions?.map(r => ({ value: r.value, label: r.label })) || [],
    },
    {
      name: 'bridgeName',
      label: 'Bridge',
      placeholder: selectedRegionForMachine ? 'Select bridge' : 'Select a region first',
      required: true,
      type: 'select' as const,
      options: filteredBridgesForMachine,
      disabled: !selectedRegionForMachine,
    },
  ]

  const repositoryFormFields = [
    {
      name: 'teamName',
      label: 'Team',
      placeholder: 'Select team',
      required: true,
      type: 'select' as const,
      options: dropdownData?.teams?.map(t => ({ value: t.value, label: t.label })) || [],
    },
    {
      name: 'repositoryName',
      label: 'Repository Name',
      placeholder: 'Enter repository name',
      required: true,
    },
  ]

  const storageFormFields = [
    {
      name: 'teamName',
      label: 'Team',
      placeholder: 'Select team',
      required: true,
      type: 'select' as const,
      options: dropdownData?.teams?.map(t => ({ value: t.value, label: t.label })) || [],
    },
    {
      name: 'storageName',
      label: 'Storage Name',
      placeholder: 'Enter storage name',
      required: true,
    },
  ]

  const scheduleFormFields = [
    {
      name: 'teamName',
      label: 'Team',
      placeholder: 'Select team',
      required: true,
      type: 'select' as const,
      options: dropdownData?.teams?.map(t => ({ value: t.value, label: t.label })) || [],
    },
    {
      name: 'scheduleName',
      label: 'Schedule Name',
      placeholder: 'Enter schedule name',
      required: true,
    },
    {
      name: 'scheduleDescription',
      label: 'Description',
      placeholder: 'Enter description (optional)',
      required: false,
    },
    {
      name: 'cronExpression',
      label: 'Cron Expression',
      placeholder: 'e.g., 0 0 * * * (daily at midnight)',
      required: true,
    },
  ]

  const teamResourcesTabs = [
    {
      key: 'machines',
      label: (
        <span>
          <CloudServerOutlined />
          Machines
        </span>
      ),
      children: (
        <Table
          columns={machineColumns}
          dataSource={machines}
          rowKey="machineName"
          loading={machinesLoading}
          pagination={{
            total: machines?.length || 0,
            pageSize: 10,
            showSizeChanger: true,
            showTotal: (total) => `Total ${total} machines`,
          }}
          locale={{
            emptyText: 'No machines found in this team',
          }}
        />
      ),
    },
    {
      key: 'repositories',
      label: (
        <span>
          <DatabaseOutlined />
          Repositories
        </span>
      ),
      children: (
        <Table
          columns={repositoryColumns}
          dataSource={repositories}
          rowKey="repositoryName"
          loading={repositoriesLoading}
          pagination={{
            total: repositories?.length || 0,
            pageSize: 10,
            showSizeChanger: true,
            showTotal: (total) => `Total ${total} repositories`,
          }}
          locale={{
            emptyText: 'No repositories found in this team',
          }}
        />
      ),
    },
    {
      key: 'storage',
      label: (
        <span>
          <HddOutlined />
          Storage
        </span>
      ),
      children: (
        <Table
          columns={storageColumns}
          dataSource={storages}
          rowKey="storageName"
          loading={storagesLoading}
          pagination={{
            total: storages?.length || 0,
            pageSize: 10,
            showSizeChanger: true,
            showTotal: (total) => `Total ${total} storage units`,
          }}
          locale={{
            emptyText: 'No storage found in this team',
          }}
        />
      ),
    },
    {
      key: 'schedules',
      label: (
        <span>
          <ScheduleOutlined />
          Schedules
        </span>
      ),
      children: (
        <Table
          columns={scheduleColumns}
          dataSource={schedules}
          rowKey="scheduleName"
          loading={schedulesLoading}
          pagination={{
            total: schedules?.length || 0,
            pageSize: 10,
            showSizeChanger: true,
            showTotal: (total) => `Total ${total} schedules`,
          }}
          locale={{
            emptyText: 'No schedules found in this team',
          }}
        />
      ),
    },
  ]

  const tabItems = [
    {
      key: 'teams',
      label: (
        <span>
          <TeamOutlined />
          Teams & Resources
        </span>
      ),
      children: (
        <Row gutter={[24, 24]}>
          <Col span={24}>
            <ResourceListView
              title={
                <Space>
                  <span style={{ fontSize: 16, fontWeight: 500 }}>Teams</span>
                  <span style={{ fontSize: 14, color: '#666' }}>Select a team to view its resources</span>
                </Space>
              }
              loading={teamsLoading}
              data={teams}
              columns={teamColumns}
              rowKey="teamName"
              searchPlaceholder="Search teams..."
              actions={
                <Button 
                  type="primary" 
                  icon={<PlusOutlined />}
                  onClick={() => setIsCreateTeamModalOpen(true)}
                  style={{ background: '#556b2f', borderColor: '#556b2f' }}
                >
                  Create Team
                </Button>
              }
              rowSelection={{
                type: 'radio',
                selectedRowKeys: selectedTeam ? [selectedTeam] : [],
                onChange: (selectedRowKeys: React.Key[]) => {
                  setSelectedTeam(selectedRowKeys[0] as string || null)
                },
              }}
              onRow={(record) => ({
                onClick: () => setSelectedTeam(record.teamName),
                style: { 
                  cursor: 'pointer',
                  backgroundColor: selectedTeam === record.teamName ? '#f0f5ff' : undefined
                },
              })}
            />
          </Col>
          
          <Col span={24}>
            <Card>
              <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <Title level={4} style={{ margin: 0 }}>
                    {selectedTeam ? `Resources in ${selectedTeam}` : 'Team Resources'}
                  </Title>
                  {!selectedTeam && (
                    <Text type="secondary" style={{ fontSize: 14 }}>
                      Select a team above to view and manage its resources
                    </Text>
                  )}
                </div>
                {selectedTeam && (
                  <Space>
                    <Button 
                      type="primary" 
                      icon={<PlusOutlined />}
                      onClick={() => {
                        switch(teamResourcesTab) {
                          case 'machines':
                            machineForm.setValue('teamName', selectedTeam)
                            setIsCreateMachineModalOpen(true)
                            break
                          case 'repositories':
                            repositoryForm.setValue('teamName', selectedTeam)
                            setIsCreateRepositoryModalOpen(true)
                            break
                          case 'storage':
                            storageForm.setValue('teamName', selectedTeam)
                            setIsCreateStorageModalOpen(true)
                            break
                          case 'schedules':
                            scheduleForm.setValue('teamName', selectedTeam)
                            setIsCreateScheduleModalOpen(true)
                            break
                        }
                      }}
                      style={{ background: '#556b2f', borderColor: '#556b2f' }}
                    >
                      Create {teamResourcesTab === 'storage' ? 'Storage' : teamResourcesTab.slice(0, -1).charAt(0).toUpperCase() + teamResourcesTab.slice(1, -1)}
                    </Button>
                  </Space>
                )}
              </div>
              
              {!selectedTeam ? (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description="Select a team to view its resources"
                  style={{ padding: '40px 0' }}
                />
              ) : (
                <Tabs
                  activeKey={teamResourcesTab}
                  onChange={setTeamResourcesTab}
                  items={teamResourcesTabs}
                />
              )}
            </Card>
          </Col>
        </Row>
      ),
    },
    {
      key: 'regions',
      label: (
        <span>
          <GlobalOutlined />
          Regions & Infrastructure
        </span>
      ),
      children: (
        <Row gutter={[24, 24]}>
          <Col span={24}>
            <ResourceListView
              title={
                <Space>
                  <span style={{ fontSize: 16, fontWeight: 500 }}>Regions</span>
                  <span style={{ fontSize: 14, color: '#666' }}>Select a region to view its bridges</span>
                </Space>
              }
              loading={regionsLoading}
              data={regions}
              columns={regionColumns}
              rowKey="regionName"
              searchPlaceholder="Search regions..."
              actions={
                <Button 
                  type="primary" 
                  icon={<PlusOutlined />}
                  onClick={() => setIsCreateRegionModalOpen(true)}
                  style={{ background: '#556b2f', borderColor: '#556b2f' }}
                >
                  Create Region
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
                style: { 
                  cursor: 'pointer',
                  backgroundColor: selectedRegion === record.regionName ? '#f0f5ff' : undefined
                },
              })}
            />
          </Col>
          
          <Col span={24}>
            <Card>
              <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <Title level={4} style={{ margin: 0 }}>
                    {selectedRegion ? `Bridges in ${selectedRegion}` : 'Bridges'}
                  </Title>
                  {!selectedRegion && (
                    <Text type="secondary" style={{ fontSize: 14 }}>
                      Select a region above to view and manage its bridges
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
                    Create Bridge
                  </Button>
                )}
              </div>
              
              {!selectedRegion ? (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description="Select a region to view its bridges"
                  style={{ padding: '40px 0' }}
                />
              ) : (
                <Table
                  columns={bridgeColumns}
                  dataSource={bridges}
                  rowKey="bridgeName"
                  loading={bridgesLoading}
                  pagination={{
                    total: bridges?.length || 0,
                    pageSize: 10,
                    showSizeChanger: true,
                    showTotal: (total) => `Total ${total} bridges`,
                  }}
                  locale={{
                    emptyText: 'No bridges found in this region',
                  }}
                />
              )}
            </Card>
          </Col>
        </Row>
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

      {/* Team Modals */}
      <Modal
        title="Create Team"
        open={isCreateTeamModalOpen}
        onCancel={() => {
          setIsCreateTeamModalOpen(false)
          teamForm.resetFields()
        }}
        footer={null}
      >
        <Form
          form={teamForm}
          layout="vertical"
          onFinish={handleCreateTeam}
        >
          <Form.Item
            name="teamName"
            label="Team Name"
            rules={[
              { required: true, message: 'Please enter team name' },
              { pattern: /^[a-zA-Z0-9-_]+$/, message: 'Team name can only contain letters, numbers, hyphens, and underscores' },
            ]}
          >
            <Input placeholder="Enter team name" />
          </Form.Item>

          <Form.Item style={{ marginBottom: 0, textAlign: 'right' }}>
            <Space>
              <Button onClick={() => {
                setIsCreateTeamModalOpen(false)
                teamForm.resetFields()
              }}>
                Cancel
              </Button>
              <Button 
                type="primary" 
                htmlType="submit"
                loading={createTeamMutation.isPending}
                style={{ background: '#556b2f', borderColor: '#556b2f' }}
              >
                Create
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      {/* Region Modals */}
      <Modal
        title="Create Region"
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
          submitText="Create"
          cancelText="Cancel"
          onCancel={() => {
            setIsCreateRegionModalOpen(false)
            regionForm.reset()
          }}
          loading={createRegionMutation.isPending}
        />
      </Modal>

      <VaultConfigModal
        open={regionVaultModalConfig.open}
        onCancel={() => setRegionVaultModalConfig({ open: false })}
        onSave={handleUpdateRegionVault}
        title={`Configure Vault - ${regionVaultModalConfig.region?.regionName}`}
        initialVault="{}"
        initialVersion={regionVaultModalConfig.region?.vaultVersion || 1}
        loading={updateRegionVaultMutation.isPending}
      />

      {/* Bridge Modals */}
      <Modal
        title="Create Bridge"
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
          submitText="Create"
          cancelText="Cancel"
          onCancel={() => {
            setIsCreateBridgeModalOpen(false)
            bridgeForm.reset()
          }}
          loading={createBridgeMutation.isPending}
        />
      </Modal>

      <VaultConfigModal
        open={bridgeVaultModalConfig.open}
        onCancel={() => setBridgeVaultModalConfig({ open: false })}
        onSave={handleUpdateBridgeVault}
        title={`Configure Vault - ${bridgeVaultModalConfig.bridge?.bridgeName}`}
        initialVault="{}"
        initialVersion={bridgeVaultModalConfig.bridge?.vaultVersion || 1}
        loading={updateBridgeVaultMutation.isPending}
      />

      {/* Machine Modals */}
      <Modal
        title="Create Machine"
        open={isCreateMachineModalOpen}
        onCancel={() => {
          setIsCreateMachineModalOpen(false)
          machineForm.reset()
        }}
        footer={null}
      >
        <ResourceForm
          form={machineForm}
          fields={machineFormFields}
          onSubmit={handleCreateMachine}
          submitText="Create"
          cancelText="Cancel"
          onCancel={() => {
            setIsCreateMachineModalOpen(false)
            machineForm.reset()
          }}
          loading={createMachineMutation.isPending}
        />
      </Modal>

      <VaultConfigModal
        open={machineVaultModalConfig.open}
        onCancel={() => setMachineVaultModalConfig({ open: false })}
        onSave={handleUpdateMachineVault}
        title={`Configure Vault - ${machineVaultModalConfig.machine?.machineName}`}
        initialVault="{}"
        initialVersion={machineVaultModalConfig.machine?.vaultVersion || 1}
        loading={updateMachineVaultMutation.isPending}
      />

      {/* Repository Modals */}
      <Modal
        title="Create Repository"
        open={isCreateRepositoryModalOpen}
        onCancel={() => {
          setIsCreateRepositoryModalOpen(false)
          repositoryForm.reset()
        }}
        footer={null}
      >
        <ResourceForm
          form={repositoryForm}
          fields={repositoryFormFields}
          onSubmit={handleCreateRepository}
          submitText="Create"
          cancelText="Cancel"
          onCancel={() => {
            setIsCreateRepositoryModalOpen(false)
            repositoryForm.reset()
          }}
          loading={createRepositoryMutation.isPending}
        />
      </Modal>

      <VaultConfigModal
        open={repositoryVaultModalConfig.open}
        onCancel={() => setRepositoryVaultModalConfig({ open: false })}
        onSave={handleUpdateRepositoryVault}
        title={`Configure Vault - ${repositoryVaultModalConfig.repository?.repositoryName}`}
        initialVault="{}"
        initialVersion={repositoryVaultModalConfig.repository?.vaultVersion || 1}
        loading={updateRepositoryVaultMutation.isPending}
      />

      {/* Storage Modals */}
      <Modal
        title="Create Storage"
        open={isCreateStorageModalOpen}
        onCancel={() => {
          setIsCreateStorageModalOpen(false)
          storageForm.reset()
        }}
        footer={null}
      >
        <ResourceForm
          form={storageForm}
          fields={storageFormFields}
          onSubmit={handleCreateStorage}
          submitText="Create"
          cancelText="Cancel"
          onCancel={() => {
            setIsCreateStorageModalOpen(false)
            storageForm.reset()
          }}
          loading={createStorageMutation.isPending}
        />
      </Modal>

      <VaultConfigModal
        open={storageVaultModalConfig.open}
        onCancel={() => setStorageVaultModalConfig({ open: false })}
        onSave={handleUpdateStorageVault}
        title={`Configure Vault - ${storageVaultModalConfig.storage?.storageName}`}
        initialVault="{}"
        initialVersion={storageVaultModalConfig.storage?.vaultVersion || 1}
        loading={updateStorageVaultMutation.isPending}
      />

      {/* Schedule Modals */}
      <Modal
        title="Create Schedule"
        open={isCreateScheduleModalOpen}
        onCancel={() => {
          setIsCreateScheduleModalOpen(false)
          scheduleForm.reset()
        }}
        footer={null}
      >
        <ResourceForm
          form={scheduleForm}
          fields={scheduleFormFields}
          onSubmit={handleCreateSchedule}
          submitText="Create"
          cancelText="Cancel"
          onCancel={() => {
            setIsCreateScheduleModalOpen(false)
            scheduleForm.reset()
          }}
          loading={createScheduleMutation.isPending}
        />
      </Modal>

      <VaultConfigModal
        open={scheduleVaultModalConfig.open}
        onCancel={() => setScheduleVaultModalConfig({ open: false })}
        onSave={handleUpdateScheduleVault}
        title={`Configure Vault - ${scheduleVaultModalConfig.schedule?.scheduleName}`}
        initialVault="{}"
        initialVersion={scheduleVaultModalConfig.schedule?.vaultVersion || 1}
        loading={updateScheduleVaultMutation.isPending}
      />
    </>
  )
}

export default OrganizationPage