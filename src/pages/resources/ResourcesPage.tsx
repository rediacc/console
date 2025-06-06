import React, { useState } from 'react'
import { Card, Tabs, Button, Space, Modal, Popconfirm, Tag, Typography, Form, Input, Table, Row, Col, Empty, Alert, Spin } from 'antd'
import { 
  TeamOutlined, 
  PlusOutlined, 
  EditOutlined, 
  DeleteOutlined, 
  UserOutlined,
  SettingOutlined,
  CloudOutlined,
  InboxOutlined,
  DesktopOutlined,
  ScheduleOutlined
} from '@ant-design/icons'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useTranslation } from 'react-i18next'
import { useSelector } from 'react-redux'
import { RootState } from '@/store/store'
import ResourceListView from '@/components/common/ResourceListView'
import ResourceForm from '@/components/forms/ResourceForm'
import VaultEditorModal from '@/components/common/VaultEditorModal'

// Team queries
import { useTeams, useCreateTeam, useUpdateTeamName, useDeleteTeam, useUpdateTeamVault, Team } from '@/api/queries/teams'


// Machine queries
import { MachineTable } from '@/components/resources/MachineTable'

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
  createRepositorySchema,
  CreateRepositoryForm,
  createStorageSchema,
  CreateStorageForm,
  createScheduleSchema,
  CreateScheduleForm,
  EditTeamForm,
  EditRepositoryForm,
  EditStorageForm,
  EditScheduleForm
} from '@/utils/validation'

const { Title, Text } = Typography

