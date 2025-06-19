import React, { useState, useRef } from 'react'
import { Card, Tabs, Button, Space, Modal, Tag, Typography, Table, Row, Col, Empty, Spin } from 'antd'
import { 
  PlusOutlined, 
  EditOutlined, 
  DeleteOutlined,
  CloudOutlined,
  InboxOutlined,
  DesktopOutlined,
  ScheduleOutlined,
  FunctionOutlined,
  WifiOutlined,
  HistoryOutlined
} from '@ant-design/icons'
import { useTranslation } from 'react-i18next'
import { useSelector } from 'react-redux'
import { RootState } from '@/store/store'
import UnifiedResourceModal, { ResourceType } from '@/components/common/UnifiedResourceModal'
import QueueItemTraceModal from '@/components/common/QueueItemTraceModal'
import ConnectivityTestModal from '@/components/common/ConnectivityTestModal'
import AuditTraceModal from '@/components/common/AuditTraceModal'
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
  useMachines
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
import { useManagedQueueItem } from '@/hooks/useManagedQueueItem'
import TeamSelector from '@/components/common/TeamSelector'
import { useQueueVaultBuilder } from '@/hooks/useQueueVaultBuilder'
import { type Machine } from '@/types'
import apiClient from '@/api/client'

const { Title } = Typography

