import React, { useState, useRef } from 'react'
import { Card, Tabs, Button, Space, Modal, Tag, Typography, Table, Row, Col, Empty, Spin, Tooltip } from 'antd'
import { useLocation } from 'react-router-dom'
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
  HistoryOutlined,
  ReloadOutlined,
  ImportOutlined
} from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { useSelector } from 'react-redux'
import { RootState } from '@/store/store'
import { useComponentStyles } from '@/hooks/useComponentStyles'
import { DESIGN_TOKENS, spacing } from '@/utils/styleConstants'
import UnifiedResourceModal, { ResourceType } from '@/components/common/UnifiedResourceModal'
import QueueItemTraceModal from '@/components/common/QueueItemTraceModal'
import ConnectivityTestModal from '@/components/common/ConnectivityTestModal'
import AuditTraceModal from '@/components/common/AuditTraceModal'
import RcloneImportWizard from '@/components/resources/RcloneImportWizard'
import { showMessage } from '@/utils/messages'

// Team queries
import { useTeams, Team } from '@/api/queries/teams'


// Machine queries
import { MachineTable } from '@/components/resources/MachineTable'
import { SplitResourceView } from '@/components/resources/SplitResourceView'
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
  const location = useLocation()
  const uiMode = useSelector((state: RootState) => state.ui.uiMode)
  const styles = useComponentStyles()
  const [selectedTeams, setSelectedTeams] = useState<string[]>([])
  const [teamResourcesTab, setTeamResourcesTab] = useState('machines')
  const [selectedMachine, setSelectedMachine] = useState<Machine | null>(null)
  const [selectedRepositoryFromMachine, setSelectedRepositoryFromMachine] = useState<Repository | null>(null)
  const [selectedContainerFromMachine, setSelectedContainerFromMachine] = useState<any | null>(null)
  
  // Unified modal state
  const [unifiedModalState, setUnifiedModalState] = useState<{
    open: boolean
    resourceType: ResourceType
    mode: 'create' | 'edit' | 'vault'
    data?: any
    preselectedFunction?: string
    creationContext?: 'credentials-only' | 'normal'
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

  // Helper to get resource translation key
  const getResourceTranslationKey = () => {
    switch(teamResourcesTab) {
      case 'machines': return 'machines'
      case 'repositories': return 'repositories'
      case 'storage': return 'storage'
      case 'schedules': return 'schedules'
      default: return teamResourcesTab
    }
  }

  // State for current editing/creating resource
  const [currentResource, setCurrentResource] = useState<any>(null)
  
  // State for machine table expanded rows and refresh keys
  const [expandedRowKeys, setExpandedRowKeys] = useState<string[]>([])
  const [refreshKeys, setRefreshKeys] = useState<Record<string, number>>({})
  
  // Handler for machine selection
  const handleMachineSelect = (machine: Machine | null) => {
    setSelectedMachine(machine)
    if (machine) {
      setSelectedRepositoryFromMachine(null) // Close repository panel
    }
  }
  
  // Handler for repository click from machine list
  const handleMachineRepositoryClick = (machine: Machine, repository: any) => {
    // Map repository data from MachineRepositoryList format to Repository type
    const mappedRepository: Repository = {
      repositoryName: repository.name,
      repositoryGuid: repository.originalGuid || repository.name, // Use GUID if available
      teamName: machine.teamName,
      vaultVersion: 0, // This will be updated from API data
      vaultContent: undefined,
      grandGuid: undefined
    }
    
    // Find the actual repository from the API data
    const actualRepository = repositories.find(r => 
      r.repositoryName === repository.name || 
      r.repositoryGuid === repository.originalGuid || 
      r.repositoryGuid === repository.name
    )
    
    if (actualRepository) {
      setSelectedRepositoryFromMachine(actualRepository)
      setSelectedMachine(null) // Close machine panel when repository is selected
    } else {
      // If we can't find the repository, still show what we have
      setSelectedRepositoryFromMachine(mappedRepository)
      setSelectedMachine(null) // Close machine panel when repository is selected
      setSelectedContainerFromMachine(null)
    }
  }
  
  // Handler for container click from machine list
  const handleMachineContainerClick = (machine: Machine, container: any) => {
    setSelectedMachine(null)
    setSelectedRepositoryFromMachine(null)
    setSelectedContainerFromMachine(container)
  }
  
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
            refetchMachines()
          } else if (resourceType === 'repository') {
            await mutation.mutateAsync({
              teamName: resource.teamName,
              repositoryName: resourceName,
            } as any)
            refetchRepositories()
          } else if (resourceType === 'storage') {
            await mutation.mutateAsync({
              teamName: resource.teamName,
              storageName: resourceName,
            } as any)
            refetchStorage()
          } else if (resourceType === 'schedule') {
            await mutation.mutateAsync({
              teamName: resource.teamName,
              scheduleName: resourceName,
            } as any)
            refetchSchedules()
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
  const { data: machines = [], refetch: refetchMachines } = useMachines(
    selectedTeams.length > 0 && (teamResourcesTab === 'machines' || teamResourcesTab === 'repositories') ? selectedTeams : undefined,
    teamResourcesTab === 'machines' || teamResourcesTab === 'repositories'
  )



  // Repository hooks - fetch repositories when we have selected teams (needed for machine functions too)
  const { data: repositories = [], isLoading: repositoriesLoading, refetch: refetchRepositories } = useRepositories(
    selectedTeams.length > 0 ? selectedTeams : undefined
  )
  const createRepositoryMutation = useCreateRepository()
  const updateRepositoryNameMutation = useUpdateRepositoryName()
  const deleteRepositoryMutation = useDeleteRepository()
  const updateRepositoryVaultMutation = useUpdateRepositoryVault()

  // Storage hooks - only fetch when storage tab is active
  const { data: storages = [], isLoading: storagesLoading, refetch: refetchStorage } = useStorage(
    selectedTeams.length > 0 && teamResourcesTab === 'storage' ? selectedTeams : undefined
  )
  const createStorageMutation = useCreateStorage()
  const updateStorageNameMutation = useUpdateStorageName()
  const deleteStorageMutation = useDeleteStorage()
  const updateStorageVaultMutation = useUpdateStorageVault()

  // Schedule hooks - only fetch when schedules tab is active
  const { data: schedules = [], isLoading: schedulesLoading, refetch: refetchSchedules } = useSchedules(
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
    machineName?: string | null
  }>({ visible: false, taskId: null, machineName: null })
  
  // Connectivity test modal state
  const [connectivityTestModal, setConnectivityTestModal] = useState(false)
  
  // Audit trace modal state
  const [auditTraceModal, setAuditTraceModal] = useState<{
    open: boolean
    entityType: string | null
    entityIdentifier: string | null
    entityName?: string
  }>({ open: false, entityType: null, entityIdentifier: null })
  
  // Rclone import wizard state
  const [rcloneImportWizardOpen, setRcloneImportWizardOpen] = useState(false)
  
  // Dynamic page sizes for resultSets
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

  // Handle navigation from marketplace
  React.useEffect(() => {
    if (location.state && (location.state as any).createRepository) {
      const state = location.state as any
      
      // Switch to repositories tab
      setTeamResourcesTab('repositories')
      
      // Set selected team if provided
      if (state.selectedTeam) {
        setSelectedTeams([state.selectedTeam])
      }
      
      // Open repository creation modal with pre-selected template
      setTimeout(() => {
        openUnifiedModal('repository', 'create', {
          teamName: state.selectedTeam,
          machineName: state.selectedMachine,
          preselectedTemplate: state.selectedTemplate
        })
      }, 100)
      
      // Clear navigation state
      window.history.replaceState({}, document.title)
    }
  }, [location])

  // Handler to open unified modal
  const openUnifiedModal = (resourceType: ResourceType, mode: 'create' | 'edit' | 'vault', data?: any, creationContext?: 'credentials-only' | 'normal') => {
    setUnifiedModalState({
      open: true,
      resourceType,
      mode,
      data,
      creationContext
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
        if (resourceType === 'repository') {
          // Check if this is credential-only mode (repositoryGuid is provided)
          const isCredentialOnlyMode = data.repositoryGuid && data.repositoryGuid.trim() !== ''
          
          // Check if we have machine and size for full repository creation
          if (data.machineName && data.size && !isCredentialOnlyMode) {
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
              showMessage('error', t('resources:errors.machineNotFound'))
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
            const createdRepo = repoResponse.resultSets[1]?.data?.find(
              (r: any) => r.repoName === data.repositoryName
            )
            
            const repositoryVault = createdRepo?.vaultContent || data.repositoryVault || '{}'
            const repositoryGuid = createdRepo?.repoGuid || ''
            
            
            if (!repositoryGuid) {
              showMessage('error', t('resources:errors.failedToGetRepositoryGuid'))
              closeUnifiedModal()
              return
            }
            
            // Build queue vault for the "new" function
            const params: any = {
              repo: repositoryGuid,  // Use repository GUID as value
              size: size
            }
            
            // Add template parameter if provided
            if (data.tmpl) {
              params.tmpl = data.tmpl
            }
            
            // Add keep_open parameter if provided
            if (data.keep_open) {
              params.keep_open = 'true'
            }
            
            const queueVault = await buildQueueVault({
              teamName: data.teamName,
              machineName: machine.value,
              bridgeName: machine.bridgeName,
              functionName: 'new',
              params: params,
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
              setQueueTraceModal({ visible: true, taskId: response.taskId, machineName: machine.value })
            } else if (response?.isQueued) {
              // Item was queued, don't open trace modal yet
              showMessage('info', t('resources:messages.repositoryCreationQueued'))
            }
            } catch (error) {
              showMessage('warning', t('repositories.repoCreatedButQueueFailed'))
            }
          } else {
            // Create repository credentials only (no machine provisioning)
            await mutations.repository.create.mutateAsync(data)
            showMessage('success', t('repositories.createSuccess'))
            closeUnifiedModal()
            // Refresh machines to show the new repository
            refetchMachines()
          }
        } else {
          // Handle machine creation with optional auto-setup
          if (resourceType === 'machine') {
            const { autoSetup, ...machineData } = data
            
            // Create the machine
            await mutations.machine.create.mutateAsync(machineData)
            showMessage('success', t('machines:createSuccess'))
            
            // If auto-setup is enabled, queue the setup function
            if (autoSetup) {
              try {
                // Find team vault data
                const team = teamsList.find(t => t.teamName === data.teamName)
                
                // Wait a bit for the machine to be fully created and indexed
                await new Promise(resolve => setTimeout(resolve, 500))
                
                // Build queue vault for the "setup" function
                const queueVault = await buildQueueVault({
                  teamName: data.teamName,
                  machineName: data.machineName,
                  bridgeName: data.bridgeName,
                  functionName: 'setup',
                  params: {
                    datastore_size: '95%',
                    source: 'apt-repo',
                    rclone_source: 'install-script',
                    docker_source: 'docker-repo',
                    install_amd_driver: 'auto',
                    install_nvidia_driver: 'auto'
                  },
                  priority: 3,
                  description: `Auto-setup for machine ${data.machineName}`,
                  addedVia: 'machine-creation-auto-setup',
                  teamVault: team?.vaultContent || '{}',
                  machineVault: data.machineVault || '{}'
                })
                
                const response = await createQueueItemMutation.mutateAsync({
                  teamName: data.teamName,
                  machineName: data.machineName,
                  bridgeName: data.bridgeName,
                  queueVault,
                  priority: 3
                })
                
                // Check if response has taskId (immediate submission) or queueId (queued)
                if (response?.taskId) {
                  showMessage('info', t('machines:setupQueued'))
                  setQueueTraceModal({ visible: true, taskId: response.taskId, machineName: data.machineName })
                } else if (response?.isQueued) {
                  showMessage('info', t('machines:setupQueuedForSubmission'))
                }
              } catch (error) {
                showMessage('warning', t('machines:machineCreatedButSetupFailed'))
              }
            }
            
            closeUnifiedModal()
            // Refresh machines
            refetchMachines()
          } else {
            // Handle other resource types
            await mutations[resourceType as keyof typeof mutations].create.mutateAsync(data)
            showMessage('success', t(`${getResourceTranslationKey()}.createSuccess`))
            closeUnifiedModal()
          }
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
          showMessage('error', t('resources:errors.machineNotFound'));
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
        // Also need machine vault for the selected machine
        const fullMachine = machines.find(m => m.machineName === machineName && m.teamName === currentResource.teamName);
        queueVaultParams.machineVault = fullMachine?.vaultContent || '{}';
      } else if (resourceType === 'storage') {
        queueVaultParams.storageName = currentResource.storageName;
        queueVaultParams.storageVault = currentResource.vaultContent || '{}';
        // Also need machine vault for the selected machine
        const fullMachine = machines.find(m => m.machineName === machineName && m.teamName === currentResource.teamName);
        queueVaultParams.machineVault = fullMachine?.vaultContent || '{}';
      }
      
      // Handle pull function source vault data
      if (functionData.function.name === 'pull') {
        // For pull from machine, get source machine vault data
        if (functionData.params.sourceType === 'machine' && functionData.params.from) {
          const sourceMachine = machines.find(m => m.machineName === functionData.params.from);
          if (sourceMachine && sourceMachine.vaultContent) {
            queueVaultParams.sourceMachineVault = sourceMachine.vaultContent;
          }
        }
        
        // For pull from storage, get source storage vault data
        if (functionData.params.sourceType === 'storage' && functionData.params.from) {
          const sourceStorage = storages.find(s => s.storageName === functionData.params.from);
          if (sourceStorage && sourceStorage.vaultContent) {
            queueVaultParams.sourceStorageVault = sourceStorage.vaultContent;
          }
        }
      }
      
      // Handle push function destination vault data
      if (functionData.function.name === 'push') {
        // For push to machine, get destination machine vault data
        if (functionData.params.destinationType === 'machine' && functionData.params.to) {
          const destinationMachine = machines.find(m => m.machineName === functionData.params.to);
          if (destinationMachine && destinationMachine.vaultContent) {
            queueVaultParams.destinationMachineVault = destinationMachine.vaultContent;
          }
        }
        
        // For push to storage, get destination storage vault data
        if (functionData.params.destinationType === 'storage' && functionData.params.to) {
          const destinationStorage = storages.find(s => s.storageName === functionData.params.to);
          if (destinationStorage && destinationStorage.vaultContent) {
            queueVaultParams.destinationStorageVault = destinationStorage.vaultContent;
          }
        }
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
        setQueueTraceModal({ visible: true, taskId: response.taskId, machineName: machineName });
      } else if (response?.isQueued) {
        // Item was queued for highest priority management
        showMessage('info', t('resources:messages.highestPriorityQueued', { resourceType }));
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
          <Tooltip title={t('common:actions.edit')}>
            <Button
              type="primary"
              size="small"
              icon={<EditOutlined />}
              style={styles.touchTargetSmall}
              data-testid={`resources-repository-edit-${record.repositoryName}`}
              onClick={() => {
                setCurrentResource(record);
                openUnifiedModal('repository', 'edit', record);
              }}
              aria-label={t('common:actions.edit')}
            />
          </Tooltip>
          <Tooltip title={t('machines:trace')}>
            <Button
              type="primary"
              size="small"
              icon={<HistoryOutlined />}
              style={styles.touchTargetSmall}
              data-testid={`resources-repository-trace-${record.repositoryName}`}
              onClick={() => {
                setAuditTraceModal({
                  open: true,
                  entityType: 'Repo',
                  entityIdentifier: record.repositoryName,
                  entityName: record.repositoryName
                });
              }}
              aria-label={t('machines:trace')}
            />
          </Tooltip>
          <Tooltip title={t('common:actions.delete')}>
            <Button
              type="primary"
              danger
              size="small"
              icon={<DeleteOutlined />}
              style={styles.touchTargetSmall}
              data-testid={`resources-repository-delete-${record.repositoryName}`}
              onClick={() => handleDeleteRepository(record)}
              aria-label={t('common:actions.delete')}
            />
          </Tooltip>
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
          <Tooltip title={t('common:actions.edit')}>
            <Button
              type="primary"
              size="small"
              icon={<EditOutlined />}
              style={styles.touchTargetSmall}
              data-testid={`resources-storage-edit-${record.storageName}`}
              onClick={() => {
                setCurrentResource(record);
                openUnifiedModal('storage', 'edit', record);
              }}
              aria-label={t('common:actions.edit')}
            />
          </Tooltip>
          <Tooltip title="Run">
            <Button
              type="primary"
              size="small"
              icon={<FunctionOutlined />}
              style={styles.touchTargetSmall}
              data-testid={`resources-storage-run-${record.storageName}`}
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
              aria-label="Run"
            />
          </Tooltip>
          <Tooltip title={t('machines:trace')}>
            <Button
              type="primary"
              size="small"
              icon={<HistoryOutlined />}
              style={styles.touchTargetSmall}
              data-testid={`resources-storage-trace-${record.storageName}`}
              onClick={() => {
                setAuditTraceModal({
                  open: true,
                  entityType: 'Storage',
                  entityIdentifier: record.storageName,
                  entityName: record.storageName
                });
              }}
              aria-label={t('machines:trace')}
            />
          </Tooltip>
          <Tooltip title={t('common:actions.delete')}>
            <Button
              type="primary"
              danger
              size="small"
              icon={<DeleteOutlined />}
              style={styles.touchTargetSmall}
              data-testid={`resources-storage-delete-${record.storageName}`}
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
              aria-label={t('common:actions.delete')}
            />
          </Tooltip>
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
          <Tooltip title={t('common:actions.edit')}>
            <Button
              type="primary"
              size="small"
              icon={<EditOutlined />}
              style={styles.touchTargetSmall}
              data-testid={`resources-schedule-edit-${record.scheduleName}`}
              onClick={() => {
                setCurrentResource(record);
                openUnifiedModal('schedule', 'edit', record);
              }}
              aria-label={t('common:actions.edit')}
            />
          </Tooltip>
          <Tooltip title={t('machines:trace')}>
            <Button
              type="primary"
              size="small"
              icon={<HistoryOutlined />}
              style={styles.touchTargetSmall}
              data-testid={`resources-schedule-trace-${record.scheduleName}`}
              onClick={() => {
                setAuditTraceModal({
                  open: true,
                  entityType: 'Schedule',
                  entityIdentifier: record.scheduleName,
                  entityName: record.scheduleName
                });
              }}
              aria-label={t('machines:trace')}
            />
          </Tooltip>
          <Tooltip title={t('common:actions.delete')}>
            <Button
              type="primary"
              danger
              size="small"
              icon={<DeleteOutlined />}
              style={styles.touchTargetSmall}
              data-testid={`resources-schedule-delete-${record.scheduleName}`}
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
              aria-label={t('common:actions.delete')}
            />
          </Tooltip>
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
        <Tooltip title={t('resourceTabs.machines')} placement="top">
          <span data-testid="resources-tab-machines">
            <DesktopOutlined style={{ fontSize: DESIGN_TOKENS.DIMENSIONS.ICON_MD }} />
          </span>
        </Tooltip>
      ),
      children: (
        <SplitResourceView
          type="machine" 
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
          onFunctionsMachine={(machine, functionName) => {
            setCurrentResource(machine)
            setUnifiedModalState({
              open: true,
              resourceType: 'machine',
              mode: 'create',
              data: machine,
              preselectedFunction: functionName
            })
            // Mark this machine for refresh when action completes
            setRefreshKeys(prev => ({
              ...prev,
              [machine.machineName]: Date.now()
            }))
          }}
          onDeleteMachine={handleDeleteMachine}
          onRefreshMachines={refetchMachines}
          onCreateRepository={(machine, repositoryGuid) => {
            // Set the team filter to the machine's team
            if (machine.teamName !== selectedTeams[0]) {
              setSelectedTeams([machine.teamName])
            }
            
            // For credential-only mode, start with empty vault so user must enter their own credential
            let vaultContent = undefined
            if (repositoryGuid) {
              vaultContent = JSON.stringify({ credential: '' })
            }
            
            // Open the repository creation modal with prefilled machine
            openUnifiedModal('repository', 'create', {
              machineName: machine.machineName,
              teamName: machine.teamName,
              prefilledMachine: true,
              repositoryGuid: repositoryGuid,  // Pass the GUID if provided
              vaultContent: vaultContent  // Pass default vault content for credential-only mode
            }, repositoryGuid ? 'credentials-only' : 'normal')  // Set creationContext based on repositoryGuid
          }}
          enabled={teamResourcesTab === 'machines'}
          className="full-height-machine-table"
          expandedRowKeys={expandedRowKeys}
          onExpandedRowsChange={setExpandedRowKeys}
          refreshKeys={refreshKeys}
          onQueueItemCreated={(taskId, machineName) => {
            setQueueTraceModal({ visible: true, taskId, machineName });
          }}
          selectedResource={selectedMachine || selectedRepositoryFromMachine || selectedContainerFromMachine}
          onResourceSelect={(resource) => {
            if (resource && 'machineName' in resource) {
              handleMachineSelect(resource as Machine)
            } else if (resource && 'repositoryName' in resource) {
              handleMachineSelect(null)
              setSelectedRepositoryFromMachine(resource as Repository)
              setSelectedContainerFromMachine(null)
            } else if (resource && 'id' in resource && 'state' in resource) {
              // Container
              handleMachineSelect(null)
              setSelectedRepositoryFromMachine(null)
              setSelectedContainerFromMachine(resource)
            } else {
              handleMachineSelect(null)
              setSelectedRepositoryFromMachine(null)
              setSelectedContainerFromMachine(null)
            }
          }}
          onMachineRepositoryClick={handleMachineRepositoryClick}
          onMachineContainerClick={handleMachineContainerClick}
        />
      ),
    },
    {
      key: 'repositories',
      label: (
        <Tooltip title={t('resourceTabs.repositories')} placement="top">
          <span data-testid="resources-tab-repositories">
            <InboxOutlined style={{ fontSize: DESIGN_TOKENS.DIMENSIONS.ICON_MD }} />
          </span>
        </Tooltip>
      ),
      children: (
        <div ref={repositoryTableRef} style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
          {repositoriesLoading ? (
            <div style={{ textAlign: 'center', padding: '100px 0' }}>
              <Spin size="large" />
              <div style={{ marginTop: 16, color: 'var(--ant-color-text-secondary)' }}>
                {t('common:general.loading')}
              </div>
            </div>
          ) : repositories.length === 0 ? (
            <Empty
              description={t('repositories.noRepositories')}
              style={{ margin: 'auto' }}
            />
          ) : (
            <Table
              data-testid="resources-repository-table"
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
        <Tooltip title={t('resourceTabs.storage')} placement="top">
          <span data-testid="resources-tab-storage">
            <CloudOutlined style={{ fontSize: DESIGN_TOKENS.DIMENSIONS.ICON_MD }} />
          </span>
        </Tooltip>
      ),
      children: (
        <div ref={storageTableRef} style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
          {storagesLoading ? (
            <div style={{ textAlign: 'center', padding: '100px 0' }}>
              <Spin size="large" />
              <div style={{ marginTop: 16, color: 'var(--ant-color-text-secondary)' }}>
                {t('common:general.loading')}
              </div>
            </div>
          ) : storages.length === 0 ? (
            <Empty
              description={t('storage.noStorage')}
              style={{ margin: 'auto' }}
            />
          ) : (
            <Table
              data-testid="resources-storage-table"
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
        <Tooltip title={t('resourceTabs.schedules')} placement="top">
          <span data-testid="resources-tab-schedules">
            <ScheduleOutlined style={{ fontSize: DESIGN_TOKENS.DIMENSIONS.ICON_MD }} />
          </span>
        </Tooltip>
      ),
      children: (
        <div ref={scheduleTableRef} style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
          {schedulesLoading ? (
            <div style={{ textAlign: 'center', padding: '100px 0' }}>
              <Spin size="large" />
              <div style={{ marginTop: 16, color: 'var(--ant-color-text-secondary)' }}>
                {t('common:general.loading')}
              </div>
            </div>
          ) : schedules.length === 0 ? (
            <Empty
              description={t('schedules.noSchedules')}
              style={{ margin: 'auto' }}
            />
          ) : (
            <Table
              data-testid="resources-schedule-table"
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

  // Calculate available height for full-height layout using design system
  const containerStyle: React.CSSProperties = {
    ...styles.container,
    height: 'calc(100vh - 64px - 48px)', // viewport - header - content margin
    overflow: 'hidden',
    ...styles.flexColumn
  }

  const cardStyle: React.CSSProperties = {
    ...styles.card,
    height: '100%',
    ...styles.flexColumn
  }

  const cardBodyStyle: React.CSSProperties = {
    flex: 1,
    overflow: 'hidden',
    ...styles.padding.md,
    ...styles.flexColumn
  }

  // Enhanced tab navigation with arrow keys for accessibility
  const handleTabKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
      event.preventDefault()
      const tabOrder = uiMode === 'simple' 
        ? ['machines', 'repositories', 'storage'] 
        : ['machines', 'repositories', 'storage', 'schedules']
      const currentIndex = tabOrder.indexOf(teamResourcesTab)
      
      if (event.key === 'ArrowLeft') {
        const newIndex = currentIndex > 0 ? currentIndex - 1 : tabOrder.length - 1
        setTeamResourcesTab(tabOrder[newIndex])
      } else {
        const newIndex = currentIndex < tabOrder.length - 1 ? currentIndex + 1 : 0
        setTeamResourcesTab(tabOrder[newIndex])
      }
    }
  }

  return (
    <>
      {uiMode !== 'simple' ? (
        <Row gutter={0} style={containerStyle}>
          <Col span={24} style={{ height: '100%' }}>
            <Card style={cardStyle} styles={{ body: cardBodyStyle }}>
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
                    <Title level={4} style={{ ...styles.heading4, margin: 0, flexShrink: 0 }}>
                      {t('teams.teamResources')}
                    </Title>
                    <TeamSelector
                      data-testid="resources-team-selector"
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
                      <Tooltip title={getCreateButtonText()}>
                        <Button 
                          type="primary" 
                          icon={<PlusOutlined />}
                          style={{
                            ...styles.buttonPrimary,
                            ...styles.touchTarget,
                            background: '#556b2f',
                            borderColor: '#556b2f'
                          }}
                          data-testid={`resources-create-${teamResourcesTab.slice(0, -1)}-button`}
                          onClick={() => {
                            switch(teamResourcesTab) {
                              case 'machines':
                                openUnifiedModal('machine', 'create')
                                break
                              case 'repositories':
                                openUnifiedModal('repository', 'create', undefined, 'credentials-only')
                                break
                              case 'storage':
                                openUnifiedModal('storage', 'create')
                                break
                              case 'schedules':
                                openUnifiedModal('schedule', 'create')
                                break
                            }
                          }}
                          aria-label={getCreateButtonText()}
                        />
                      </Tooltip>
                      {teamResourcesTab === 'storage' && (
                        <Tooltip title={t('resources:storage.import.button')}>
                          <Button
                            icon={<ImportOutlined />}
                            style={styles.touchTarget}
                            data-testid="resources-import-button"
                            onClick={() => setRcloneImportWizardOpen(true)}
                            aria-label={t('resources:storage.import.button')}
                          />
                        </Tooltip>
                      )}
                      {teamResourcesTab === 'machines' && (
                        <Tooltip title={t('machines:connectivityTest')}>
                          <Button 
                            icon={<WifiOutlined />}
                            style={styles.touchTarget}
                            data-testid="resources-connectivity-test-button"
                            onClick={() => setConnectivityTestModal(true)}
                            disabled={machines.length === 0}
                            aria-label={t('machines:connectivityTest')}
                          />
                        </Tooltip>
                      )}
                      <Tooltip title={t('common:actions.refresh')}>
                        <Button 
                          icon={<ReloadOutlined />}
                          style={styles.touchTarget}
                          data-testid="resources-refresh-button"
                          onClick={() => {
                            switch(teamResourcesTab) {
                              case 'machines':
                                refetchMachines()
                                // Also update refresh keys for expanded rows
                                setRefreshKeys(prev => ({
                                  ...prev,
                                  _global: Date.now()
                                }))
                                break
                              case 'repositories':
                                refetchRepositories()
                                break
                              case 'storage':
                                refetchStorage()
                                break
                              case 'schedules':
                                refetchSchedules()
                                break
                            }
                          }}
                          aria-label={t('common:actions.refresh')}
                        />
                      </Tooltip>
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
                  onKeyDown={handleTabKeyDown}
                  tabIndex={0}
                />
              )}
            </Card>
          </Col>
        </Row>
      ) : (
        <Row gutter={0} style={containerStyle}>
          <Col span={24} style={{ height: '100%' }}>
            <Card style={cardStyle} styles={{ body: cardBodyStyle }}>
              <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0 }}>
                <div>
                  <Title level={4} style={{ ...styles.heading4, margin: 0 }}>
                    {t('teams.teamResources')}
                  </Title>
                </div>
                <Space>
                  <Tooltip title={getCreateButtonText()}>
                    <Button 
                      type="primary" 
                      icon={<PlusOutlined />}
                      style={{
                        ...styles.buttonPrimary,
                        ...styles.touchTarget,
                        background: '#556b2f',
                        borderColor: '#556b2f'
                      }}
                      data-testid={`resources-create-${teamResourcesTab.slice(0, -1)}-button`}
                      onClick={() => {
                        switch(teamResourcesTab) {
                          case 'machines':
                            openUnifiedModal('machine', 'create')
                            break
                          case 'repositories':
                            openUnifiedModal('repository', 'create', undefined, 'credentials-only')
                            break
                          case 'storage':
                            openUnifiedModal('storage', 'create')
                            break
                        }
                      }}
                      aria-label={getCreateButtonText()}
                    />
                  </Tooltip>
                  {teamResourcesTab === 'storage' && (
                    <Tooltip title={t('resources:storage.import.button')}>
                      <Button
                        icon={<ImportOutlined />}
                        style={styles.touchTarget}
                        data-testid="resources-import-button"
                        onClick={() => setRcloneImportWizardOpen(true)}
                        aria-label={t('resources:storage.import.button')}
                      />
                    </Tooltip>
                  )}
                  {teamResourcesTab === 'machines' && (
                    <Tooltip title={t('machines:connectivityTest')}>
                      <Button 
                        icon={<WifiOutlined />}
                        style={styles.touchTarget}
                        data-testid="resources-connectivity-test-button"
                        onClick={() => setConnectivityTestModal(true)}
                        disabled={machines.length === 0}
                        aria-label={t('machines:connectivityTest')}
                      />
                    </Tooltip>
                  )}
                  <Tooltip title={t('common:actions.refresh')}>
                    <Button 
                      icon={<ReloadOutlined />}
                      style={styles.touchTarget}
                      data-testid="resources-refresh-button"
                      onClick={() => {
                        switch(teamResourcesTab) {
                          case 'machines':
                            refetchMachines()
                            // Also update refresh keys for expanded rows
                            setRefreshKeys(prev => ({
                              ...prev,
                              _global: Date.now()
                            }))
                            break
                          case 'repositories':
                            refetchRepositories()
                            break
                          case 'storage':
                            refetchStorage()
                            break
                        }
                      }}
                      aria-label={t('common:actions.refresh')}
                    />
                  </Tooltip>
                </Space>
              </div>
              
              <Tabs
                activeKey={teamResourcesTab}
                onChange={setTeamResourcesTab}
                items={teamResourcesTabs.filter(tab => tab.key !== 'schedules')}
                style={{ flex: 1, display: 'flex', flexDirection: 'column' }}
                className="full-height-tabs"
                onKeyDown={handleTabKeyDown}
                tabIndex={0}
              />
            </Card>
          </Col>
        </Row>
      )}





      {/* Unified Resource Modal */}
      <UnifiedResourceModal
        data-testid={`resources-${unifiedModalState.resourceType}-modal`}
        open={unifiedModalState.open}
        onCancel={closeUnifiedModal}
        resourceType={unifiedModalState.resourceType}
        mode={unifiedModalState.mode}
        existingData={unifiedModalState.data || currentResource}
        teamFilter={selectedTeams.length > 0 ? selectedTeams : undefined}
        creationContext={unifiedModalState.creationContext}
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
          unifiedModalState.resourceType === 'machine' ? ['machine', 'backup'] :
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
        preselectedFunction={unifiedModalState.preselectedFunction}
      />

      {/* Queue Item Trace Modal */}
      <QueueItemTraceModal
        data-testid="resources-queue-trace-modal"
        taskId={queueTraceModal.taskId}
        visible={queueTraceModal.visible}
        onClose={() => {
          setQueueTraceModal({ visible: false, taskId: null, machineName: null })
          // If we know the specific machine, refresh its data
          if (queueTraceModal.machineName) {
            setRefreshKeys(prev => ({
              ...prev,
              [queueTraceModal.machineName]: Date.now()
            }))
          } else {
            // Otherwise refresh all expanded machines
            setRefreshKeys(prev => {
              const newKeys = { ...prev }
              expandedRowKeys.forEach(key => {
                newKeys[key] = Date.now()
              })
              return newKeys
            })
          }
          // Refresh machines data to update repository lists
          refetchMachines()
        }}
      />

      {/* Connectivity Test Modal */}
      <ConnectivityTestModal
        data-testid="resources-connectivity-test-modal"
        open={connectivityTestModal}
        onClose={() => setConnectivityTestModal(false)}
        machines={machines}
        teamFilter={selectedTeams}
      />

      {/* Audit Trace Modal */}
      <AuditTraceModal
        data-testid="resources-audit-trace-modal"
        open={auditTraceModal.open}
        onCancel={() => setAuditTraceModal({ open: false, entityType: null, entityIdentifier: null })}
        entityType={auditTraceModal.entityType}
        entityIdentifier={auditTraceModal.entityIdentifier}
        entityName={auditTraceModal.entityName}
      />

      {/* Rclone Import Wizard */}
      <RcloneImportWizard
        data-testid="resources-rclone-import-wizard"
        open={rcloneImportWizardOpen}
        onClose={() => setRcloneImportWizardOpen(false)}
        teamName={selectedTeams[0] || ''}
        onImportComplete={() => {
          refetchStorage()
          showMessage('success', t('resources:storage.import.successMessage'))
        }}
      />
    </>
  )
}

export default ResourcesPage