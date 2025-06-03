import React, { useState } from 'react'
import { Card, Tabs, Button, Space, Modal, Popconfirm, Tag, Typography, Form, Input, Table, Row, Col, Empty, Badge } from 'antd'
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
  ScheduleOutlined
} from '@ant-design/icons'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useTranslation } from 'react-i18next'
import ResourceListView from '@/components/common/ResourceListView'
import ResourceForm from '@/components/forms/ResourceForm'
import VaultConfigModal from '@/components/common/VaultConfigModal'

// Team queries
import { useTeams, useCreateTeam, useUpdateTeamName, useDeleteTeam, Team } from '@/api/queries/teams'

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

// Machine queries
import { 
  useMachines, 
  useCreateMachine, 
  useUpdateMachineName,
  useUpdateMachineBridge,
  useDeleteMachine, 
  useUpdateMachineVault, 
  Machine 
} from '@/api/queries/machines'

// Repository queries
import { 
  useRepositories, 
  useCreateRepository, 
  useUpdateRepositoryName,
  useDeleteRepository, 
  useUpdateRepositoryVault, 
  Repository 
} from '@/api/queries/repositories'

// Storage queries
import { 
  useStorage, 
  useCreateStorage, 
  useUpdateStorageName,
  useDeleteStorage, 
  useUpdateStorageVault, 
  Storage 
} from '@/api/queries/storage'

// Schedule queries
import { 
  useSchedules, 
  useCreateSchedule, 
  useUpdateScheduleName,
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
  CreateScheduleForm,
  editTeamSchema,
  EditTeamForm,
  editRegionSchema,
  EditRegionForm,
  editBridgeSchema,
  EditBridgeForm,
  editMachineSchema,
  EditMachineForm,
  editRepositorySchema,
  EditRepositoryForm,
  editStorageSchema,
  EditStorageForm,
  editScheduleSchema,
  EditScheduleForm
} from '@/utils/validation'

const { Title, Text } = Typography