const ResourcesPage: React.FC = () => {
  const { t } = useTranslation(['resources', 'machines', 'common'])
  const uiMode = useSelector((state: RootState) => state.ui.uiMode)
  const [selectedTeams, setSelectedTeams] = useState<string[]>([])
  const [teamResourcesTab, setTeamResourcesTab] = useState('machines')
  
  // Unified modal state
  const [unifiedModalState, setUnifiedModalState] = useState<{
    open: boolean
    resourceType: ResourceType
    mode: 'create' | 'edit' | 'vault'
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
      case 'repositories': return t('repositories.createRepository')
      case 'storage': return t('storage.createStorage')
      case 'schedules': return t('schedules.createSchedule')
      default: return t('general.create')
    }
  }

  // State for current editing/creating resource
  const [currentResource, setCurrentResource] = useState<any>(null)
  
  // Machine mutations
  const createMachineMutation = useCreateMachine()
  const updateMachineNameMutation = useUpdateMachineName()
  const updateMachineBridgeMutation = useUpdateMachineBridge()
  const deleteMachineMutation = useDeleteMachine()
  const updateMachineVaultMutation = useUpdateMachineVault()
  
  // Generic delete handler
  const handleDelete = async (resourceType: ResourceType, resource: any) => {
    const resourceName = resource[`${resourceType}Name`]
    const mutations = {
      machine: deleteMachineMutation,
      repository: deleteRepositoryMutation,
      storage: deleteStorageMutation,
      schedule: deleteScheduleMutation
    }
    
    // Get the correct translation namespace and key
    const getTranslationKey = (key: string) => {
      if (resourceType === 'machine') {
        return `machines:${key}`
      }
      const resourceKey = resourceType === 'repository' ? 'repositories' : `${resourceType}s`
      return `resources:${resourceKey}.${key}`
    }
    
    Modal.confirm({
      title: t(getTranslationKey(resourceType === 'machine' ? 'confirmDelete' : `delete${resourceType.charAt(0).toUpperCase() + resourceType.slice(1)}`)),
      content: t(getTranslationKey(resourceType === 'machine' ? 'deleteWarning' : 'confirmDelete'), { 
        name: resourceName,
        [`${resourceType}Name`]: resourceName 
      }),
      okText: t('common:actions.delete'),
      okType: 'danger',
      cancelText: t('common:actions.cancel'),
      onOk: async () => {
        try {
          const mutation = mutations[resourceType as keyof typeof mutations]
          if (resourceType === 'machine') {
            await mutation.mutateAsync({
              teamName: resource.teamName,
              machineName: resourceName,
            } as any)
          } else if (resourceType === 'repository') {
            await mutation.mutateAsync({
              teamName: resource.teamName,
              repositoryName: resourceName,
            } as any)
          } else if (resourceType === 'storage') {
            await mutation.mutateAsync({
              teamName: resource.teamName,
              storageName: resourceName,
            } as any)
          } else if (resourceType === 'schedule') {
            await mutation.mutateAsync({
              teamName: resource.teamName,
              scheduleName: resourceName,
            } as any)
          }
          showMessage('success', t(getTranslationKey('deleteSuccess')))
        } catch (error) {
          showMessage('error', t(getTranslationKey('deleteError')))
        }
      },
    })
  }
  
  // Specific delete handlers using generic function
  const handleDeleteMachine = (machine: Machine) => handleDelete('machine', machine)

  // Common hooks
  const { data: dropdownData } = useDropdownData()

  // Team hooks
  const { data: teams, isLoading: teamsLoading } = useTeams()
  const teamsList: Team[] = teams || []
  
  // Machine hooks - fetch machines for connectivity test and repository creation
  const { data: machines = [] } = useMachines(
    selectedTeams.length > 0 && (teamResourcesTab === 'machines' || teamResourcesTab === 'repositories') ? selectedTeams : undefined,
    teamResourcesTab === 'machines' || teamResourcesTab === 'repositories'
  )



  // Repository hooks - fetch repositories when we have selected teams (needed for machine functions too)
  const { data: repositories = [], isLoading: repositoriesLoading } = useRepositories(
    selectedTeams.length > 0 ? selectedTeams : undefined
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
  
  // Queue mutation - using managed version for high-priority handling
  const createQueueItemMutation = useManagedQueueItem()
  const { buildQueueVault } = useQueueVaultBuilder()
  
  // Queue trace modal state
  const [queueTraceModal, setQueueTraceModal] = useState<{
    visible: boolean
    taskId: string | null
  }>({ visible: false, taskId: null })
  
  // Connectivity test modal state
  const [connectivityTestModal, setConnectivityTestModal] = useState(false)
  
  // Audit trace modal state
  const [auditTraceModal, setAuditTraceModal] = useState<{
    open: boolean
    entityType: string | null
    entityIdentifier: string | null
    entityName?: string
  }>({ open: false, entityType: null, entityIdentifier: null })
  
  // Dynamic page sizes for tables
  const repositoryPageSize = useDynamicPageSize(repositoryTableRef, {
    containerOffset: 220, // Account for tab headers, pagination, and padding
    minRows: 5,
    maxRows: 50,
    rowHeight: 55 // Typical row height with padding
  })
  
  const storagePageSize = useDynamicPageSize(storageTableRef, {
    containerOffset: 220,
    minRows: 5,
    maxRows: 50,
    rowHeight: 55
  })
  
  const schedulePageSize = useDynamicPageSize(scheduleTableRef, {
    containerOffset: 220,
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
  const openUnifiedModal = (resourceType: ResourceType, mode: 'create' | 'edit' | 'vault', data?: any) => {
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
      const { resourceType, mode } = unifiedModalState
      const mutations = {
        machine: { create: createMachineMutation, updateName: updateMachineNameMutation, updateVault: updateMachineVaultMutation },
        repository: { create: createRepositoryMutation, updateName: updateRepositoryNameMutation, updateVault: updateRepositoryVaultMutation },
        storage: { create: createStorageMutation, updateName: updateStorageNameMutation, updateVault: updateStorageVaultMutation },
        schedule: { create: createScheduleMutation, updateName: updateScheduleNameMutation, updateVault: updateScheduleVaultMutation }
      }
      
      if (mode === 'create') {
        // For repository creation, we need to handle the two-step process
        if (resourceType === 'repository' && data.machineName && data.size) {
          // Step 1: Create the repository credentials
          const { machineName, size, ...repoData } = data
          await mutations.repository.create.mutateAsync(repoData)
          
          // Step 2: Queue the "new" function to create the repository on the machine
          try {
            // Find the machine details
            const teamData = dropdownData?.machinesByTeam?.find(
              t => t.teamName === data.teamName
            )
            const machine = teamData?.machines?.find(
              m => m.value === machineName
            )
            
            if (!machine) {
              showMessage('error', 'Selected machine not found')
              closeUnifiedModal()
              return
            }
            
            // Find team vault data
            const team = teamsList.find(t => t.teamName === data.teamName)
            
            // Find the full machine data to get vault content
            const fullMachine = machines.find(m => m.machineName === machineName && m.teamName === data.teamName)
            
            // Wait a bit for the repository to be fully created and indexed
            await new Promise(resolve => setTimeout(resolve, 500))
            
            // Fetch the created repository to get its vault with credentials
            const repoResponse = await apiClient.get('/GetTeamRepositories', {
              teamName: data.teamName
            })
            
            // The repository data is in the second table (index 1)
            const createdRepo = repoResponse.tables[1]?.data?.find(
              (r: any) => r.repoName === data.repositoryName
            )
            
            const repositoryVault = createdRepo?.vaultContent || data.repositoryVault || '{}'
            const repositoryGuid = createdRepo?.repoGuid || ''
            
            
            if (!repositoryGuid) {
              showMessage('error', 'Failed to get repository GUID')
              closeUnifiedModal()
              return
            }
            
            // Build queue vault for the "new" function
            const queueVault = await buildQueueVault({
              teamName: data.teamName,
              machineName: machine.value,
              bridgeName: machine.bridgeName,
              functionName: 'new',
              params: {
                repo: repositoryGuid,  // Use repository GUID as value
                size: size
              },
              priority: 3,
              description: `Create repository ${data.repositoryName} with size ${size}`,
              addedVia: 'repository-creation',
              teamVault: team?.vaultContent || '{}',
              machineVault: fullMachine?.vaultContent || '{}',
              repositoryVault: repositoryVault,
              repositoryGuid: repositoryGuid
            })
            
            const response = await createQueueItemMutation.mutateAsync({
              teamName: data.teamName,
              machineName: machine.value,
              bridgeName: machine.bridgeName,
              queueVault,
              priority: 3
            })
            
            showMessage('success', t('repositories.createSuccess'))
            
            // Check if response has taskId (immediate submission) or queueId (queued)
            if (response?.taskId) {
              setQueueTraceModal({ visible: true, taskId: response.taskId })
            } else if (response?.isQueued) {
              // Item was queued, don't open trace modal yet
              showMessage('info', 'Repository creation queued for submission')
            }
          } catch (error) {
            showMessage('warning', t('repositories.repoCreatedButQueueFailed'))
          }
        } else {
          await mutations[resourceType as keyof typeof mutations].create.mutateAsync(data)
        }
      } else {
        const resourceName = `${resourceType}Name`
        const currentName = currentResource[resourceName]
        const newName = data[resourceName]
        
        // Update name if changed
        if (newName !== currentName) {
          const mutation = mutations[resourceType as keyof typeof mutations].updateName
          if (resourceType === 'machine') {
            await mutation.mutateAsync({
              teamName: currentResource.teamName,
              currentMachineName: currentName,
              newMachineName: newName,
            } as any)
          } else if (resourceType === 'repository') {
            await mutation.mutateAsync({
              teamName: currentResource.teamName,
              currentRepositoryName: currentName,
              newRepositoryName: newName,
            } as any)
          } else if (resourceType === 'storage') {
            await mutation.mutateAsync({
              teamName: currentResource.teamName,
              currentStorageName: currentName,
              newStorageName: newName,
            } as any)
          } else if (resourceType === 'schedule') {
            await mutation.mutateAsync({
              teamName: currentResource.teamName,
              currentScheduleName: currentName,
              newScheduleName: newName,
            } as any)
          }
        }
        
        // Update vault if changed
        const vaultData = data[`${resourceType}Vault`]
        if (vaultData && vaultData !== currentResource.vaultContent) {
          const vaultMutation = mutations[resourceType as keyof typeof mutations].updateVault
          if (resourceType === 'machine') {
            await vaultMutation.mutateAsync({
              teamName: currentResource.teamName,
              machineName: newName || currentName,
              machineVault: vaultData,
              vaultVersion: currentResource.vaultVersion + 1,
            } as any)
          } else if (resourceType === 'repository') {
            await vaultMutation.mutateAsync({
              teamName: currentResource.teamName,
              repositoryName: newName || currentName,
              repositoryVault: vaultData,
              vaultVersion: currentResource.vaultVersion + 1,
            } as any)
          } else if (resourceType === 'storage') {
            await vaultMutation.mutateAsync({
              teamName: currentResource.teamName,
              storageName: newName || currentName,
              storageVault: vaultData,
              vaultVersion: currentResource.vaultVersion + 1,
            } as any)
          } else if (resourceType === 'schedule') {
            await vaultMutation.mutateAsync({
              teamName: currentResource.teamName,
              scheduleName: newName || currentName,
              scheduleVault: vaultData,
              vaultVersion: currentResource.vaultVersion + 1,
            } as any)
          }
        }
        
        // Handle machine-specific bridge update
        if (resourceType === 'machine' && data.bridgeName !== currentResource.bridgeName) {
          await updateMachineBridgeMutation.mutateAsync({
            teamName: currentResource.teamName,
            machineName: newName || currentName,
            newBridgeName: data.bridgeName,
          })
        }
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
      const { resourceType } = unifiedModalState
      const mutations = {
        machine: updateMachineVaultMutation,
        repository: updateRepositoryVaultMutation,
        storage: updateStorageVaultMutation,
        schedule: updateScheduleVaultMutation
      }
      
      const mutation = mutations[resourceType as keyof typeof mutations]
      if (resourceType === 'machine') {
        await mutation.mutateAsync({
          teamName: currentResource.teamName,
          machineName: currentResource.machineName,
          machineVault: vault,
          vaultVersion: version,
        } as any)
      } else if (resourceType === 'repository') {
        await mutation.mutateAsync({
          teamName: currentResource.teamName,
          repositoryName: currentResource.repositoryName,
          repositoryVault: vault,
          vaultVersion: version,
        } as any)
      } else if (resourceType === 'storage') {
        await mutation.mutateAsync({
          teamName: currentResource.teamName,
          storageName: currentResource.storageName,
          storageVault: vault,
          vaultVersion: version,
        } as any)
      } else if (resourceType === 'schedule') {
        await mutation.mutateAsync({
          teamName: currentResource.teamName,
          scheduleName: currentResource.scheduleName,
          scheduleVault: vault,
          vaultVersion: version,
        } as any)
      }
    } catch (error) {
      // Error handled by mutation
    }
  }

  const handleDeleteRepository = (repository: Repository) => handleDelete('repository', repository)
  const handleDeleteStorage = (storage: Storage) => handleDelete('storage', storage)
  const handleDeleteSchedule = (schedule: Schedule) => handleDelete('schedule', schedule)

  // Generic function selection handler
  const handleResourceFunctionSelected = async (
    resourceType: 'machine' | 'repository' | 'storage',
    functionData: {
      function: QueueFunction;
      params: Record<string, any>;
      priority: number;
      description: string;
      selectedMachine?: string;
    }
  ) => {
    if (!currentResource) return;
    
    
    try {
      // Determine machine details
      let machineName: string;
      let bridgeName: string;
      
      if (resourceType === 'machine') {
        machineName = currentResource.machineName;
        bridgeName = currentResource.bridgeName;
        
        // Note: "new" function no longer creates repositories
        // Repositories should be created through the Repositories tab
      } else {
        if (!functionData.selectedMachine) return;
        
        const teamData = dropdownData?.machinesByTeam?.find(
          t => t.teamName === currentResource.teamName
        );
        const machine = teamData?.machines?.find(
          m => m.value === functionData.selectedMachine
        );
        
        if (!machine) {
          showMessage('error', 'Selected machine not found');
          return;
        }
        
        machineName = machine.value;
        bridgeName = machine.bridgeName;
      }
      
      // Find team vault data
      const teamData = teamsList.find(t => t.teamName === currentResource.teamName);
      
      // Build queue vault with dynamic resource name
      const queueVaultParams: any = {
        teamName: currentResource.teamName,
        machineName,
        bridgeName,
        functionName: functionData.function.name,
        params: functionData.params,
        priority: functionData.priority,
        description: functionData.description,
        addedVia: `${resourceType}-table`,
        teamVault: teamData?.vaultContent || '{}'
      };
      
      // Add resource-specific field and vault
      if (resourceType === 'machine') {
        queueVaultParams.machineVault = currentResource.vaultContent || '{}';
        
        // Find the repository vault data if repo is specified
        if (functionData.params.repo) {
          const repository = repositories.find(r => r.repositoryGuid === functionData.params.repo);
          queueVaultParams.repositoryGuid = repository?.repositoryGuid || functionData.params.repo;
          queueVaultParams.repositoryVault = repository?.vaultContent || '{}';
        } else {
          queueVaultParams.repositoryVault = '{}';
        }
      } else if (resourceType === 'repository') {
        queueVaultParams.repositoryGuid = currentResource.repositoryGuid;
        queueVaultParams.repositoryVault = currentResource.vaultContent || '{}';
      } else if (resourceType === 'storage') {
        queueVaultParams.storageName = currentResource.storageName;
      }
      
      const queueVault = await buildQueueVault(queueVaultParams);
      
      const response = await createQueueItemMutation.mutateAsync({
        teamName: currentResource.teamName,
        machineName,
        bridgeName,
        queueVault,
        priority: functionData.priority
      });
      
      closeUnifiedModal();
      
      if (response?.taskId) {
        showMessage('success', t(`${resourceType}s:queueItemCreated`));
        setQueueTraceModal({ visible: true, taskId: response.taskId });
      } else if (response?.isQueued) {
        // Item was queued for highest priority management
        showMessage('info', `Highest priority ${resourceType} function queued for submission`);
      }
    } catch (error) {
      // Error is handled by the mutation
    }
  };
  
  // Specific handlers using generic function
  const handleMachineFunctionSelected = (functionData: any) => 
    handleResourceFunctionSelected('machine', functionData);

  const handleRepositoryFunctionSelected = (functionData: any) => 
    handleResourceFunctionSelected('repository', functionData);
    
  const handleStorageFunctionSelected = (functionData: any) => 
    handleResourceFunctionSelected('storage', functionData);

  // Removed individual function handlers - now using generic handler above




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
    {
      title: t('common:table.actions'),
      key: 'actions',
      width: 250,
      render: (_: any, record: Repository) => (
        <Space>
          <Button
            type="primary"
            size="small"
            icon={<EditOutlined />}
            onClick={() => {
              setCurrentResource(record);
              openUnifiedModal('repository', 'edit', record);
            }}
          >
            {t('common:actions.edit')}
          </Button>
          <Button
            type="primary"
            size="small"
            icon={<HistoryOutlined />}
            onClick={() => {
              setAuditTraceModal({
                open: true,
                entityType: 'Repo',
                entityIdentifier: record.repositoryName,
                entityName: record.repositoryName
              });
            }}
          >
            {t('machines:trace')}
          </Button>
          <Button
            type="primary"
            danger
            size="small"
            icon={<DeleteOutlined />}
            onClick={() => {
              Modal.confirm({
                title: t('repositories.deleteRepository'),
                content: t('repositories.confirmDelete', { repositoryName: record.repositoryName }),
                okText: t('general.yes'),
                okType: 'danger',
                cancelText: t('general.no'),
                onOk: () => handleDeleteRepository(record),
              });
            }}
          >
            {t('common:actions.delete')}
          </Button>
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
    {
      title: t('common:table.actions'),
      key: 'actions',
      width: 350,
      render: (_: any, record: Storage) => (
        <Space>
          <Button
            type="primary"
            size="small"
            icon={<EditOutlined />}
            onClick={() => {
              setCurrentResource(record);
              openUnifiedModal('storage', 'edit', record);
            }}
          >
            {t('common:actions.edit')}
          </Button>
          <Button
            type="primary"
            size="small"
            icon={<FunctionOutlined />}
            onClick={() => {
              setCurrentResource(record);
              // Use a special state to show function selection
              setUnifiedModalState({
                open: true,
                resourceType: 'storage',
                mode: 'create',
                data: record
              });
            }}
          >
            Run
          </Button>
          <Button
            type="primary"
            size="small"
            icon={<HistoryOutlined />}
            onClick={() => {
              setAuditTraceModal({
                open: true,
                entityType: 'Storage',
                entityIdentifier: record.storageName,
                entityName: record.storageName
              });
            }}
          >
            {t('machines:trace')}
          </Button>
          <Button
            type="primary"
            danger
            size="small"
            icon={<DeleteOutlined />}
            onClick={() => {
              Modal.confirm({
                title: t('storage.deleteStorage'),
                content: t('storage.confirmDelete', { storageName: record.storageName }),
                okText: t('general.yes'),
                okType: 'danger',
                cancelText: t('general.no'),
                onOk: () => handleDeleteStorage(record),
              });
            }}
          >
            {t('common:actions.delete')}
          </Button>
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
    {
      title: t('common:table.actions'),
      key: 'actions',
      width: 250,
      render: (_: any, record: Schedule) => (
        <Space>
          <Button
            type="primary"
            size="small"
            icon={<EditOutlined />}
            onClick={() => {
              setCurrentResource(record);
              openUnifiedModal('schedule', 'edit', record);
            }}
          >
            {t('common:actions.edit')}
          </Button>
          <Button
            type="primary"
            size="small"
            icon={<HistoryOutlined />}
            onClick={() => {
              setAuditTraceModal({
                open: true,
                entityType: 'Schedule',
                entityIdentifier: record.scheduleName,
                entityName: record.scheduleName
              });
            }}
          >
            {t('machines:trace')}
          </Button>
          <Button
            type="primary"
            danger
            size="small"
            icon={<DeleteOutlined />}
            onClick={() => {
              Modal.confirm({
                title: t('schedules.deleteSchedule'),
                content: t('schedules.confirmDelete', { scheduleName: record.scheduleName }),
                okText: t('general.yes'),
                okType: 'danger',
                cancelText: t('general.no'),
                onOk: () => handleDeleteSchedule(record),
              });
            }}
          >
            {t('common:actions.delete')}
          </Button>
        </Space>
      ),
    },
  ]

  // Check if we're currently submitting or updating vault
  const isSubmitting = createMachineMutation.isPending ||
                      updateMachineNameMutation.isPending ||
                      updateMachineBridgeMutation.isPending ||
                      createRepositoryMutation.isPending || 
                      updateRepositoryNameMutation.isPending ||
                      createStorageMutation.isPending ||
                      updateStorageNameMutation.isPending ||
                      createScheduleMutation.isPending ||
                      updateScheduleNameMutation.isPending ||
                      createQueueItemMutation.isPending
                      
  const isUpdatingVault = updateMachineVaultMutation.isPending ||
                         updateRepositoryVaultMutation.isPending ||
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
            openUnifiedModal('machine', 'vault', machine)
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
          onCreateRepository={(machine) => {
            // Set the team filter to the machine's team
            if (machine.teamName !== selectedTeams[0]) {
              setSelectedTeams([machine.teamName])
            }
            // Open the repository creation modal with prefilled machine
            openUnifiedModal('repository', 'create', { 
              machineName: machine.machineName,
              teamName: machine.teamName,
              prefilledMachine: true 
            })
          }}
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
    height: 'calc(100vh - 64px - 48px)', // viewport - header - content margin
    overflow: 'hidden',
    display: 'flex',
    flexDirection: 'column'
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
                      {teamResourcesTab !== 'repositories' && (
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
                              case 'schedules':
                                openUnifiedModal('schedule', 'create')
                                break
                            }
                          }}
                          style={{ background: '#556b2f', borderColor: '#556b2f' }}
                        >
                          {getCreateButtonText()}
                        </Button>
                      )}
                      {teamResourcesTab === 'machines' && (
                        <Button 
                          icon={<WifiOutlined />}
                          onClick={() => setConnectivityTestModal(true)}
                          disabled={machines.length === 0}
                        >
                          Connectivity Test
                        </Button>
                      )}
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
                  {teamResourcesTab === 'machines' && (
                    <Button 
                      icon={<WifiOutlined />}
                      onClick={() => setConnectivityTestModal(true)}
                      disabled={machines.length === 0}
                    >
                      Connectivity Test
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
          (unifiedModalState.resourceType === 'machine' || unifiedModalState.resourceType === 'repository' || unifiedModalState.resourceType === 'storage')
            ? unifiedModalState.resourceType === 'machine' 
              ? handleMachineFunctionSelected 
              : unifiedModalState.resourceType === 'repository'
              ? handleRepositoryFunctionSelected
              : handleStorageFunctionSelected
            : undefined
        }
        isSubmitting={isSubmitting}
        isUpdatingVault={isUpdatingVault}
        functionCategories={
          unifiedModalState.resourceType === 'machine' ? ['machine'] :
          unifiedModalState.resourceType === 'repository' ? ['repository', 'backup', 'network'] : 
          unifiedModalState.resourceType === 'storage' ? ['backup'] :
          []
        }
        hiddenParams={
          unifiedModalState.resourceType === 'repository' ? ['repo', 'grand'] : 
          unifiedModalState.resourceType === 'storage' ? ['storage'] : 
          []
        }
        defaultParams={
          unifiedModalState.resourceType === 'repository' && currentResource ? { 
            repo: currentResource.repositoryGuid,
            grand: currentResource.grandGuid || ''
          } : 
          unifiedModalState.resourceType === 'storage' && currentResource ? { storage: currentResource.storageName } : 
          {}
        }
      />

      {/* Queue Item Trace Modal */}
      <QueueItemTraceModal
        taskId={queueTraceModal.taskId}
        visible={queueTraceModal.visible}
        onClose={() => setQueueTraceModal({ visible: false, taskId: null })}
      />

      {/* Connectivity Test Modal */}
      <ConnectivityTestModal
        open={connectivityTestModal}
        onClose={() => setConnectivityTestModal(false)}
        machines={machines}
        teamFilter={selectedTeams}
      />

      {/* Audit Trace Modal */}
      <AuditTraceModal
        open={auditTraceModal.open}
        onCancel={() => setAuditTraceModal({ open: false, entityType: null, entityIdentifier: null })}
        entityType={auditTraceModal.entityType}
        entityIdentifier={auditTraceModal.entityIdentifier}
        entityName={auditTraceModal.entityName}
      />
    </>
  )
}

export default ResourcesPage