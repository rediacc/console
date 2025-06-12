import React, { useState, useRef, useEffect } from 'react'
import { Card, Tabs, Button, Space, Modal, Tag, Typography, Table, Row, Col, Empty, Spin, Dropdown } from 'antd'
import { 
  PlusOutlined, 
  EditOutlined, 
  DeleteOutlined, 
  SettingOutlined,
  CloudOutlined,
  InboxOutlined,
  DesktopOutlined,
  ScheduleOutlined,
  MoreOutlined,
  FunctionOutlined
} from '@ant-design/icons'
import { useTranslation } from 'react-i18next'
import { useSelector } from 'react-redux'
import { RootState } from '@/store/store'
import UnifiedResourceModal, { ResourceType } from '@/components/resources/UnifiedResourceModal'
import QueueItemTraceModal from '@/components/common/QueueItemTraceModal'
import { showMessage } from '@/utils/messages'

// Team queries
import { useTeams, Team } from '@/api/queries/teams'


// Machine queries
import { MachineTable } from '@/components/resources/MachineTable'
import {
  useCreateMachine,
  useUpdateMachineName,
  useUpdateMachineBridge,
  useUpdateMachineVault,
  useDeleteMachine,
  type Machine
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
// Validation schemas now handled in UnifiedResourceModal
import { useDynamicPageSize } from '@/hooks/useDynamicPageSize'
import { type QueueFunction } from '@/api/queries/queue'
import { useCreateQueueItem } from '@/api/queries/queue'
import FunctionSelectionModal from '@/components/common/FunctionSelectionModal'
import TeamSelector from '@/components/common/TeamSelector'
import { useQueueVaultBuilder } from '@/hooks/useQueueVaultBuilder'

const { Title, Text } = Typography

const ResourcesPage: React.FC = () => {
  const { t } = useTranslation(['resources', 'machines', 'common'])
  const uiMode = useSelector((state: RootState) => state.ui.uiMode)
  const [selectedTeams, setSelectedTeams] = useState<string[]>([])
  const [teamResourcesTab, setTeamResourcesTab] = useState('machines')
  
  // Unified modal state
  const [unifiedModalState, setUnifiedModalState] = useState<{
    open: boolean
    resourceType: ResourceType
    mode: 'create' | 'edit'
    data?: any
  }>({ open: false, resourceType: 'machine', mode: 'create' })
  
  // Refs for table containers
  const repositoryTableRef = useRef<HTMLDivElement>(null)
  const storageTableRef = useRef<HTMLDivElement>(null)
  const scheduleTableRef = useRef<HTMLDivElement>(null)
  
  // Team state - removed create team functionality (exists in System page)
  

  // Machine state - removed modal states since we navigate to machines page instead

  // Machine state removed - now handled by unified modal
  
  // Helper to get create button text based on current tab
  const getCreateButtonText = () => {
    switch(teamResourcesTab) {
      case 'machines': return t('machines.createMachine')
      case 'storage': return t('storage.createStorage')
      case 'schedules': return t('schedules.createSchedule')
      default: return t('general.create')
    }
  }

  // State for current editing/creating resource
  const [currentResource, setCurrentResource] = useState<any>(null)
  
  // Machine delete mutation
  const deleteMachineMutation = useDeleteMachine()
  
  // Machine-specific handlers
  const handleDeleteMachine = async (machine: Machine) => {
    Modal.confirm({
      title: t('machines:confirmDelete'),
      content: t('machines:deleteWarning', { name: machine.machineName }),
      okText: t('common:actions.delete'),
      okType: 'danger',
      cancelText: t('common:actions.cancel'),
      onOk: async () => {
        try {
          await deleteMachineMutation.mutateAsync({
            teamName: machine.teamName,
            machineName: machine.machineName,
          })
          showMessage('success', t('machines:deleteSuccess'))
        } catch (error) {
          showMessage('error', t('machines:deleteError'))
        }
      },
    })
  }

  // Common hooks
  const { data: dropdownData } = useDropdownData()

  // Team hooks
  const { data: teams, isLoading: teamsLoading } = useTeams()
  const teamsList: Team[] = teams || []



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
  
  // Queue mutation
  const createQueueItemMutation = useCreateQueueItem()
  const { buildQueueVault } = useQueueVaultBuilder()
  
  // Queue trace modal state
  const [queueTraceModal, setQueueTraceModal] = useState<{
    visible: boolean
    taskId: string | null
  }>({ visible: false, taskId: null })
  
  // Dynamic page sizes for tables
  const repositoryPageSize = useDynamicPageSize(repositoryTableRef, {
    containerOffset: 200, // Account for tab headers, pagination, and padding
    minRows: 5,
    maxRows: 50,
    rowHeight: 55 // Typical row height with padding
  })
  
  const storagePageSize = useDynamicPageSize(storageTableRef, {
    containerOffset: 200,
    minRows: 5,
    maxRows: 50,
    rowHeight: 55
  })
  
  const schedulePageSize = useDynamicPageSize(scheduleTableRef, {
    containerOffset: 200,
    minRows: 5,
    maxRows: 50,
    rowHeight: 55
  })

  // Set default selected team on startup
  const hasInitializedTeam = useRef(false)
  React.useEffect(() => {
    if (!teamsLoading && !hasInitializedTeam.current && teamsList && teamsList.length > 0) {
      hasInitializedTeam.current = true
      if (uiMode === 'simple') {
        // In simple mode, try to select "Private Team" first
        const privateTeam = teamsList.find((team: Team) => team.teamName === 'Private Team')
        if (privateTeam) {
          setSelectedTeams(['Private Team'])
        } else {
          // Fall back to first team if Private Team doesn't exist
          setSelectedTeams([teamsList[0].teamName])
        }
      } else {
        // In expert mode, select the first team
        setSelectedTeams([teamsList[0].teamName])
      }
    }
  }, [uiMode, teamsList, teamsLoading])

  // Handler to open unified modal
  const openUnifiedModal = (resourceType: ResourceType, mode: 'create' | 'edit', data?: any) => {
    setUnifiedModalState({
      open: true,
      resourceType,
      mode,
      data
    })
  }
  
  const closeUnifiedModal = () => {
    setUnifiedModalState({
      open: false,
      resourceType: 'machine',
      mode: 'create'
    })
    setCurrentResource(null)
  }

  // Team handlers removed - create team functionality exists in System page


  // Machine handlers removed - handled in MachinePage

  // Unified modal submit handler
  const handleUnifiedModalSubmit = async (data: any) => {
    try {
      switch (unifiedModalState.resourceType) {
        case 'repository':
          if (unifiedModalState.mode === 'create') {
            await createRepositoryMutation.mutateAsync(data)
          } else {
            await updateRepositoryNameMutation.mutateAsync({
              teamName: currentResource.teamName,
              currentRepositoryName: currentResource.repositoryName,
              newRepositoryName: data.repositoryName,
            })
          }
          break
        case 'storage':
          if (unifiedModalState.mode === 'create') {
            await createStorageMutation.mutateAsync(data)
          } else {
            await updateStorageNameMutation.mutateAsync({
              teamName: currentResource.teamName,
              currentStorageName: currentResource.storageName,
              newStorageName: data.storageName,
            })
          }
          break
        case 'schedule':
          if (unifiedModalState.mode === 'create') {
            await createScheduleMutation.mutateAsync(data)
          } else {
            await updateScheduleNameMutation.mutateAsync({
              teamName: currentResource.teamName,
              currentScheduleName: currentResource.scheduleName,
              newScheduleName: data.scheduleName,
            })
          }
          break
      }
      closeUnifiedModal()
    } catch (error) {
      // Error handled by mutation
    }
  }

  // Unified vault update handler
  const handleUnifiedVaultUpdate = async (vault: string, version: number) => {
    if (!currentResource) return

    try {
      switch (unifiedModalState.resourceType) {
        case 'machine':
          await updateMachineVaultMutation.mutateAsync({
            teamName: currentResource.teamName,
            machineName: currentResource.machineName,
            machineVault: vault,
            vaultVersion: version,
          })
          break
        case 'repository':
          await updateRepositoryVaultMutation.mutateAsync({
            teamName: currentResource.teamName,
            repositoryName: currentResource.repositoryName,
            repositoryVault: vault,
            vaultVersion: version,
          })
          break
        case 'storage':
          await updateStorageVaultMutation.mutateAsync({
            teamName: currentResource.teamName,
            storageName: currentResource.storageName,
            storageVault: vault,
            vaultVersion: version,
          })
          break
        case 'schedule':
          await updateScheduleVaultMutation.mutateAsync({
            teamName: currentResource.teamName,
            scheduleName: currentResource.scheduleName,
            scheduleVault: vault,
            vaultVersion: version,
          })
          break
      }
    } catch (error) {
      // Error handled by mutation
    }
  }

  // Repository delete handler
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

  // Storage delete handler
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

  // Schedule delete handler
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

  // Handle function selection for machine
  const handleMachineFunctionSelected = async (functionData: {
    function: QueueFunction;
    params: Record<string, any>;
    priority: number;
    description: string;
  }) => {
    if (!currentResource) return;

    try {
      // Check if this is repo_new function - if so, create repository first
      if (functionData.function.name === 'repo_new') {
        const repoName = functionData.params.repo;
        if (!repoName) {
          showMessage('error', 'Repository name is required for repo_new function');
          return;
        }

        // Create repository in the system first
        try {
          await createRepositoryMutation.mutateAsync({
            teamName: currentResource.teamName,
            repositoryName: repoName,
            repositoryVault: '{}'
          });
        } catch (error: any) {
          // If repository creation fails, don't proceed with queue item
          return;
        }
      }

      // Find the team vault data
      const teamData = teamsList.find(t => t.teamName === currentResource.teamName)
      // TODO: Repository vault would need a separate query - not available in dropdown data
      const repoData = null

      // Build the queue vault with context data
      const queueVault = await buildQueueVault({
        teamName: currentResource.teamName,
        machineName: currentResource.machineName,
        bridgeName: currentResource.bridgeName,
        repositoryName: functionData.params.repo, // Include if repo param exists
        functionName: functionData.function.name,
        params: functionData.params,
        priority: functionData.priority,
        description: functionData.description,
        addedVia: 'machine-table',
        // Pass vault data
        machineVault: currentResource.vaultContent || '{}',
        teamVault: teamData?.vaultContent || '{}',
        repositoryVault: repoData?.vaultContent || '{}'
      });

      const response = await createQueueItemMutation.mutateAsync({
        teamName: currentResource.teamName,
        machineName: currentResource.machineName,
        bridgeName: currentResource.bridgeName,
        queueVault,
        priority: functionData.priority
      });
      
      // Reset the modal
      closeUnifiedModal();
      
      // Automatically open the trace modal if queue item was created successfully
      if (response?.taskId) {
        showMessage('success', t('machines:queueItemCreated'));
        setQueueTraceModal({ visible: true, taskId: response.taskId });
      }
    } catch (error) {
      // Error is handled by the mutation
    }
  };

  // Handle function selection for repository
  const handleRepositoryFunctionSelected = async (functionData: {
    function: QueueFunction;
    params: Record<string, any>;
    priority: number;
    description: string;
    selectedMachine?: string;
  }) => {
    if (!currentResource || !functionData.selectedMachine) return;

    // Find the selected machine data
    const teamData = dropdownData?.machinesByTeam?.find(t => t.teamName === currentResource.teamName);
    const machine = teamData?.machines?.find(m => m.value === functionData.selectedMachine);
    
    if (!machine) {
      showMessage('error', 'Selected machine not found');
      return;
    }

    // Find the team vault data for the repository's team
    const repoTeamData = teamsList.find(t => t.teamName === currentResource.teamName)
    
    // Build the queue vault with context data
    const queueVault = await buildQueueVault({
      teamName: currentResource.teamName,
      machineName: machine.value,
      bridgeName: machine.bridgeName,
      repositoryName: currentResource.repositoryName,
      functionName: functionData.function.name,
      params: functionData.params, // Params already include repo from defaultParams
      priority: functionData.priority,
      description: functionData.description,
      addedVia: 'repository-table',
      // Pass vault data
      teamVault: repoTeamData?.vaultContent,
      // TODO: Machine vault not available in dropdown data (would need separate query)
      // machineVault: machineData?.vaultContent,
      // TODO: Repository vault not available in current interface
      // repositoryVault: currentResource.vaultContent
    });

    try {
      const response = await createQueueItemMutation.mutateAsync({
        teamName: currentResource.teamName,
        machineName: machine.value,
        bridgeName: machine.bridgeName,
        queueVault,
        priority: functionData.priority
      });
      
      // Reset the modal
      closeUnifiedModal();
      
      // Automatically open the trace modal if queue item was created successfully
      if (response?.taskId) {
        showMessage('success', t('repositories.queueItemCreated'));
        setQueueTraceModal({ visible: true, taskId: response.taskId });
      }
    } catch (error) {
      // Error is handled by the mutation
    }
  };




  // Repository columns
  const repositoryColumns = [
    {
      title: t('general.actions'),
      key: 'actions',
      width: 80,
      align: 'center' as const,
      fixed: 'left' as const,
      render: (_: any, record: Repository) => (
        <Dropdown
          menu={{
            items: [
              {
                key: 'vault',
                label: t('general.vault'),
                icon: <SettingOutlined />,
                onClick: () => {
                  setCurrentResource(record);
                  openUnifiedModal('repository', 'edit', record);
                },
              },
              {
                key: 'edit',
                label: t('general.edit'),
                icon: <EditOutlined />,
                onClick: () => {
                  setCurrentResource(record);
                  openUnifiedModal('repository', 'edit', record);
                },
              },
              {
                key: 'functions',
                label: t('repositories.repositoryFunctions'),
                icon: <FunctionOutlined />,
                onClick: () => {
                  setCurrentResource(record);
                  // Use a special state to show function selection
                  setUnifiedModalState({
                    open: true,
                    resourceType: 'repository',
                    mode: 'create',
                    data: record
                  });
                },
              },
              {
                type: 'divider',
              },
              {
                key: 'delete',
                label: t('general.delete'),
                icon: <DeleteOutlined />,
                danger: true,
                onClick: () => {
                  Modal.confirm({
                    title: t('repositories.deleteRepository'),
                    content: t('repositories.confirmDelete', { repositoryName: record.repositoryName }),
                    okText: t('general.yes'),
                    okType: 'danger',
                    cancelText: t('general.no'),
                    onOk: () => handleDeleteRepository(record),
                  });
                },
              },
            ],
          }}
          trigger={['click']}
        >
          <Button type="text" icon={<MoreOutlined />} />
        </Dropdown>
      ),
    },
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
      render: (teamName: string) => <Tag color="#8FBC8F">{teamName}</Tag>,
    },
    ...(uiMode === 'expert' ? [{
      title: t('general.vaultVersion'),
      dataIndex: 'vaultVersion',
      key: 'vaultVersion',
      width: 100,
      align: 'center' as const,
      render: (version: number) => <Tag>{t('common:general.versionFormat', { version })}</Tag>,
    }] : []),
  ]

  // Storage columns
  const storageColumns = [
    {
      title: t('general.actions'),
      key: 'actions',
      width: 80,
      align: 'center' as const,
      fixed: 'left' as const,
      render: (_: any, record: Storage) => (
        <Dropdown
          menu={{
            items: [
              {
                key: 'vault',
                label: t('general.vault'),
                icon: <SettingOutlined />,
                onClick: () => {
                  setCurrentResource(record);
                  openUnifiedModal('storage', 'edit', record);
                },
              },
              {
                key: 'edit',
                label: t('general.edit'),
                icon: <EditOutlined />,
                onClick: () => {
                  setCurrentResource(record);
                  openUnifiedModal('storage', 'edit', record);
                },
              },
              {
                type: 'divider',
              },
              {
                key: 'delete',
                label: t('general.delete'),
                icon: <DeleteOutlined />,
                danger: true,
                onClick: () => {
                  Modal.confirm({
                    title: t('storage.deleteStorage'),
                    content: t('storage.confirmDelete', { storageName: record.storageName }),
                    okText: t('general.yes'),
                    okType: 'danger',
                    cancelText: t('general.no'),
                    onOk: () => handleDeleteStorage(record),
                  });
                },
              },
            ],
          }}
          trigger={['click']}
        >
          <Button type="text" icon={<MoreOutlined />} />
        </Dropdown>
      ),
    },
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
      render: (teamName: string) => <Tag color="#8FBC8F">{teamName}</Tag>,
    },
    ...(uiMode === 'expert' ? [{
      title: t('general.vaultVersion'),
      dataIndex: 'vaultVersion',
      key: 'vaultVersion',
      width: 100,
      align: 'center' as const,
      render: (version: number) => <Tag>{t('common:general.versionFormat', { version })}</Tag>,
    }] : []),
  ]

  // Schedule columns
  const scheduleColumns = [
    {
      title: t('general.actions'),
      key: 'actions',
      width: 80,
      align: 'center' as const,
      fixed: 'left' as const,
      render: (_: any, record: Schedule) => (
        <Dropdown
          menu={{
            items: [
              {
                key: 'vault',
                label: t('general.vault'),
                icon: <SettingOutlined />,
                onClick: () => {
                  setCurrentResource(record);
                  openUnifiedModal('schedule', 'edit', record);
                },
              },
              {
                key: 'edit',
                label: t('general.edit'),
                icon: <EditOutlined />,
                onClick: () => {
                  setCurrentResource(record);
                  openUnifiedModal('schedule', 'edit', record);
                },
              },
              {
                type: 'divider',
              },
              {
                key: 'delete',
                label: t('general.delete'),
                icon: <DeleteOutlined />,
                danger: true,
                onClick: () => {
                  Modal.confirm({
                    title: t('schedules.deleteSchedule'),
                    content: t('schedules.confirmDelete', { scheduleName: record.scheduleName }),
                    okText: t('general.yes'),
                    okType: 'danger',
                    cancelText: t('general.no'),
                    onOk: () => handleDeleteSchedule(record),
                  });
                },
              },
            ],
          }}
          trigger={['click']}
        >
          <Button type="text" icon={<MoreOutlined />} />
        </Dropdown>
      ),
    },
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
      render: (teamName: string) => <Tag color="#8FBC8F">{teamName}</Tag>,
    },
    ...(uiMode === 'expert' ? [{
      title: t('general.vaultVersion'),
      dataIndex: 'vaultVersion',
      key: 'vaultVersion',
      width: 100,
      align: 'center' as const,
      render: (version: number) => <Tag>{t('common:general.versionFormat', { version })}</Tag>,
    }] : []),
  ]

  // Check if we're currently submitting or updating vault
  const isSubmitting = createRepositoryMutation.isPending || 
                      updateRepositoryNameMutation.isPending ||
                      createStorageMutation.isPending ||
                      updateStorageNameMutation.isPending ||
                      createScheduleMutation.isPending ||
                      updateScheduleNameMutation.isPending ||
                      createQueueItemMutation.isPending
                      
  const isUpdatingVault = updateRepositoryVaultMutation.isPending ||
                         updateStorageVaultMutation.isPending ||
                         updateScheduleVaultMutation.isPending

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
          onCreateMachine={() => openUnifiedModal('machine', 'create')}
          onEditMachine={(machine) => {
            setCurrentResource(machine)
            openUnifiedModal('machine', 'edit', machine)
          }}
          onVaultMachine={(machine) => {
            setCurrentResource(machine)
            openUnifiedModal('machine', 'edit', machine)
          }}
          onFunctionsMachine={(machine) => {
            setCurrentResource(machine)
            setUnifiedModalState({
              open: true,
              resourceType: 'machine',
              mode: 'create',
              data: machine
            })
          }}
          onDeleteMachine={handleDeleteMachine}
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
      children: (
        <div ref={repositoryTableRef} style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
          {repositoriesLoading ? (
            <div style={{ textAlign: 'center', padding: '100px 0' }}>
              <Spin size="large" tip={t('common:general.loading')} />
            </div>
          ) : repositories.length === 0 ? (
            <Empty
              description={t('repositories.noRepositories')}
              style={{ margin: 'auto' }}
            />
          ) : (
            <Table
              columns={repositoryColumns}
              dataSource={repositories}
              rowKey="repositoryName"
              scroll={{ x: 'max-content' }}
              pagination={{
                total: repositories?.length || 0,
                pageSize: repositoryPageSize,
                showSizeChanger: false,
                showTotal: (total, range) => `${t('common:general.showingRecords', { start: range[0], end: range[1], total })}`,
                position: ['bottomRight'],
              }}
              style={{ flex: 1 }}
              sticky
            />
          )}
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
      children: (
        <div ref={storageTableRef} style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
          {storagesLoading ? (
            <div style={{ textAlign: 'center', padding: '100px 0' }}>
              <Spin size="large" tip={t('common:general.loading')} />
            </div>
          ) : storages.length === 0 ? (
            <Empty
              description={t('storage.noStorage')}
              style={{ margin: 'auto' }}
            />
          ) : (
            <Table
              columns={storageColumns}
              dataSource={storages}
              rowKey="storageName"
              scroll={{ x: 'max-content' }}
              pagination={{
                total: storages?.length || 0,
                pageSize: storagePageSize,
                showSizeChanger: false,
                showTotal: (total, range) => `${t('common:general.showingRecords', { start: range[0], end: range[1], total })}`,
                position: ['bottomRight'],
              }}
              style={{ flex: 1 }}
              sticky
            />
          )}
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
      children: (
        <div ref={scheduleTableRef} style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
          {schedulesLoading ? (
            <div style={{ textAlign: 'center', padding: '100px 0' }}>
              <Spin size="large" tip={t('common:general.loading')} />
            </div>
          ) : schedules.length === 0 ? (
            <Empty
              description={t('schedules.noSchedules')}
              style={{ margin: 'auto' }}
            />
          ) : (
            <Table
              columns={scheduleColumns}
              dataSource={schedules}
              rowKey="scheduleName"
              scroll={{ x: 'max-content' }}
              pagination={{
                total: schedules?.length || 0,
                pageSize: schedulePageSize,
                showSizeChanger: false,
                showTotal: (total, range) => `${t('common:general.showingRecords', { start: range[0], end: range[1], total })}`,
                position: ['bottomRight'],
              }}
              style={{ flex: 1 }}
              sticky
            />
          )}
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
          <Col span={24} style={{ height: '100%' }}>
            <Card style={cardStyle} bodyStyle={cardBodyStyle}>
              <div style={{ marginBottom: 16 }}>
                <div style={{ 
                  display: 'flex', 
                  alignItems: 'center', 
                  justifyContent: 'space-between',
                  flexWrap: 'wrap',
                  gap: 16
                }}>
                  <div style={{ 
                    display: 'flex', 
                    alignItems: 'center', 
                    gap: 16,
                    flex: '1 1 auto',
                    minWidth: 0
                  }}>
                    <Title level={4} style={{ margin: 0, flexShrink: 0 }}>
                      {t('teams.teamResources')}
                    </Title>
                    <TeamSelector
                      teams={teamsList}
                      selectedTeams={selectedTeams}
                      onChange={setSelectedTeams}
                      loading={teamsLoading}
                      placeholder={t('teams.selectTeamToView')}
                      style={{ 
                        minWidth: 250, 
                        maxWidth: 400,
                        width: '100%'
                      }}
                    />
                  </div>
                  
                  {selectedTeams.length > 0 && (
                    <div style={{ 
                      display: 'flex',
                      gap: 8,
                      flexShrink: 0
                    }}>
                      <Button 
                        type="primary" 
                        icon={<PlusOutlined />}
                        onClick={() => {
                          switch(teamResourcesTab) {
                            case 'machines':
                              openUnifiedModal('machine', 'create')
                              break
                            case 'repositories':
                              openUnifiedModal('repository', 'create')
                              break
                            case 'storage':
                              openUnifiedModal('storage', 'create')
                              break
                            case 'schedules':
                              openUnifiedModal('schedule', 'create')
                              break
                          }
                        }}
                        style={{ background: '#556b2f', borderColor: '#556b2f' }}
                      >
                        {getCreateButtonText()}
                      </Button>
                    </div>
                  )}
                </div>
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
                  style={{ flex: 1, display: 'flex', flexDirection: 'column' }}
                  className="full-height-tabs"
                />
              )}
            </Card>
          </Col>
        </Row>
      ) : (
        <Row gutter={24} style={containerStyle}>
          <Col span={24} style={{ height: '100%' }}>
            <Card style={cardStyle} bodyStyle={cardBodyStyle}>
              <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0 }}>
                <div>
                  <Title level={4} style={{ margin: 0 }}>
                    {t('teams.teamResources')}
                  </Title>
                </div>
                <Space>
                  {(
                    <Button 
                      type="primary" 
                      icon={<PlusOutlined />}
                      onClick={() => {
                        switch(teamResourcesTab) {
                          case 'machines':
                            openUnifiedModal('machine', 'create')
                            break
                          case 'storage':
                            openUnifiedModal('storage', 'create')
                            break
                        }
                      }}
                      style={{ background: '#556b2f', borderColor: '#556b2f' }}
                    >
                      {getCreateButtonText()}
                    </Button>
                  )}
                </Space>
              </div>
              
              <Tabs
                activeKey={teamResourcesTab}
                onChange={setTeamResourcesTab}
                items={teamResourcesTabs.filter(tab => tab.key !== 'schedules')}
                style={{ flex: 1, display: 'flex', flexDirection: 'column' }}
                className="full-height-tabs"
              />
            </Card>
          </Col>
        </Row>
      )}





      {/* Unified Resource Modal */}
      <UnifiedResourceModal
        open={unifiedModalState.open}
        onCancel={closeUnifiedModal}
        resourceType={unifiedModalState.resourceType}
        mode={unifiedModalState.mode}
        existingData={unifiedModalState.data || currentResource}
        teamFilter={selectedTeams.length > 0 ? selectedTeams : undefined}
        onSubmit={handleUnifiedModalSubmit}
        onUpdateVault={unifiedModalState.mode === 'edit' ? handleUnifiedVaultUpdate : undefined}
        onFunctionSubmit={
          unifiedModalState.data && 
          (unifiedModalState.resourceType === 'machine' || unifiedModalState.resourceType === 'repository')
            ? unifiedModalState.resourceType === 'machine' 
              ? handleMachineFunctionSelected 
              : handleRepositoryFunctionSelected
            : undefined
        }
        isSubmitting={isSubmitting}
        isUpdatingVault={isUpdatingVault}
        functionCategories={
          unifiedModalState.resourceType === 'machine' ? ['machine'] :
          unifiedModalState.resourceType === 'repository' ? ['repository', 'backup', 'network'] : 
          []
        }
        hiddenParams={unifiedModalState.resourceType === 'repository' ? ['repo'] : []}
        defaultParams={unifiedModalState.resourceType === 'repository' && currentResource ? { repo: currentResource.repositoryName } : {}}
      />

      {/* Queue Item Trace Modal */}
      <QueueItemTraceModal
        taskId={queueTraceModal.taskId}
        visible={queueTraceModal.visible}
        onClose={() => setQueueTraceModal({ visible: false, taskId: null })}
      />
    </>
  )
}

export default ResourcesPage