const OrganizationPage: React.FC = () => {
  const { t } = useTranslation('organization')
  const [activeTab, setActiveTab] = useState('teams')
  const [selectedTeam, setSelectedTeam] = useState<string | null>(null)
  const [teamResourcesTab, setTeamResourcesTab] = useState('machines')
  
  // Team state
  const [isCreateTeamModalOpen, setIsCreateTeamModalOpen] = useState(false)
  const [editingTeam, setEditingTeam] = useState<Team | null>(null)
  const [teamForm] = Form.useForm()
  
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

  // Machine state
  const [isCreateMachineModalOpen, setIsCreateMachineModalOpen] = useState(false)
  const [editingMachine, setEditingMachine] = useState<Machine | null>(null)
  const [machineVaultModalConfig, setMachineVaultModalConfig] = useState<{
    open: boolean
    machine?: Machine
  }>({ open: false })

  // Repository state
  const [isCreateRepositoryModalOpen, setIsCreateRepositoryModalOpen] = useState(false)
  const [editingRepository, setEditingRepository] = useState<Repository | null>(null)
  const [repositoryVaultModalConfig, setRepositoryVaultModalConfig] = useState<{
    open: boolean
    repository?: Repository
  }>({ open: false })

  // Storage state
  const [isCreateStorageModalOpen, setIsCreateStorageModalOpen] = useState(false)
  const [editingStorage, setEditingStorage] = useState<Storage | null>(null)
  const [storageVaultModalConfig, setStorageVaultModalConfig] = useState<{
    open: boolean
    storage?: Storage
  }>({ open: false })

  // Schedule state
  const [isCreateScheduleModalOpen, setIsCreateScheduleModalOpen] = useState(false)
  const [editingSchedule, setEditingSchedule] = useState<Schedule | null>(null)
  const [scheduleVaultModalConfig, setScheduleVaultModalConfig] = useState<{
    open: boolean
    schedule?: Schedule
  }>({ open: false })

  // Common hooks
  const { data: dropdownData } = useDropdownData()

  // Team hooks
  const { data: teams = [], isLoading: teamsLoading } = useTeams()
  const createTeamMutation = useCreateTeam()
  const updateTeamNameMutation = useUpdateTeamName()
  const deleteTeamMutation = useDeleteTeam()

  // Region hooks
  const { data: regions = [], isLoading: regionsLoading } = useRegions()
  const createRegionMutation = useCreateRegion()
  const updateRegionNameMutation = useUpdateRegionName()
  const deleteRegionMutation = useDeleteRegion()
  const updateRegionVaultMutation = useUpdateRegionVault()

  // Bridge hooks
  const { data: bridges = [], isLoading: bridgesLoading } = useBridges(selectedRegion || undefined)
  const createBridgeMutation = useCreateBridge()
  const updateBridgeNameMutation = useUpdateBridgeName()
  const deleteBridgeMutation = useDeleteBridge()
  const updateBridgeVaultMutation = useUpdateBridgeVault()

  // Machine hooks
  const { data: machines = [], isLoading: machinesLoading } = useMachines(selectedTeam || undefined)
  const createMachineMutation = useCreateMachine()
  const updateMachineNameMutation = useUpdateMachineName()
  const updateMachineBridgeMutation = useUpdateMachineBridge()
  const deleteMachineMutation = useDeleteMachine()
  const updateMachineVaultMutation = useUpdateMachineVault()

  // Repository hooks
  const { data: repositories = [], isLoading: repositoriesLoading } = useRepositories(selectedTeam || undefined)
  const createRepositoryMutation = useCreateRepository()
  const updateRepositoryNameMutation = useUpdateRepositoryName()
  const deleteRepositoryMutation = useDeleteRepository()
  const updateRepositoryVaultMutation = useUpdateRepositoryVault()

  // Storage hooks
  const { data: storages = [], isLoading: storagesLoading } = useStorage(selectedTeam || undefined)
  const createStorageMutation = useCreateStorage()
  const updateStorageNameMutation = useUpdateStorageName()
  const deleteStorageMutation = useDeleteStorage()
  const updateStorageVaultMutation = useUpdateStorageVault()

  // Schedule hooks
  const { data: schedules = [], isLoading: schedulesLoading } = useSchedules(selectedTeam || undefined)
  const createScheduleMutation = useCreateSchedule()
  const updateScheduleNameMutation = useUpdateScheduleName()
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

  const handleEditTeam = async (values: EditTeamForm) => {
    if (!editingTeam) return
    try {
      await updateTeamNameMutation.mutateAsync({
        currentTeamName: editingTeam.teamName,
        newTeamName: values.teamName,
      })
      setEditingTeam(null)
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

  const handleEditMachine = async (values: EditMachineForm) => {
    if (!editingMachine) return
    try {
      await updateMachineNameMutation.mutateAsync({
        teamName: editingMachine.teamName,
        currentMachineName: editingMachine.machineName,
        newMachineName: values.machineName,
      })
      if (values.bridgeName !== editingMachine.bridgeName) {
        await updateMachineBridgeMutation.mutateAsync({
          teamName: editingMachine.teamName,
          machineName: values.machineName,
          newBridgeName: values.bridgeName,
        })
      }
      setEditingMachine(null)
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

  const handleEditRepository = async (values: EditRepositoryForm) => {
    if (!editingRepository) return
    try {
      await updateRepositoryNameMutation.mutateAsync({
        teamName: editingRepository.teamName,
        currentRepositoryName: editingRepository.repositoryName,
        newRepositoryName: values.repositoryName,
      })
      setEditingRepository(null)
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

  const handleEditStorage = async (values: EditStorageForm) => {
    if (!editingStorage) return
    try {
      await updateStorageNameMutation.mutateAsync({
        teamName: editingStorage.teamName,
        currentStorageName: editingStorage.storageName,
        newStorageName: values.storageName,
      })
      setEditingStorage(null)
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

  const handleEditSchedule = async (values: EditScheduleForm) => {
    if (!editingSchedule) return
    try {
      await updateScheduleNameMutation.mutateAsync({
        teamName: editingSchedule.teamName,
        currentScheduleName: editingSchedule.scheduleName,
        newScheduleName: values.scheduleName,
      })
      setEditingSchedule(null)
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
      title: t('teams.teamName'),
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
      title: t('teams.members'),
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
      title: t('teams.machines'),
      dataIndex: 'machineCount',
      key: 'machineCount',
      width: 100,
    },
    {
      title: t('teams.repositories'),
      dataIndex: 'repoCount',
      key: 'repoCount',
      width: 120,
    },
    {
      title: t('teams.storage'),
      dataIndex: 'storageCount',
      key: 'storageCount',
      width: 100,
    },
    {
      title: t('teams.schedules'),
      dataIndex: 'scheduleCount',
      key: 'scheduleCount',
      width: 100,
    },
    {
      title: t('general.actions'),
      key: 'actions',
      width: 150,
      render: (_: any, record: Team) => (
        <Space>
          <Button 
            type="link" 
            icon={<EditOutlined />}
            onClick={() => {
              setEditingTeam(record)
              teamForm.setFieldsValue({ teamName: record.teamName })
            }}
          >
            {t('general.edit')}
          </Button>
          <Popconfirm
            title={t('teams.deleteTeam')}
            description={t('teams.confirmDelete', { teamName: record.teamName })}
            onConfirm={() => handleDeleteTeam(record.teamName)}
            okText={t('general.yes')}
            cancelText={t('general.no')}
            okButtonProps={{ danger: true }}
          >
            <Button 
              type="link" 
              danger 
              icon={<DeleteOutlined />}
              loading={deleteTeamMutation.isPending}
            >
              {t('general.delete')}
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  // Region columns
  const regionColumns = [
    {
      title: t('regions.regionName'),
      dataIndex: 'regionName',
      key: 'regionName',
      render: (text: string) => (
        <Space>
          <GlobalOutlined style={{ color: '#556b2f' }} />
          <strong>{text}</strong>
        </Space>
      ),
    },
    {
      title: t('regions.bridges'),
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
      title: t('general.vaultVersion'),
      dataIndex: 'vaultVersion',
      key: 'vaultVersion',
      width: 120,
      render: (version: number) => <Tag>{t('general.versionFormat', { version })}</Tag>,
    },
    {
      title: t('general.actions'),
      key: 'actions',
      width: 200,
      render: (_: any, record: Region) => (
        <Space>
          <Button
            type="link"
            icon={<SettingOutlined />}
            onClick={() => setRegionVaultModalConfig({ open: true, region: record })}
          >
            {t('general.vault')}
          </Button>
          <Button 
            type="link" 
            icon={<EditOutlined />}
            onClick={() => {
              setEditingRegion(record)
              regionForm.setValue('regionName', record.regionName)
            }}
          >
            {t('general.edit')}
          </Button>
          <Popconfirm
            title={t('regions.deleteRegion')}
            description={t('regions.confirmDelete', { regionName: record.regionName })}
            onConfirm={() => handleDeleteRegion(record.regionName)}
            okText={t('general.yes')}
            cancelText={t('general.no')}
            okButtonProps={{ danger: true }}
          >
            <Button 
              type="link" 
              danger 
              icon={<DeleteOutlined />}
              loading={deleteRegionMutation.isPending}
            >
              {t('general.delete')}
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  // Bridge columns
  const bridgeColumns = [
    {
      title: t('bridges.bridgeName'),
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
      title: t('teams.machines'),
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
      title: t('general.vaultVersion'),
      dataIndex: 'vaultVersion',
      key: 'vaultVersion',
      width: 120,
      render: (version: number) => <Tag>{t('general.versionFormat', { version })}</Tag>,
    },
    {
      title: t('general.actions'),
      key: 'actions',
      width: 200,
      render: (_: any, record: Bridge) => (
        <Space>
          <Button
            type="link"
            icon={<SettingOutlined />}
            onClick={() => setBridgeVaultModalConfig({ open: true, bridge: record })}
          >
            {t('general.vault')}
          </Button>
          <Button 
            type="link" 
            icon={<EditOutlined />}
            onClick={() => {
              setEditingBridge(record)
              bridgeForm.setValue('bridgeName', record.bridgeName)
            }}
          >
            {t('general.edit')}
          </Button>
          <Popconfirm
            title={t('bridges.deleteBridge')}
            description={t('bridges.confirmDelete', { bridgeName: record.bridgeName })}
            onConfirm={() => handleDeleteBridge(record)}
            okText={t('general.yes')}
            cancelText={t('general.no')}
            okButtonProps={{ danger: true }}
          >
            <Button 
              type="link" 
              danger 
              icon={<DeleteOutlined />}
              loading={deleteBridgeMutation.isPending}
            >
              {t('general.delete')}
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  // Machine columns
  const machineColumns = [
    {
      title: t('machines.machineName'),
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
      title: t('bridges.bridge'),
      dataIndex: 'bridgeName',
      key: 'bridgeName',
      render: (bridge: string) => <Tag color="blue">{bridge}</Tag>,
    },
    {
      title: t('machines.queueItems'),
      dataIndex: 'queueCount',
      key: 'queueCount',
      width: 120,
      render: (count: number) => (
        <Badge count={count} showZero style={{ backgroundColor: count > 0 ? '#52c41a' : '#d9d9d9' }} />
      ),
    },
    {
      title: t('general.vaultVersion'),
      dataIndex: 'vaultVersion',
      key: 'vaultVersion',
      width: 120,
      render: (version: number) => <Tag>{t('general.versionFormat', { version })}</Tag>,
    },
    {
      title: t('general.actions'),
      key: 'actions',
      width: 200,
      render: (_: any, record: Machine) => (
        <Space>
          <Button
            type="link"
            icon={<SettingOutlined />}
            onClick={() => setMachineVaultModalConfig({ open: true, machine: record })}
          >
            {t('general.vault')}
          </Button>
          <Button 
            type="link" 
            icon={<EditOutlined />}
            onClick={() => {
              setEditingMachine(record)
              machineForm.setValue('machineName', record.machineName)
              machineForm.setValue('bridgeName', record.bridgeName)
            }}
          >
            {t('general.edit')}
          </Button>
          <Popconfirm
            title={t('machines.deleteMachine')}
            description={t('machines.confirmDelete', { machineName: record.machineName })}
            onConfirm={() => handleDeleteMachine(record)}
            okText={t('general.yes')}
            cancelText={t('general.no')}
            okButtonProps={{ danger: true }}
          >
            <Button 
              type="link" 
              danger 
              icon={<DeleteOutlined />}
              loading={deleteMachineMutation.isPending}
            >
              {t('general.delete')}
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  // Repository columns
  const repositoryColumns = [
    {
      title: t('repositories.repositoryName'),
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
      title: t('general.vaultVersion'),
      dataIndex: 'vaultVersion',
      key: 'vaultVersion',
      width: 120,
      render: (version: number) => <Tag>{t('general.versionFormat', { version })}</Tag>,
    },
    {
      title: t('general.actions'),
      key: 'actions',
      width: 200,
      render: (_: any, record: Repository) => (
        <Space>
          <Button
            type="link"
            icon={<SettingOutlined />}
            onClick={() => setRepositoryVaultModalConfig({ open: true, repository: record })}
          >
            {t('general.vault')}
          </Button>
          <Button 
            type="link" 
            icon={<EditOutlined />}
            onClick={() => {
              setEditingRepository(record)
              repositoryForm.setValue('repositoryName', record.repositoryName)
            }}
          >
            {t('general.edit')}
          </Button>
          <Popconfirm
            title={t('repositories.deleteRepository')}
            description={t('repositories.confirmDelete', { repositoryName: record.repositoryName })}
            onConfirm={() => handleDeleteRepository(record)}
            okText={t('general.yes')}
            cancelText={t('general.no')}
            okButtonProps={{ danger: true }}
          >
            <Button 
              type="link" 
              danger 
              icon={<DeleteOutlined />}
              loading={deleteRepositoryMutation.isPending}
            >
              {t('general.delete')}
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  // Storage columns
  const storageColumns = [
    {
      title: t('storage.storageName'),
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
      title: t('general.vaultVersion'),
      dataIndex: 'vaultVersion',
      key: 'vaultVersion',
      width: 120,
      render: (version: number) => <Tag>{t('general.versionFormat', { version })}</Tag>,
    },
    {
      title: t('general.actions'),
      key: 'actions',
      width: 200,
      render: (_: any, record: Storage) => (
        <Space>
          <Button
            type="link"
            icon={<SettingOutlined />}
            onClick={() => setStorageVaultModalConfig({ open: true, storage: record })}
          >
            {t('general.vault')}
          </Button>
          <Button 
            type="link" 
            icon={<EditOutlined />}
            onClick={() => {
              setEditingStorage(record)
              storageForm.setValue('storageName', record.storageName)
            }}
          >
            {t('general.edit')}
          </Button>
          <Popconfirm
            title={t('storage.deleteStorage')}
            description={t('storage.confirmDelete', { storageName: record.storageName })}
            onConfirm={() => handleDeleteStorage(record)}
            okText={t('general.yes')}
            cancelText={t('general.no')}
            okButtonProps={{ danger: true }}
          >
            <Button 
              type="link" 
              danger 
              icon={<DeleteOutlined />}
              loading={deleteStorageMutation.isPending}
            >
              {t('general.delete')}
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  // Schedule columns
  const scheduleColumns = [
    {
      title: t('schedules.scheduleName'),
      dataIndex: 'scheduleName',
      key: 'scheduleName',
      render: (text: string) => (
        <Space>
          <ScheduleOutlined style={{ color: '#556b2f' }} />
          <strong>{text}</strong>
        </Space>
      ),
    },
    {
      title: t('general.vaultVersion'),
      dataIndex: 'vaultVersion',
      key: 'vaultVersion',
      width: 120,
      render: (version: number) => <Tag>{t('general.versionFormat', { version })}</Tag>,
    },
    {
      title: t('general.actions'),
      key: 'actions',
      width: 200,
      render: (_: any, record: Schedule) => (
        <Space>
          <Button
            type="link"
            icon={<SettingOutlined />}
            onClick={() => setScheduleVaultModalConfig({ open: true, schedule: record })}
          >
            {t('general.vault')}
          </Button>
          <Button 
            type="link" 
            icon={<EditOutlined />}
            onClick={() => {
              setEditingSchedule(record)
              scheduleForm.setValue('scheduleName', record.scheduleName)
            }}
          >
            {t('general.edit')}
          </Button>
          <Popconfirm
            title={t('schedules.deleteSchedule')}
            description={t('schedules.confirmDelete', { scheduleName: record.scheduleName })}
            onConfirm={() => handleDeleteSchedule(record)}
            okText={t('general.yes')}
            cancelText={t('general.no')}
            okButtonProps={{ danger: true }}
          >
            <Button 
              type="link" 
              danger 
              icon={<DeleteOutlined />}
              loading={deleteScheduleMutation.isPending}
            >
              {t('general.delete')}
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
      label: t('regions.regionName'),
      placeholder: t('regions.placeholders.enterRegionName'),
      required: true,
    },
  ]

  const bridgeFormFields = [
    {
      name: 'regionName',
      label: t('general.region'),
      placeholder: t('regions.placeholders.selectRegion'),
      required: true,
      type: 'select' as const,
      options: dropdownData?.regions?.map((r: any) => ({ value: r.value, label: r.label })) || [],
    },
    {
      name: 'bridgeName',
      label: t('bridges.bridgeName'),
      placeholder: t('bridges.placeholders.enterBridgeName'),
      required: true,
    },
  ]

  // Get filtered bridges based on selected region
  const selectedRegionForMachine = machineForm.watch('regionName')
  const filteredBridgesForMachine = React.useMemo(() => {
    if (!selectedRegionForMachine || !dropdownData?.bridgesByRegion) return []
    
    const regionData = dropdownData.bridgesByRegion.find(
      (r: any) => r.regionName === selectedRegionForMachine
    )
    return regionData?.bridges?.map((b: any) => ({ 
      value: b.value, 
      label: b.label 
    })) || []
  }, [selectedRegionForMachine, dropdownData])

  // Clear bridge selection when region changes
  React.useEffect(() => {
    const currentBridge = machineForm.getValues('bridgeName')
    if (currentBridge && !filteredBridgesForMachine.find((b: any) => b.value === currentBridge)) {
      machineForm.setValue('bridgeName', '')
    }
  }, [selectedRegionForMachine, filteredBridgesForMachine])

  const machineFormFields = [
    {
      name: 'teamName',
      label: t('general.team'),
      placeholder: t('teams.placeholders.selectTeam'),
      required: true,
      type: 'select' as const,
      options: dropdownData?.teams?.map(t => ({ value: t.value, label: t.label })) || [],
    },
    {
      name: 'machineName',
      label: t('machines.machineName'),
      placeholder: t('machines.placeholders.enterMachineName'),
      required: true,
    },
    {
      name: 'regionName',
      label: t('general.region'),
      placeholder: t('regions.placeholders.selectRegion'),
      required: true,
      type: 'select' as const,
      options: dropdownData?.regions?.map((r: any) => ({ value: r.value, label: r.label })) || [],
    },
    {
      name: 'bridgeName',
      label: t('bridges.bridge'),
      placeholder: selectedRegionForMachine ? t('bridges.placeholders.selectBridge') : t('bridges.placeholders.selectRegionFirst'),
      required: true,
      type: 'select' as const,
      options: filteredBridgesForMachine,
      disabled: !selectedRegionForMachine,
    },
  ]

  const repositoryFormFields = [
    {
      name: 'teamName',
      label: t('general.team'),
      placeholder: t('teams.placeholders.selectTeam'),
      required: true,
      type: 'select' as const,
      options: dropdownData?.teams?.map(t => ({ value: t.value, label: t.label })) || [],
    },
    {
      name: 'repositoryName',
      label: t('repositories.repositoryName'),
      placeholder: t('repositories.placeholders.enterRepositoryName'),
      required: true,
    },
  ]

  const storageFormFields = [
    {
      name: 'teamName',
      label: t('general.team'),
      placeholder: t('teams.placeholders.selectTeam'),
      required: true,
      type: 'select' as const,
      options: dropdownData?.teams?.map(t => ({ value: t.value, label: t.label })) || [],
    },
    {
      name: 'storageName',
      label: t('storage.storageName'),
      placeholder: t('storage.placeholders.enterStorageName'),
      required: true,
    },
  ]

  const scheduleFormFields = [
    {
      name: 'teamName',
      label: t('general.team'),
      placeholder: t('teams.placeholders.selectTeam'),
      required: true,
      type: 'select' as const,
      options: dropdownData?.teams?.map(t => ({ value: t.value, label: t.label })) || [],
    },
    {
      name: 'scheduleName',
      label: t('schedules.scheduleName'),
      placeholder: t('schedules.placeholders.enterScheduleName'),
      required: true,
    },
  ]

  const teamResourcesTabs = [
    {
      key: 'machines',
      label: (
        <span>
          <CloudServerOutlined />
          {t('resourceTabs.machines')}
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
            showTotal: (total) => t('machines.totalMachines', { total }),
          }}
          locale={{
            emptyText: t('machines.noMachines'),
          }}
        />
      ),
    },
    {
      key: 'repositories',
      label: (
        <span>
          <DatabaseOutlined />
          {t('resourceTabs.repositories')}
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
            showTotal: (total) => t('repositories.totalRepositories', { total }),
          }}
          locale={{
            emptyText: t('repositories.noRepositories'),
          }}
        />
      ),
    },
    {
      key: 'storage',
      label: (
        <span>
          <HddOutlined />
          {t('resourceTabs.storage')}
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
            showTotal: (total) => t('storage.totalStorage', { total }),
          }}
          locale={{
            emptyText: t('storage.noStorage'),
          }}
        />
      ),
    },
    {
      key: 'schedules',
      label: (
        <span>
          <ScheduleOutlined />
          {t('resourceTabs.schedules')}
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
            showTotal: (total) => t('schedules.totalSchedules', { total }),
          }}
          locale={{
            emptyText: t('schedules.noSchedules'),
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
          {t('tabs.teamsResources')}
        </span>
      ),
      children: (
        <Row gutter={[24, 24]}>
          <Col span={24}>
            <ResourceListView
              title={
                <Space>
                  <span style={{ fontSize: 16, fontWeight: 500 }}>{t('teams.title')}</span>
                  <span style={{ fontSize: 14, color: '#666' }}>{t('teams.selectTeamPrompt')}</span>
                </Space>
              }
              loading={teamsLoading}
              data={teams}
              columns={teamColumns}
              rowKey="teamName"
              searchPlaceholder={t('teams.searchTeams')}
              actions={
                <Button 
                  type="primary" 
                  icon={<PlusOutlined />}
                  onClick={() => setIsCreateTeamModalOpen(true)}
                  style={{ background: '#556b2f', borderColor: '#556b2f' }}
                >
                  {t('teams.createTeam')}
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
                className: selectedTeam === record.teamName ? 'selected-row' : '',
                style: { cursor: 'pointer' },
              })}
            />
          </Col>
          
          <Col span={24}>
            <Card>
              <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <Title level={4} style={{ margin: 0 }}>
                    {selectedTeam ? t('teams.resourcesInTeam', { team: selectedTeam }) : t('teams.teamResources')}
                  </Title>
                  {!selectedTeam && (
                    <Text type="secondary" style={{ fontSize: 14 }}>
                      {t('teams.selectTeamToView')}
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
                      {teamResourcesTab === 'machines' && t('machines.createMachine')}
                      {teamResourcesTab === 'repositories' && t('repositories.createRepository')}
                      {teamResourcesTab === 'storage' && t('storage.createStorage')}
                      {teamResourcesTab === 'schedules' && t('schedules.createSchedule')}
                    </Button>
                  </Space>
                )}
              </div>
              
              {!selectedTeam ? (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={t('teams.selectTeamPrompt')}
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
          {t('tabs.regionsInfrastructure')}
        </span>
      ),
      children: (
        <Row gutter={[24, 24]}>
          <Col span={24}>
            <ResourceListView
              title={
                <Space>
                  <span style={{ fontSize: 16, fontWeight: 500 }}>{t('regions.title')}</span>
                  <span style={{ fontSize: 14, color: '#666' }}>{t('regions.selectRegionPrompt')}</span>
                </Space>
              }
              loading={regionsLoading}
              data={regions}
              columns={regionColumns}
              rowKey="regionName"
              searchPlaceholder={t('regions.searchRegions')}
              actions={
                <Button 
                  type="primary" 
                  icon={<PlusOutlined />}
                  onClick={() => setIsCreateRegionModalOpen(true)}
                  style={{ background: '#556b2f', borderColor: '#556b2f' }}
                >
                  {t('regions.createRegion')}
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
                    {selectedRegion ? t('regions.bridgesInRegion', { region: selectedRegion }) : t('bridges.title')}
                  </Title>
                  {!selectedRegion && (
                    <Text type="secondary" style={{ fontSize: 14 }}>
                      {t('regions.selectRegionToView')}
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
                    {t('bridges.createBridge')}
                  </Button>
                )}
              </div>
              
              {!selectedRegion ? (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={t('regions.selectRegionPrompt')}
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
                    showTotal: (total) => t('bridges.totalBridges', { total }),
                  }}
                  locale={{
                    emptyText: t('bridges.noBridges'),
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
        title={t('teams.createTeam')}
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
            label={t('teams.teamName')}
            rules={[
              { required: true, message: t('teams.validation.teamNameRequired') },
              { pattern: /^[a-zA-Z0-9-_]+$/, message: t('teams.validation.teamNamePattern') },
            ]}
          >
            <Input placeholder={t('teams.placeholders.enterTeamName')} />
          </Form.Item>

          <Form.Item style={{ marginBottom: 0, textAlign: 'right' }}>
            <Space>
              <Button onClick={() => {
                setIsCreateTeamModalOpen(false)
                teamForm.resetFields()
              }}>
                {t('general.cancel')}
              </Button>
              <Button 
                type="primary" 
                htmlType="submit"
                loading={createTeamMutation.isPending}
                style={{ background: '#556b2f', borderColor: '#556b2f' }}
              >
                {t('general.create')}
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      {/* Edit Team Modal */}
      <Modal
        title={t('teams.editTeam')}
        open={!!editingTeam}
        onCancel={() => {
          setEditingTeam(null)
          teamForm.resetFields()
        }}
        footer={null}
      >
        <Form
          form={teamForm}
          layout="vertical"
          onFinish={handleEditTeam}
        >
          <Form.Item
            name="teamName"
            label={t('teams.teamName')}
            rules={[
              { required: true, message: t('teams.validation.teamNameRequired') },
              { pattern: /^[a-zA-Z0-9-_]+$/, message: t('teams.validation.teamNamePattern') },
            ]}
          >
            <Input placeholder={t('teams.placeholders.enterTeamName')} />
          </Form.Item>

          <Form.Item style={{ marginBottom: 0, textAlign: 'right' }}>
            <Space>
              <Button onClick={() => {
                setEditingTeam(null)
                teamForm.resetFields()
              }}>
                {t('general.cancel')}
              </Button>
              <Button 
                type="primary" 
                htmlType="submit"
                loading={updateTeamNameMutation.isPending}
                style={{ background: '#556b2f', borderColor: '#556b2f' }}
              >
                {t('general.save')}
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      {/* Region Modals */}
      <Modal
        title={t('regions.createRegion')}
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
          submitText={t('general.create')}
          cancelText={t('general.cancel')}
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
        title={t('general.configureVault', { name: regionVaultModalConfig.region?.regionName || '' })}
        initialVault="{}"
        initialVersion={regionVaultModalConfig.region?.vaultVersion || 1}
        loading={updateRegionVaultMutation.isPending}
      />

      {/* Edit Region Modal */}
      <Modal
        title={t('regions.editRegion')}
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
            label: t('regions.regionName'),
            placeholder: t('regions.placeholders.enterRegionName'),
            required: true,
          }]}
          onSubmit={handleEditRegion}
          submitText={t('general.save')}
          cancelText={t('general.cancel')}
          onCancel={() => {
            setEditingRegion(null)
            regionForm.reset()
          }}
          loading={updateRegionNameMutation.isPending}
        />
      </Modal>

      {/* Bridge Modals */}
      <Modal
        title={t('bridges.createBridge')}
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
          submitText={t('general.create')}
          cancelText={t('general.cancel')}
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
        title={t('general.configureVault', { name: bridgeVaultModalConfig.bridge?.bridgeName || '' })}
        initialVault="{}"
        initialVersion={bridgeVaultModalConfig.bridge?.vaultVersion || 1}
        loading={updateBridgeVaultMutation.isPending}
      />

      {/* Edit Bridge Modal */}
      <Modal
        title={t('bridges.editBridge')}
        open={!!editingBridge}
        onCancel={() => {
          setEditingBridge(null)
          bridgeForm.reset()
        }}
        footer={null}
      >
        <ResourceForm
          form={bridgeForm}
          fields={[{
            name: 'bridgeName',
            label: t('bridges.bridgeName'),
            placeholder: t('bridges.placeholders.enterBridgeName'),
            required: true,
          }]}
          onSubmit={handleEditBridge}
          submitText={t('general.save')}
          cancelText={t('general.cancel')}
          onCancel={() => {
            setEditingBridge(null)
            bridgeForm.reset()
          }}
          loading={updateBridgeNameMutation.isPending}
        />
      </Modal>

      {/* Machine Modals */}
      <Modal
        title={t('machines.createMachine')}
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
          submitText={t('general.create')}
          cancelText={t('general.cancel')}
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
        title={t('general.configureVault', { name: machineVaultModalConfig.machine?.machineName || '' })}
        initialVault="{}"
        initialVersion={machineVaultModalConfig.machine?.vaultVersion || 1}
        loading={updateMachineVaultMutation.isPending}
      />

      {/* Edit Machine Modal */}
      <Modal
        title={t('machines.editMachine')}
        open={!!editingMachine}
        onCancel={() => {
          setEditingMachine(null)
          machineForm.reset()
        }}
        footer={null}
      >
        <ResourceForm
          form={machineForm}
          fields={[
            {
              name: 'machineName',
              label: t('machines.machineName'),
              placeholder: t('machines.placeholders.enterMachineName'),
              required: true,
            },
            {
              name: 'bridgeName',
              label: t('bridges.bridge'),
              type: 'select',
              placeholder: t('machines.placeholders.selectBridge'),
              required: true,
              options: dropdownData?.bridges?.map(b => ({ label: b, value: b })) || [],
            },
          ]}
          onSubmit={handleEditMachine}
          submitText={t('general.save')}
          cancelText={t('general.cancel')}
          onCancel={() => {
            setEditingMachine(null)
            machineForm.reset()
          }}
          loading={updateMachineNameMutation.isPending || updateMachineBridgeMutation.isPending}
        />
      </Modal>

      {/* Repository Modals */}
      <Modal
        title={t('repositories.createRepository')}
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
          submitText={t('general.create')}
          cancelText={t('general.cancel')}
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
        title={t('general.configureVault', { name: repositoryVaultModalConfig.repository?.repositoryName || '' })}
        initialVault="{}"
        initialVersion={repositoryVaultModalConfig.repository?.vaultVersion || 1}
        loading={updateRepositoryVaultMutation.isPending}
      />

      {/* Edit Repository Modal */}
      <Modal
        title={t('repositories.editRepository')}
        open={!!editingRepository}
        onCancel={() => {
          setEditingRepository(null)
          repositoryForm.reset()
        }}
        footer={null}
      >
        <ResourceForm
          form={repositoryForm}
          fields={[{
            name: 'repositoryName',
            label: t('repositories.repositoryName'),
            placeholder: t('repositories.placeholders.enterRepositoryName'),
            required: true,
          }]}
          onSubmit={handleEditRepository}
          submitText={t('general.save')}
          cancelText={t('general.cancel')}
          onCancel={() => {
            setEditingRepository(null)
            repositoryForm.reset()
          }}
          loading={updateRepositoryNameMutation.isPending}
        />
      </Modal>

      {/* Storage Modals */}
      <Modal
        title={t('storage.createStorage')}
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
          submitText={t('general.create')}
          cancelText={t('general.cancel')}
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
        title={t('general.configureVault', { name: storageVaultModalConfig.storage?.storageName || '' })}
        initialVault="{}"
        initialVersion={storageVaultModalConfig.storage?.vaultVersion || 1}
        loading={updateStorageVaultMutation.isPending}
      />

      {/* Edit Storage Modal */}
      <Modal
        title={t('storage.editStorage')}
        open={!!editingStorage}
        onCancel={() => {
          setEditingStorage(null)
          storageForm.reset()
        }}
        footer={null}
      >
        <ResourceForm
          form={storageForm}
          fields={[{
            name: 'storageName',
            label: t('storage.storageName'),
            placeholder: t('storage.placeholders.enterStorageName'),
            required: true,
          }]}
          onSubmit={handleEditStorage}
          submitText={t('general.save')}
          cancelText={t('general.cancel')}
          onCancel={() => {
            setEditingStorage(null)
            storageForm.reset()
          }}
          loading={updateStorageNameMutation.isPending}
        />
      </Modal>

      {/* Schedule Modals */}
      <Modal
        title={t('schedules.createSchedule')}
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
          submitText={t('general.create')}
          cancelText={t('general.cancel')}
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
        title={t('general.configureVault', { name: scheduleVaultModalConfig.schedule?.scheduleName || '' })}
        initialVault="{}"
        initialVersion={scheduleVaultModalConfig.schedule?.vaultVersion || 1}
        loading={updateScheduleVaultMutation.isPending}
      />

      {/* Edit Schedule Modal */}
      <Modal
        title={t('schedules.editSchedule')}
        open={!!editingSchedule}
        onCancel={() => {
          setEditingSchedule(null)
          scheduleForm.reset()
        }}
        footer={null}
      >
        <ResourceForm
          form={scheduleForm}
          fields={[{
            name: 'scheduleName',
            label: t('schedules.scheduleName'),
            placeholder: t('schedules.placeholders.enterScheduleName'),
            required: true,
          }]}
          onSubmit={handleEditSchedule}
          submitText={t('general.save')}
          cancelText={t('general.cancel')}
          onCancel={() => {
            setEditingSchedule(null)
            scheduleForm.reset()
          }}
          loading={updateScheduleNameMutation.isPending}
        />
      </Modal>
    </>
  )
}

export default OrganizationPage