const ResourcesPage: React.FC = () => {
  const { t } = useTranslation(['resources', 'machines', 'common'])
  const uiMode = useSelector((state: RootState) => state.ui.uiMode)
  const [selectedTeams, setSelectedTeams] = useState<string[]>([])
  const [teamResourcesTab, setTeamResourcesTab] = useState('machines')
  
  // Team state
  const [isCreateTeamModalOpen, setIsCreateTeamModalOpen] = useState(false)
  const [editingTeam, setEditingTeam] = useState<Team | null>(null)
  const [teamForm] = Form.useForm()
  const [teamVaultModalConfig, setTeamVaultModalConfig] = useState<{
    open: boolean
    team?: Team
  }>({ open: false })
  

  // Machine state - removed modal states since we navigate to machines page instead

  // Machine state
  const [isCreateMachineModalOpen, setIsCreateMachineModalOpen] = useState(false)

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
  const { data: teams, isLoading: teamsLoading } = useTeams()
  const teamsList: Team[] = teams || []
  const createTeamMutation = useCreateTeam()
  const updateTeamNameMutation = useUpdateTeamName()
  const deleteTeamMutation = useDeleteTeam()
  const updateTeamVaultMutation = useUpdateTeamVault()



  // Repository hooks - only fetch when repository tab is active
  const { data: repositories = [], isLoading: repositoriesLoading } = useRepositories(
    selectedTeams.length > 0 && teamResourcesTab === 'repositories' ? selectedTeams : undefined
  )
  const createRepositoryMutation = useCreateRepository()
  const updateRepositoryNameMutation = useUpdateRepositoryName()
  const deleteRepositoryMutation = useDeleteRepository()
  const updateRepositoryVaultMutation = useUpdateRepositoryVault()

  // Storage hooks - only fetch when storage tab is active
  const { data: storages = [], isLoading: storagesLoading } = useStorage(
    selectedTeams.length > 0 && teamResourcesTab === 'storage' ? selectedTeams : undefined
  )
  const createStorageMutation = useCreateStorage()
  const updateStorageNameMutation = useUpdateStorageName()
  const deleteStorageMutation = useDeleteStorage()
  const updateStorageVaultMutation = useUpdateStorageVault()

  // Schedule hooks - only fetch when schedules tab is active
  const { data: schedules = [], isLoading: schedulesLoading } = useSchedules(
    selectedTeams.length > 0 && teamResourcesTab === 'schedules' ? selectedTeams : undefined
  )
  const createScheduleMutation = useCreateSchedule()
  const updateScheduleNameMutation = useUpdateScheduleName()
  const deleteScheduleMutation = useDeleteSchedule()
  const updateScheduleVaultMutation = useUpdateScheduleVault()

  // Set default selected team in Simple mode
  React.useEffect(() => {
    if (uiMode === 'simple' && selectedTeams.length === 0 && teamsList && teamsList.length > 0) {
      // Check if "Private Team" exists
      const privateTeam = teamsList.find((team: Team) => team.teamName === 'Private Team')
      if (privateTeam) {
        setSelectedTeams(['Private Team'])
      }
    }
  }, [uiMode, selectedTeams, teamsList])

  // Forms

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
      if (selectedTeams.includes(teamName)) {
        setSelectedTeams(selectedTeams.filter(t => t !== teamName))
      }
    } catch (error) {
      // Error handled by mutation
    }
  }

  const handleUpdateTeamVault = async (vault: string, version: number) => {
    if (!teamVaultModalConfig.team) return

    await updateTeamVaultMutation.mutateAsync({
      teamName: teamVaultModalConfig.team.teamName,
      teamVault: vault,
      vaultVersion: version,
    })
    setTeamVaultModalConfig({ open: false })
  }


  // Machine handlers removed - handled in MachinePage

  // Set default values for Simple mode when modals open
  React.useEffect(() => {
    if (isCreateRepositoryModalOpen && uiMode === 'simple') {
      repositoryForm.setValue('teamName', 'Private Team');
    }
  }, [isCreateRepositoryModalOpen, uiMode, repositoryForm]);

  React.useEffect(() => {
    if (isCreateStorageModalOpen && uiMode === 'simple') {
      storageForm.setValue('teamName', 'Private Team');
    }
  }, [isCreateStorageModalOpen, uiMode, storageForm]);

  React.useEffect(() => {
    if (isCreateScheduleModalOpen && uiMode === 'simple') {
      scheduleForm.setValue('teamName', 'Private Team');
    }
  }, [isCreateScheduleModalOpen, uiMode, scheduleForm]);

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
      ellipsis: true,
      render: (text: string) => (
        <Space>
          <TeamOutlined style={{ color: '#556b2f' }} />
          <strong>{text}</strong>
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
      ellipsis: true,
      render: (text: string) => (
        <Space>
          <InboxOutlined style={{ color: '#556b2f' }} />
          <strong>{text}</strong>
        </Space>
      ),
    },
    {
      title: t('general.team'),
      dataIndex: 'teamName',
      key: 'teamName',
      width: 150,
      ellipsis: true,
      render: (teamName: string) => <Tag color="blue">{teamName}</Tag>,
    },
    ...(uiMode === 'expert' ? [{
      title: t('general.vaultVersion'),
      dataIndex: 'vaultVersion',
      key: 'vaultVersion',
      width: 100,
      align: 'center' as const,
      render: (version: number) => <Tag>{t('common:general.versionFormat', { version })}</Tag>,
    }] : []),
    {
      title: t('general.actions'),
      key: 'actions',
      width: 250,
      align: 'center' as const,
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
      ellipsis: true,
      render: (text: string) => (
        <Space>
          <CloudOutlined style={{ color: '#556b2f' }} />
          <strong>{text}</strong>
        </Space>
      ),
    },
    {
      title: t('general.team'),
      dataIndex: 'teamName',
      key: 'teamName',
      width: 150,
      ellipsis: true,
      render: (teamName: string) => <Tag color="blue">{teamName}</Tag>,
    },
    ...(uiMode === 'expert' ? [{
      title: t('general.vaultVersion'),
      dataIndex: 'vaultVersion',
      key: 'vaultVersion',
      width: 100,
      align: 'center' as const,
      render: (version: number) => <Tag>{t('common:general.versionFormat', { version })}</Tag>,
    }] : []),
    {
      title: t('general.actions'),
      key: 'actions',
      width: 250,
      align: 'center' as const,
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
      ellipsis: true,
      render: (text: string) => (
        <Space>
          <ScheduleOutlined style={{ color: '#556b2f' }} />
          <strong>{text}</strong>
        </Space>
      ),
    },
    {
      title: t('general.team'),
      dataIndex: 'teamName',
      key: 'teamName',
      width: 150,
      ellipsis: true,
      render: (teamName: string) => <Tag color="blue">{teamName}</Tag>,
    },
    ...(uiMode === 'expert' ? [{
      title: t('general.vaultVersion'),
      dataIndex: 'vaultVersion',
      key: 'vaultVersion',
      width: 100,
      align: 'center' as const,
      render: (version: number) => <Tag>{t('common:general.versionFormat', { version })}</Tag>,
    }] : []),
    {
      title: t('general.actions'),
      key: 'actions',
      width: 250,
      align: 'center' as const,
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

  const repositoryFormFields = uiMode === 'simple'
    ? [
        {
          name: 'repositoryName',
          label: t('repositories.repositoryName'),
          placeholder: t('repositories.placeholders.enterRepositoryName'),
          required: true,
        },
      ]
    : [
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

  const storageFormFields = uiMode === 'simple'
    ? [
        {
          name: 'storageName',
          label: t('storage.storageName'),
          placeholder: t('storage.placeholders.enterStorageName'),
          required: true,
        },
      ]
    : [
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

  const scheduleFormFields = uiMode === 'simple'
    ? [
        {
          name: 'scheduleName',
          label: t('schedules.scheduleName'),
          placeholder: t('schedules.placeholders.enterScheduleName'),
          required: true,
        },
      ]
    : [
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
          <DesktopOutlined />
          {t('resourceTabs.machines')}
        </span>
      ),
      children: (
        <MachineTable 
          teamFilter={selectedTeams.length > 0 ? selectedTeams : undefined}
          showFilters={true}
          showActions={true}
          showCreateModal={isCreateMachineModalOpen}
          onCreateModalChange={setIsCreateMachineModalOpen}
          enabled={teamResourcesTab === 'machines'}
          className="full-height-machine-table"
        />
      ),
    },
    {
      key: 'repositories',
      label: (
        <span>
          <InboxOutlined />
          {t('resourceTabs.repositories')}
        </span>
      ),
      children: repositoriesLoading ? (
        <div style={{ textAlign: 'center', padding: '100px 0' }}>
          <Spin size="large" tip={t('common:general.loading')} />
        </div>
      ) : (
        <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
          <Table
            columns={repositoryColumns}
            dataSource={repositories}
            rowKey="repositoryName"
            scroll={{ x: 'max-content', y: 'calc(100vh - 400px)' }}
            pagination={{
              total: repositories?.length || 0,
              pageSize: 10,
              showSizeChanger: true,
              showTotal: (total) => t('repositories.totalRepositories', { total }),
              position: ['bottomRight'],
            }}
            locale={{
              emptyText: t('repositories.noRepositories'),
            }}
            sticky
          />
        </div>
      ),
    },
    {
      key: 'storage',
      label: (
        <span>
          <CloudOutlined />
          {t('resourceTabs.storage')}
        </span>
      ),
      children: storagesLoading ? (
        <div style={{ textAlign: 'center', padding: '100px 0' }}>
          <Spin size="large" tip={t('common:general.loading')} />
        </div>
      ) : (
        <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
          <Table
            columns={storageColumns}
            dataSource={storages}
            rowKey="storageName"
            scroll={{ x: 'max-content', y: 'calc(100vh - 400px)' }}
            pagination={{
              total: storages?.length || 0,
              pageSize: 10,
              showSizeChanger: true,
              showTotal: (total) => t('storage.totalStorage', { total }),
              position: ['bottomRight'],
            }}
            locale={{
              emptyText: t('storage.noStorage'),
            }}
            sticky
          />
        </div>
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
      children: schedulesLoading ? (
        <div style={{ textAlign: 'center', padding: '100px 0' }}>
          <Spin size="large" tip={t('common:general.loading')} />
        </div>
      ) : (
        <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
          <Table
            columns={scheduleColumns}
            dataSource={schedules}
            rowKey="scheduleName"
            scroll={{ x: 'max-content', y: 'calc(100vh - 400px)' }}
            pagination={{
              total: schedules?.length || 0,
              pageSize: 10,
              showSizeChanger: true,
              showTotal: (total) => t('schedules.totalSchedules', { total }),
              position: ['bottomRight'],
            }}
            locale={{
              emptyText: t('schedules.noSchedules'),
            }}
            sticky
          />
        </div>
      ),
    },
  ]

  // Calculate available height for full-height layout
  const containerStyle: React.CSSProperties = {
    height: 'calc(100vh - 64px - 48px - 32px)', // viewport - header - breadcrumb - margins
    overflow: 'hidden'
  }

  const cardStyle: React.CSSProperties = {
    height: '100%',
    display: 'flex',
    flexDirection: 'column'
  }

  const cardBodyStyle: React.CSSProperties = {
    flex: 1,
    overflow: 'hidden',
    padding: '16px',
    display: 'flex',
    flexDirection: 'column'
  }

  return (
    <>
      {uiMode !== 'simple' ? (
        <Row gutter={24} style={containerStyle}>
          <Col span={8} style={{ height: '100%' }}>
            <ResourceListView
              title={
                <Space>
                  <span style={{ fontSize: 16, fontWeight: 500 }}>{t('teams.title')}</span>
                </Space>
              }
              loading={teamsLoading}
              data={teamsList}
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
                type: 'checkbox',
                selectedRowKeys: selectedTeams,
                onChange: (selectedRowKeys: React.Key[]) => {
                  setSelectedTeams(selectedRowKeys as string[])
                },
              }}
              onRow={(record) => ({
                onClick: (e: React.MouseEvent) => {
                  // Check if the click is on the checkbox or its parent elements
                  const target = e.target as HTMLElement
                  const isCheckboxClick = target.closest('.ant-checkbox-wrapper') || 
                                        target.closest('.ant-checkbox') ||
                                        target.closest('td[class*="ant-table-selection-column"]')
                  
                  if (!isCheckboxClick) {
                    // Row click selects only one team (not on checkbox)
                    setSelectedTeams([record.teamName])
                  }
                },
                className: selectedTeams.includes(record.teamName) ? 'selected-row' : '',
                style: { cursor: 'pointer' },
              })}
              containerStyle={{
                height: '100%',
                display: 'flex',
                flexDirection: 'column',
              }}
              tableStyle={{ 
                height: 'calc(100vh - 300px)'
              }}
              pagination={{
                pageSize: 50,
                showSizeChanger: true,
                pageSizeOptions: ['20', '50', '100', '200'],
                position: ['bottomRight'],
              }}
            />
          </Col>
          
          <Col span={16} style={{ height: '100%' }}>
            <Card style={cardStyle} bodyStyle={cardBodyStyle}>
              <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <Title level={4} style={{ margin: 0 }}>
                    {selectedTeams.length > 0 ? t('teams.resourcesInTeams', { count: selectedTeams.length }) : t('teams.teamResources')}
                  </Title>
                  {selectedTeams.length === 0 && (
                    <Text type="secondary" style={{ fontSize: 14 }}>
                      {t('teams.selectTeamToView')}
                    </Text>
                  )}
                </div>
                {selectedTeams.length > 0 && (
                  <Space>
                    <Button 
                      type="primary" 
                      icon={<PlusOutlined />}
                      onClick={() => {
                        switch(teamResourcesTab) {
                          case 'machines':
                            setIsCreateMachineModalOpen(true)
                            break
                          case 'repositories':
                            if (selectedTeams.length === 1) {
                              repositoryForm.setValue('teamName', selectedTeams[0])
                            }
                            setIsCreateRepositoryModalOpen(true)
                            break
                          case 'storage':
                            if (selectedTeams.length === 1) {
                              storageForm.setValue('teamName', selectedTeams[0])
                            }
                            setIsCreateStorageModalOpen(true)
                            break
                          case 'schedules':
                            if (selectedTeams.length === 1) {
                              scheduleForm.setValue('teamName', selectedTeams[0])
                            }
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
              
              {selectedTeams.length === 0 ? (
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
                  style={{ height: 'calc(100% - 60px)', display: 'flex', flexDirection: 'column' }}
                  className="full-height-tabs"
                  destroyInactiveTabPane
                />
              )}
            </Card>
          </Col>
        </Row>
      ) : (
        <Card>
          <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <Title level={4} style={{ margin: 0 }}>
                {t('teams.teamResources')}
              </Title>
            </div>
            <Space>
              <Button 
                type="primary" 
                icon={<PlusOutlined />}
                onClick={() => {
                  switch(teamResourcesTab) {
                    case 'machines':
                      setIsCreateMachineModalOpen(true)
                      break
                    case 'repositories':
                      repositoryForm.setValue('teamName', 'Private Team')
                      setIsCreateRepositoryModalOpen(true)
                      break
                    case 'storage':
                      storageForm.setValue('teamName', 'Private Team')
                      setIsCreateStorageModalOpen(true)
                      break
                  }
                }}
                style={{ background: '#556b2f', borderColor: '#556b2f' }}
              >
                {teamResourcesTab === 'machines' && t('machines.createMachine')}
                {teamResourcesTab === 'repositories' && t('repositories.createRepository')}
                {teamResourcesTab === 'storage' && t('storage.createStorage')}
              </Button>
            </Space>
          </div>
          
          <Tabs
            activeKey={teamResourcesTab}
            onChange={setTeamResourcesTab}
            items={teamResourcesTabs.filter(tab => tab.key !== 'schedules')}
            destroyInactiveTabPane
          />
        </Card>
      )}

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

      <VaultEditorModal
        open={teamVaultModalConfig.open}
        onCancel={() => setTeamVaultModalConfig({ open: false })}
        onSave={handleUpdateTeamVault}
        entityType="TEAM"
        title={t('general.configureVault', { name: teamVaultModalConfig.team?.teamName || '' })}
        initialVault={teamVaultModalConfig.team?.vaultContent || "{}"}
        initialVersion={teamVaultModalConfig.team?.vaultVersion || 1}
        loading={updateTeamVaultMutation.isPending}
      />



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
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
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
          
          {uiMode === 'simple' && (
            <div style={{ 
              borderTop: '1px solid #f0f0f0', 
              paddingTop: 16,
              marginTop: 8
            }}>
              <Alert
                message={t('general.defaultsApplied')}
                description={
                  <Space direction="vertical" size={0}>
                    <Text>{t('general.team')}: Private Team</Text>
                  </Space>
                }
                type="info"
                showIcon
              />
            </div>
          )}
        </div>
      </Modal>

      <VaultEditorModal
        open={repositoryVaultModalConfig.open}
        onCancel={() => setRepositoryVaultModalConfig({ open: false })}
        onSave={handleUpdateRepositoryVault}
        entityType="REPOSITORY"
        title={t('general.configureVault', { name: repositoryVaultModalConfig.repository?.repositoryName || '' })}
        initialVault={repositoryVaultModalConfig.repository?.vaultContent || "{}"}
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
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
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
          
          {uiMode === 'simple' && (
            <div style={{ 
              borderTop: '1px solid #f0f0f0', 
              paddingTop: 16,
              marginTop: 8
            }}>
              <Alert
                message={t('general.defaultsApplied')}
                description={
                  <Space direction="vertical" size={0}>
                    <Text>{t('general.team')}: Private Team</Text>
                  </Space>
                }
                type="info"
                showIcon
              />
            </div>
          )}
        </div>
      </Modal>

      <VaultEditorModal
        open={storageVaultModalConfig.open}
        onCancel={() => setStorageVaultModalConfig({ open: false })}
        onSave={handleUpdateStorageVault}
        entityType="STORAGE"
        title={t('general.configureVault', { name: storageVaultModalConfig.storage?.storageName || '' })}
        initialVault={storageVaultModalConfig.storage?.vaultContent || "{}"}
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
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
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
          
          {uiMode === 'simple' && (
            <div style={{ 
              borderTop: '1px solid #f0f0f0', 
              paddingTop: 16,
              marginTop: 8
            }}>
              <Alert
                message={t('general.defaultsApplied')}
                description={
                  <Space direction="vertical" size={0}>
                    <Text>{t('general.team')}: Private Team</Text>
                  </Space>
                }
                type="info"
                showIcon
              />
            </div>
          )}
        </div>
      </Modal>

      <VaultEditorModal
        open={scheduleVaultModalConfig.open}
        onCancel={() => setScheduleVaultModalConfig({ open: false })}
        onSave={handleUpdateScheduleVault}
        entityType="SCHEDULE"
        title={t('general.configureVault', { name: scheduleVaultModalConfig.schedule?.scheduleName || '' })}
        initialVault={scheduleVaultModalConfig.schedule?.vaultContent || "{}"}
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

export default ResourcesPage