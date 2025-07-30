import React, { useEffect, useState } from 'react'
import { Table, Spin, Alert, Tag, Space, Typography, Button, Dropdown, Empty, Card, Row, Col, Progress } from 'antd'
import { InboxOutlined, CheckCircleOutlined, FunctionOutlined, PlayCircleOutlined, StopOutlined, ExpandOutlined, CloudUploadOutlined, CloudDownloadOutlined, PauseCircleOutlined, ReloadOutlined, DeleteOutlined, FileTextOutlined, LineChartOutlined, DesktopOutlined, ClockCircleOutlined, DatabaseOutlined, HddOutlined, ApiOutlined, DisconnectOutlined, GlobalOutlined, KeyOutlined, AppstoreOutlined, CloudServerOutlined, RightOutlined } from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { type QueueFunction } from '@/api/queries/queue'
import { useQueueVaultBuilder } from '@/hooks/useQueueVaultBuilder'
import { useManagedQueueItem } from '@/hooks/useManagedQueueItem'
import { Machine } from '@/types'
import { useTeams } from '@/api/queries/teams'
import { useRepositories, useCreateRepository, useDeleteRepository } from '@/api/queries/repositories'
import { useMachines } from '@/api/queries/machines'
import { useStorage } from '@/api/queries/storage'
import type { ColumnsType } from 'antd/es/table'
import FunctionSelectionModal from '@/components/common/FunctionSelectionModal'
import QueueItemTraceModal from '@/components/common/QueueItemTraceModal'
import { LocalActionsMenu } from './LocalActionsMenu'
import { showMessage } from '@/utils/messages'
import { tokenService } from '@/services/tokenService'
import { useAppSelector } from '@/store/store'
import { getLocalizedRelativeTime } from '@/utils/timeUtils'

const { Text } = Typography

interface Repository {
  name: string
  size: number
  size_human: string
  modified: number
  modified_human: string
  mounted: boolean
  mount_path: string
  image_path: string
  accessible: boolean
  has_rediaccfile: boolean
  docker_running: boolean
  container_count: number
  plugin_count: number
  has_services: boolean
  service_count: number
  isUnmapped?: boolean  // True when showing GUID instead of name
  originalGuid?: string // The original GUID when unmapped
  disk_space?: {
    total: string
    used: string
    available: string
    use_percent: string
  }
}

interface SystemInfo {
  hostname: string
  kernel: string
  os_name: string
  uptime: string
  system_time: number
  system_time_human: string
  timezone: string
  cpu_count: number
  cpu_model: string
  memory: {
    total: string
    used: string
    available: string
  }
  disk: {
    total: string
    used: string
    available: string
    use_percent: string
  }
  datastore: {
    path: string
    total: string
    used: string
    available: string
    use_percent: string
  }
}

interface MachineRepositoryListProps {
  machine: Machine
  onActionComplete?: () => void
  hideSystemInfo?: boolean
  onCreateRepository?: (machine: Machine, repositoryGuid: string) => void
  onRepositoryClick?: (repository: Repository) => void
  highlightedRepository?: Repository | null
  onContainerClick?: (container: any) => void
  highlightedContainer?: any | null
  isLoading?: boolean
  onRefreshMachines?: () => Promise<any>
}


export const MachineRepositoryList: React.FC<MachineRepositoryListProps> = ({ machine, onActionComplete, hideSystemInfo = false, onCreateRepository, onRepositoryClick, highlightedRepository, onContainerClick, highlightedContainer, isLoading, onRefreshMachines }) => {
  const { t } = useTranslation(['resources', 'common', 'machines', 'functions'])
  const userEmail = useAppSelector((state) => state.auth.user?.email || '')
  const [currentToken, setCurrentToken] = useState<string>('')
  const [repositories, setRepositories] = useState<Repository[]>([])
  const [systemContainers, setSystemContainers] = useState<any[]>([])
  const [systemInfo, setSystemInfo] = useState<SystemInfo | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedRepository, setSelectedRepository] = useState<Repository | null>(null)
  const [functionModalOpen, setFunctionModalOpen] = useState(false)
  const [selectedFunction, setSelectedFunction] = useState<string | null>(null)
  const [queueTraceModal, setQueueTraceModal] = useState<{
    visible: boolean
    taskId: string | null
  }>({ visible: false, taskId: null })
  const [expandedRows, setExpandedRows] = useState<string[]>([])
  const [servicesData, setServicesData] = useState<Record<string, any>>({})
  const [containersData, setContainersData] = useState<Record<string, any>>({})
  const [createdRepositoryName, setCreatedRepositoryName] = useState<string | null>(null)
  const [isRefreshingRepo, setIsRefreshingRepo] = useState(false)
  const [showRepoLoadingIndicator, setShowRepoLoadingIndicator] = useState(false)
  const [repoLoadingTimer, setRepoLoadingTimer] = useState<NodeJS.Timeout | null>(null)
  const [expandingRepoKey, setExpandingRepoKey] = useState<string | null>(null)
  
  // Keep managed queue for function execution
  const managedQueueMutation = useManagedQueueItem()
  const { buildQueueVault } = useQueueVaultBuilder()
  const { data: teams } = useTeams()
  const { data: teamRepositories = [], isLoading: repositoriesLoading, refetch: refetchRepositories } = useRepositories(machine.teamName)
  const { data: machinesData = [] } = useMachines(machine.teamName)
  const { data: storageData = [] } = useStorage(machine.teamName)
  const createRepositoryMutation = useCreateRepository()
  const deleteRepositoryMutation = useDeleteRepository()

  // IMPORTANT: This component uses a hybrid approach:
  // 1. teamRepositories (from API) - provides repository credentials and metadata
  // 2. vaultStatus data - provides machine-specific repository status (mounted, size, containers, etc.)
  // 
  // The vaultStatus is populated by the bridge after each operation via list_system() function.
  // While this data can become stale, it provides valuable machine-specific information
  // that isn't available through the direct API (like mount status, disk usage, container counts).
  useEffect(() => {
    // Use cached vaultStatus data from the machine object
    if (!repositoriesLoading && machine) {
      if (machine.vaultStatus) {
        // Check if vaultStatus is just an error message (not JSON)
        if (machine.vaultStatus.trim().startsWith('jq:') || 
            machine.vaultStatus.trim().startsWith('error:') ||
            !machine.vaultStatus.trim().startsWith('{')) {
          // Invalid vaultStatus data
          setError('Invalid repository data')
          setLoading(false)
        } else {
          // Use existing vaultStatus data
          try {
            const vaultStatusData = JSON.parse(machine.vaultStatus)
            
            if (vaultStatusData.status === 'completed' && vaultStatusData.result) {
            
            // Clean the result string - remove trailing newlines and any jq errors
            let cleanedResult = vaultStatusData.result;
            
            // First, try to find where the JSON ends by looking for the last valid JSON closing
            const jsonEndMatch = cleanedResult.match(/(\}[\s\n]*$)/);
            if (jsonEndMatch) {
              const lastBraceIndex = cleanedResult.lastIndexOf('}');
              // Check if there's content after the last closing brace that looks like an error
              if (lastBraceIndex < cleanedResult.length - 10) { // Allow some whitespace
                cleanedResult = cleanedResult.substring(0, lastBraceIndex + 1);
              }
            }
            
            // Also handle the case where there might be a newline followed by jq errors
            const newlineIndex = cleanedResult.indexOf('\njq:');
            if (newlineIndex > 0) {
              cleanedResult = cleanedResult.substring(0, newlineIndex);
            }
            
            // Trim any trailing whitespace/newlines
            cleanedResult = cleanedResult.trim();
            
            const result = JSON.parse(cleanedResult)
            if (result) {
              // Process system information if available
              if (result.system) {
                setSystemInfo(result.system)
              }
              
              if (result.repositories && Array.isArray(result.repositories)) {
                // Map repository GUIDs back to names if needed
                const mappedRepositories = result.repositories.map((repo: Repository) => {
                  // Check if the name looks like a GUID
                  const isGuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(repo.name);
                  
                  if (isGuid) {
                    // Find the matching repository by GUID
                    const matchingRepo = teamRepositories.find(r => r.repositoryGuid === repo.name);
                    if (matchingRepo) {
                      return {
                        ...repo,
                        name: matchingRepo.repositoryName,
                        isUnmapped: false
                      };
                    } else {
                      // No matching repository found, mark as unmapped
                      return {
                        ...repo,
                        isUnmapped: true,
                        originalGuid: repo.name
                      };
                    }
                  }
                  
                  return {
                    ...repo,
                    isUnmapped: false
                  };
                });
                
                // Count plugin containers for each repository before setting
                const repositoriesWithPluginCounts = mappedRepositories.map((repo: Repository) => {
                  // Initialize plugin count
                  let pluginCount = 0
                  
                  // Count containers that are plugins (name starts with "plugin-")
                  if (result.containers && Array.isArray(result.containers)) {
                    result.containers.forEach((container: any) => {
                      // Check if this container belongs to this repository
                      const belongsToRepo = container.repository === repo.name ||
                        container.labels?.['com.redisolar.repository-guid'] === repo.name ||
                        container.labels?.['com.rediacc.repository-guid'] === repo.name
                      
                      // Check if it's a plugin container
                      if (belongsToRepo && container.name && container.name.startsWith('plugin-')) {
                        pluginCount++
                      }
                    })
                  }
                  
                  return {
                    ...repo,
                    plugin_count: pluginCount
                  }
                })
                
                setRepositories(repositoriesWithPluginCounts)
                
                // Process containers and services if included
                if (result.containers && Array.isArray(result.containers)) {
                  // Group containers by repository
                  const containersMap: Record<string, any> = {}
                  
                  // Initialize empty containers for all repositories
                  mappedRepositories.forEach((repo: Repository) => {
                    containersMap[repo.name] = { containers: [], error: null }
                  })
                  
                  result.containers.forEach((container: any) => {
                    // Check if container has a repository field (newer format)
                    if (container.repository) {
                      const repoGuid = container.repository
                      // Find the mapped repository that corresponds to this GUID
                      const mappedRepo = mappedRepositories.find((repo: Repository) => {
                        // Find the original repository with this GUID
                        const originalRepo = result.repositories.find((r: any) => r.name === repoGuid)
                        if (!originalRepo) return false
                        // Match by mount path or other unique properties
                        return repo.mount_path === originalRepo.mount_path || 
                               repo.image_path === originalRepo.image_path
                      })
                      if (mappedRepo) {
                        containersMap[mappedRepo.name].containers.push(container)
                      }
                    }
                    // Fallback to checking labels
                    else {
                      // Extract repository GUID from labels
                      const repoGuid = container.labels?.['com.redisolar.repository-guid'] || 
                                      container.labels?.['com.rediacc.repository-guid']
                      if (repoGuid) {
                        // Find the mapped repository
                        const mappedRepo = mappedRepositories.find((repo: Repository) => {
                          const originalRepo = result.repositories.find((r: any) => r.name === repoGuid)
                          if (!originalRepo) return false
                          return repo.mount_path === originalRepo.mount_path || 
                                 repo.image_path === originalRepo.image_path
                        })
                        if (mappedRepo) {
                          containersMap[mappedRepo.name].containers.push(container)
                        }
                      }
                    }
                  })
                  
                  setContainersData(containersMap)
                }
                
                if (result.services && Array.isArray(result.services)) {
                  // Group services by repository
                  const servicesMap: Record<string, any> = {}
                  
                  // Initialize empty services for all repositories
                  mappedRepositories.forEach((repo: Repository) => {
                    servicesMap[repo.name] = { services: [], error: null }
                  })
                  
                  // Add services to their respective repositories
                  result.services.forEach((service: any) => {
                    // Check if service has a repository field (newer format)
                    if (service.repository) {
                      const repoGuid = service.repository
                      // Find the mapped repository that corresponds to this GUID
                      const mappedRepo = mappedRepositories.find((repo: Repository) => {
                        // Find the original repository with this GUID
                        const originalRepo = result.repositories.find((r: any) => r.name === repoGuid)
                        if (!originalRepo) return false
                        // Match by mount path or other unique properties
                        return repo.mount_path === originalRepo.mount_path || 
                               repo.image_path === originalRepo.image_path
                      })
                      if (mappedRepo) {
                        servicesMap[mappedRepo.name].services.push(service)
                      }
                    }
                    // Fallback to old format checking service_name or unit_file
                    else if (service.service_name || service.unit_file) {
                      const serviceName = service.service_name || service.unit_file || ''
                      // Try to extract GUID from service name
                      const guidMatch = serviceName.match(/rediacc_([0-9a-f-]{36})_/)
                      if (guidMatch) {
                        const repoGuid = guidMatch[1]
                        // Find the mapped repository
                        const mappedRepo = mappedRepositories.find((repo: Repository) => {
                          const originalRepo = result.repositories.find((r: any) => r.name === repoGuid)
                          if (!originalRepo) return false
                          return repo.mount_path === originalRepo.mount_path || 
                                 repo.image_path === originalRepo.image_path
                        })
                        if (mappedRepo) {
                          servicesMap[mappedRepo.name].services.push(service)
                        }
                      }
                    }
                  })
                  
                  setServicesData(servicesMap)
                }
              } else {
                setRepositories([])
              }
              
              setLoading(false)
            }
          }
          } catch (err) {
            setError('Failed to parse repository data')
            setLoading(false)
          }
        }
      } else {
        // No vaultStatus data available
        setRepositories([])
        setLoading(false)
      }
    }
  }, [machine, repositoriesLoading, teamRepositories])

  // Fetch current token when modal might be opened
  useEffect(() => {
    const fetchToken = async () => {
      const token = await tokenService.getToken()
      if (token) {
        setCurrentToken(token)
      }
    }
    fetchToken()
  }, [])

  // Clean up timer on unmount
  useEffect(() => {
    return () => {
      if (repoLoadingTimer) {
        clearTimeout(repoLoadingTimer)
      }
    }
  }, [repoLoadingTimer])

  const handleRefresh = () => {
    // Trigger parent component to refresh machine data
    if (onActionComplete) {
      onActionComplete()
    }
  }

  const handleRunFunction = (repository: Repository, functionName?: string) => {
    setSelectedRepository(repository)
    setSelectedFunction(functionName || null)
    setFunctionModalOpen(true)
  }

  const handleQuickAction = async (repository: Repository, functionName: string, priority: number = 4, option?: string) => {
    try {
      // Find team vault data
      const team = teams?.find(t => t.teamName === machine.teamName)
      
      // Find the repository vault data
      const repositoryData = teamRepositories.find(r => r.repositoryName === repository.name)
      
      if (!repositoryData || !repositoryData.vaultContent) {
        showMessage('error', t('resources:repositories.noCredentialsFound', { name: repository.name }))
        return
      }
      
      // Find the grand repository vault if grandGuid exists
      let grandRepositoryVault = repositoryData.vaultContent
      if (repositoryData.grandGuid) {
        const grandRepository = teamRepositories.find(r => r.repositoryGuid === repositoryData.grandGuid)
        if (grandRepository && grandRepository.vaultContent) {
          grandRepositoryVault = grandRepository.vaultContent
        }
      }
      
      // Build params with option if provided
      const params: Record<string, any> = {
        repo: repositoryData.repositoryGuid,
        grand: repositoryData.grandGuid || ''
      }
      
      // Add option parameter if provided
      if (option) {
        params.option = option
      }
      
      // Build queue vault
      const queueVault = await buildQueueVault({
        teamName: machine.teamName,
        machineName: machine.machineName,
        bridgeName: machine.bridgeName,
        functionName: functionName,
        params: params,
        priority: priority,
        description: `${functionName} ${repository.name}`,
        addedVia: 'machine-repository-list-quick',
        teamVault: team?.vaultContent || '{}',
        machineVault: machine.vaultContent || '{}',
        repositoryGuid: repositoryData.repositoryGuid,
        repositoryVault: grandRepositoryVault
      })
      
      const response = await managedQueueMutation.mutateAsync({
        teamName: machine.teamName,
        machineName: machine.machineName,
        bridgeName: machine.bridgeName,
        queueVault,
        priority: priority
      })
      
      if (response?.taskId) {
        showMessage('success', t('resources:repositories.queueItemCreated'))
        setQueueTraceModal({ visible: true, taskId: response.taskId })
      } else if (response?.isQueued) {
        showMessage('info', t('resources:repositories.highestPriorityQueued'))
      }
    } catch (error) {
      showMessage('error', t('resources:repositories.failedToCreateQueueItem'))
    }
  }


  const handleContainerAction = async (repository: Repository, container: any, action: string) => {
    try {
      // Find team vault data
      const team = teams?.find(t => t.teamName === machine.teamName)
      
      // Find the repository vault data
      const repositoryData = teamRepositories.find(r => r.repositoryName === repository.name)
      
      if (!repositoryData || !repositoryData.vaultContent) {
        showMessage('error', t('resources:repositories.noCredentialsFound', { name: repository.name }))
        return
      }
      
      // Find the grand repository vault if grandGuid exists
      let grandRepositoryVault = repositoryData.vaultContent
      if (repositoryData.grandGuid) {
        const grandRepository = teamRepositories.find(r => r.repositoryGuid === repositoryData.grandGuid)
        if (grandRepository && grandRepository.vaultContent) {
          grandRepositoryVault = grandRepository.vaultContent
        }
      }
      
      // Build params based on action
      const params: Record<string, any> = {
        repo: repositoryData.repositoryGuid,
        container: container.id || container.name
      }
      
      // Add action-specific params
      if (action === 'container_remove') {
        params.force = 'false' // Default to safe remove
      } else if (action === 'container_logs') {
        params.lines = '100'
        params.follow = 'false'
      }
      
      // Build queue vault
      const queueVault = await buildQueueVault({
        teamName: machine.teamName,
        machineName: machine.machineName,
        bridgeName: machine.bridgeName,
        functionName: action,
        params,
        priority: 4,
        description: `${action} ${container.name}`,
        addedVia: 'machine-repository-list-container-action',
        teamVault: team?.vaultContent || '{}',
        machineVault: machine.vaultContent || '{}',
        repositoryGuid: repositoryData.repositoryGuid,
        repositoryVault: grandRepositoryVault
      })
      
      const response = await managedQueueMutation.mutateAsync({
        teamName: machine.teamName,
        machineName: machine.machineName,
        bridgeName: machine.bridgeName,
        queueVault,
        priority: 4
      })
      
      if (response?.taskId) {
        showMessage('success', t('resources:repositories.queueItemCreated'))
        setQueueTraceModal({ visible: true, taskId: response.taskId })
        
        // Container action completed
      } else if (response?.isQueued) {
        showMessage('info', t('resources:repositories.highestPriorityQueued'))
      }
    } catch (error) {
      showMessage('error', t('resources:repositories.failedToCreateQueueItem'))
    }
  }


  const handleFunctionSubmit = async (functionData: {
    function: QueueFunction
    params: Record<string, any>
    priority: number
    description: string
  }) => {
    if (!selectedRepository) return

    try {
      // Find team vault data
      const team = teams?.find(t => t.teamName === machine.teamName)
      
      // Find the repository vault data
      const repositoryData = teamRepositories.find(r => r.repositoryName === selectedRepository.name)
      
      
      if (!repositoryData || !repositoryData.vaultContent) {
        showMessage('error', t('resources:repositories.noCredentialsFound', { name: selectedRepository.name }))
        setFunctionModalOpen(false)
        setSelectedRepository(null)
        return
      }
      
      // Find the grand repository vault if grandGuid exists
      let grandRepositoryVault = repositoryData.vaultContent
      if (repositoryData.grandGuid) {
        const grandRepository = teamRepositories.find(r => r.repositoryGuid === repositoryData.grandGuid)
        if (grandRepository && grandRepository.vaultContent) {
          grandRepositoryVault = grandRepository.vaultContent
        }
      }
      
      let finalParams = { ...functionData.params }
      let repositoryGuid = repositoryData.repositoryGuid
      let repositoryVault = grandRepositoryVault
      let destinationMachineVault = undefined
      let destinationStorageVault = undefined
      let sourceMachineVault = undefined
      let sourceStorageVault = undefined
      
      // For pull from machine, get source machine vault data
      if (functionData.function.name === 'pull' && 
          functionData.params.sourceType === 'machine' && 
          functionData.params.from) {
        const sourceMachine = machinesData?.find(m => m.machineName === functionData.params.from)
        if (sourceMachine && sourceMachine.vaultContent) {
          sourceMachineVault = sourceMachine.vaultContent
        }
      }
      
      // For pull from storage, get source storage vault data
      if (functionData.function.name === 'pull' && 
          functionData.params.sourceType === 'storage' && 
          functionData.params.from) {
        const sourceStorage = storageData?.find(s => s.storageName === functionData.params.from)
        if (sourceStorage && sourceStorage.vaultContent) {
          sourceStorageVault = sourceStorage.vaultContent
        }
      }
      
      // For push to machine, get destination machine vault data
      if (functionData.function.name === 'push' && 
          functionData.params.destinationType === 'machine' && 
          functionData.params.to) {
        const destinationMachine = machinesData?.find(m => m.machineName === functionData.params.to)
        if (destinationMachine && destinationMachine.vaultContent) {
          destinationMachineVault = destinationMachine.vaultContent
        }
      }
      
      // For push to storage, get destination storage vault data
      if (functionData.function.name === 'push' && 
          functionData.params.destinationType === 'storage' && 
          functionData.params.to) {
        const destinationStorage = storageData?.find(s => s.storageName === functionData.params.to)
        if (destinationStorage && destinationStorage.vaultContent) {
          destinationStorageVault = destinationStorage.vaultContent
        }
      }
      
      // Special handling for push function - only create repository for machine-to-machine push
      if (functionData.function.name === 'push' && 
          functionData.params.dest && 
          functionData.params.destinationType === 'machine') {
        try {
          // Create a new repository with the destination filename
          await createRepositoryMutation.mutateAsync({
            teamName: machine.teamName,
            repositoryName: functionData.params.dest,
            parentRepoName: selectedRepository.name
          })
          
          // Store the created repository name for potential cleanup
          setCreatedRepositoryName(functionData.params.dest)
          
          // Immediately refresh the repositories list to get the new repository
          const { data: updatedRepos } = await refetchRepositories()
          
          // Find the newly created repository to get its GUID
          const newRepo = updatedRepos?.find(r => r.repositoryName === functionData.params.dest)
          
          if (newRepo && newRepo.repositoryGuid) {
            // Use the new repository's GUID as the dest parameter
            finalParams.dest = newRepo.repositoryGuid
            // Keep the original repository GUID for the source
            finalParams.repo = repositoryData.repositoryGuid
            // Set the grand GUID from the parent repository
            finalParams.grand = repositoryData.grandGuid || repositoryData.repositoryGuid || ''
          } else {
            // If we can't find the new repository, clean up and error
            throw new Error('Could not find newly created repository')
          }
          
        } catch (createError) {
          // If we already created the repository but failed to get its GUID, clean it up
          if (createdRepositoryName) {
            try {
              await deleteRepositoryMutation.mutateAsync({
                teamName: machine.teamName,
                repositoryName: createdRepositoryName
              })
            } catch (deleteError) {
              // Failed to cleanup repository after error
            }
          }
          showMessage('error', t('resources:repositories.failedToCreateRepository'))
          setFunctionModalOpen(false)
          setSelectedRepository(null)
          return
        }
      } else if (functionData.function.name === 'push' && 
                 functionData.params.destinationType === 'storage') {
        // For storage push, we just pass the parameters as-is
        // No need to create a new repository
        finalParams.repo = repositoryData.repositoryGuid
        finalParams.grand = repositoryData.grandGuid || repositoryData.repositoryGuid || ''
      } else if (functionData.function.name === 'pull') {
        // For pull function, set the repo and grand parameters
        finalParams.repo = repositoryData.repositoryGuid
        finalParams.grand = repositoryData.grandGuid || repositoryData.repositoryGuid || ''
      }
      
      // Build queue vault
      const queueVault = await buildQueueVault({
        teamName: machine.teamName,
        machineName: machine.machineName,
        bridgeName: machine.bridgeName,
        functionName: functionData.function.name,
        params: finalParams,
        priority: functionData.priority,
        description: functionData.description,
        addedVia: 'machine-repository-list',
        teamVault: team?.vaultContent || '{}',
        machineVault: machine.vaultContent || '{}',
        repositoryGuid,
        repositoryVault,
        destinationMachineVault,
        destinationStorageVault,
        sourceMachineVault,
        sourceStorageVault
      })
      
      
      const response = await managedQueueMutation.mutateAsync({
        teamName: machine.teamName,
        machineName: machine.machineName,
        bridgeName: machine.bridgeName,
        queueVault,
        priority: functionData.priority
      })
      
      setFunctionModalOpen(false)
      setSelectedRepository(null)
      
      if (response?.taskId) {
        showMessage('success', t('resources:repositories.queueItemCreated'))
        setQueueTraceModal({ visible: true, taskId: response.taskId })
      } else if (response?.isQueued) {
        // Item was queued for highest priority management
        showMessage('info', t('resources:repositories.highestPriorityQueued'))
      }
    } catch (error) {
      // Show more specific error message if available
      const errorMessage = error instanceof Error ? error.message : t('resources:repositories.failedToCreateQueueItem')
      showMessage('error', errorMessage)
    }
  }

  // Services columns
  const serviceColumns: ColumnsType<any> = [
    {
      title: t('resources:repositories.serviceName'),
      dataIndex: 'name',
      key: 'name',
      ellipsis: true,
      render: (name: string) => <Tag color="blue">{name}</Tag>,
    },
    {
      title: t('resources:repositories.activeState'),
      dataIndex: 'active_state',
      key: 'active_state',
      render: (state: string) => (
        <Tag color={state === 'active' ? 'success' : state === 'failed' ? 'error' : 'default'}>
          {state}
        </Tag>
      ),
    },
    {
      title: t('resources:repositories.memory'),
      dataIndex: 'memory_human',
      key: 'memory_human',
      render: (memory: string) => memory || '-',
    },
    {
      title: t('resources:repositories.pid'),
      dataIndex: 'main_pid',
      key: 'main_pid',
      width: 80,
      render: (pid: number) => pid > 0 ? pid : '-',
    },
    {
      title: t('resources:repositories.restarts'),
      dataIndex: 'restart_count',
      key: 'restart_count',
      render: (count: number) => <Tag>{count}</Tag>,
    },
  ]
    
    // Container columns (without actions column which will be added in renderExpandedRow)
    const containerColumns: ColumnsType<any> = [
      {
        title: t('resources:repositories.containerName'),
        dataIndex: 'name',
        key: 'name',
        ellipsis: true,
        render: (name: string, record: any) => {
          const isPlugin = name?.startsWith('plugin-')
          return (
            <Space>
              {isPlugin ? <ApiOutlined style={{ color: '#1890ff' }} /> : <AppstoreOutlined style={{ color: '#52c41a' }} />}
              <strong>{name}</strong>
            </Space>
          )
        },
      },
      {
        title: t('resources:repositories.containerPorts'),
        dataIndex: 'port_mappings',
        key: 'port_mappings',
        ellipsis: true,
        render: (portMappings: any[], record: any) => {
          // If we have structured port mappings, use them
          if (portMappings && Array.isArray(portMappings) && portMappings.length > 0) {
            return (
              <Space direction="vertical" size={0}>
                {portMappings.map((mapping, index) => (
                  <Text key={index} style={{ fontSize: 12 }}>
                    {mapping.host_port ? (
                      <span>
                        {mapping.host}:{mapping.host_port} → {mapping.container_port}/{mapping.protocol}
                      </span>
                    ) : (
                      <span>{mapping.container_port}/{mapping.protocol}</span>
                    )}
                  </Text>
                ))}
              </Space>
            )
          }
          // Fallback to raw ports string
          else if (record.ports) {
            return <Text style={{ fontSize: 12 }}>{record.ports}</Text>
          }
          return '-'
        },
      },
    ]
    
  const renderExpandedRow = (record: Repository) => {
    const services = servicesData[record.name]
    const containers = containersData[record.name]
    
    // Separate plugin containers from regular containers
    const pluginContainers = containers?.containers?.filter((c: any) => c.name && c.name.startsWith('plugin-')) || []
    const regularContainers = containers?.containers?.filter((c: any) => !c.name || !c.name.startsWith('plugin-')) || []
    
    // Container columns with repository context
    const containerColumnsWithRepo: ColumnsType<any> = [
      ...containerColumns.slice(0, -1), // All columns except actions
      {
        title: t('common:table.actions'),
        key: 'actions',
        fixed: 'right',
        render: (_: any, container: any) => {
          const menuItems = []
          
          if (container.state === 'running') {
            // Running container actions
            menuItems.push({
              key: 'stop',
              label: t('functions:functions.container_stop.name'),
              icon: <StopOutlined />,
              onClick: () => handleContainerAction(record, container, 'container_stop')
            })
            menuItems.push({
              key: 'restart',
              label: t('functions:functions.container_restart.name'),
              icon: <ReloadOutlined />,
              onClick: () => handleContainerAction(record, container, 'container_restart')
            })
            menuItems.push({
              key: 'pause',
              label: t('functions:functions.container_pause.name'),
              icon: <PauseCircleOutlined />,
              onClick: () => handleContainerAction(record, container, 'container_pause')
            })
          } else if (container.state === 'paused') {
            // Paused container actions
            menuItems.push({
              key: 'unpause',
              label: t('functions:functions.container_unpause.name'),
              icon: <PlayCircleOutlined />,
              onClick: () => handleContainerAction(record, container, 'container_unpause')
            })
          } else {
            // Stopped container actions
            menuItems.push({
              key: 'start',
              label: t('functions:functions.container_start.name'),
              icon: <PlayCircleOutlined />,
              onClick: () => handleContainerAction(record, container, 'container_start')
            })
            menuItems.push({
              key: 'remove',
              label: t('functions:functions.container_remove.name'),
              icon: <DeleteOutlined />,
              onClick: () => handleContainerAction(record, container, 'container_remove')
            })
          }
          
          // Always available actions
          menuItems.push({ type: 'divider' as const })
          menuItems.push({
            key: 'logs',
            label: t('functions:functions.container_logs.name'),
            icon: <FileTextOutlined />,
            onClick: () => handleContainerAction(record, container, 'container_logs')
          })
          menuItems.push({
            key: 'inspect',
            label: t('functions:functions.container_inspect.name'),
            icon: <LineChartOutlined />,
            onClick: () => handleContainerAction(record, container, 'container_inspect')
          })
          menuItems.push({
            key: 'stats',
            label: t('functions:functions.container_stats.name'),
            icon: <LineChartOutlined />,
            onClick: () => handleContainerAction(record, container, 'container_stats')
          })
          
          return (
            <Dropdown
              menu={{ items: menuItems }}
              trigger={['click']}
            >
              <Button
                type="primary"
                size="small"
                icon={<FunctionOutlined />}
                loading={managedQueueMutation.isPending}
                data-testid={`machine-repo-list-container-actions-${container.id}`}
              >
                {t('machines:remote')}
              </Button>
            </Dropdown>
          )
        },
      },
    ]
    
    return (
      <div style={{ padding: '16px', position: 'relative' }}>
        {/* Loading Overlay for Repository Expansion */}
        {showRepoLoadingIndicator && expandingRepoKey === record.name && (
          <div style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(255, 255, 255, 0.7)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 10,
            borderRadius: '4px'
          }}>
            <Space direction="vertical" align="center">
              <Spin size="large" />
              <Text type="secondary">{t('common:general.refreshing')}</Text>
            </Space>
          </div>
        )}
        
        <div style={{ marginBottom: 16 }} data-testid="machine-repo-list-expanded-header">
          <Typography.Title level={5} style={{ margin: 0 }}>{t('resources:repositories.containersAndPlugins')}</Typography.Title>
        </div>
        
        {/* Regular Containers Table */}
        <div style={{ marginBottom: 24 }} data-testid="machine-repo-list-containers-section">
          <Typography.Title level={5} style={{ marginBottom: 16 }}>
            {t('resources:repositories.containersList')}
          </Typography.Title>
          {containers?.error ? (
            <Alert message={t('resources:repositories.errorLoadingContainers')} description={containers.error} type="error" />
          ) : regularContainers.length > 0 ? (
            <Table
              columns={containerColumnsWithRepo}
              dataSource={regularContainers}
              rowKey="id"
              size="small"
              pagination={false}
              scroll={{ x: 'max-content' }}
              data-testid="machine-repo-list-containers-table"
              onRow={(container) => ({
                onClick: (e) => {
                  const target = e.target as HTMLElement
                  if (target.closest('button') || target.closest('.ant-dropdown-trigger')) {
                    return
                  }
                  onContainerClick?.(container)
                },
                style: {
                  cursor: onContainerClick ? 'pointer' : 'default',
                  backgroundColor: highlightedContainer?.id === container.id ? 'rgba(24, 144, 255, 0.05)' : undefined,
                  transition: 'background-color 0.3s ease'
                },
                onMouseEnter: (e) => {
                  if (onContainerClick) {
                    e.currentTarget.style.backgroundColor = highlightedContainer?.id === container.id ? 'rgba(24, 144, 255, 0.05)' : 'rgba(0, 0, 0, 0.02)'
                  }
                },
                onMouseLeave: (e) => {
                  e.currentTarget.style.backgroundColor = highlightedContainer?.id === container.id ? 'rgba(24, 144, 255, 0.05)' : ''
                }
              })}
            />
          ) : (
            <Empty description={t('resources:repositories.noContainers')} data-testid="machine-repo-list-no-containers" />
          )}
        </div>
        
        {/* Plugin Containers Table */}
        {pluginContainers.length > 0 && (
          <div data-testid="machine-repo-list-plugins-section">
            <Typography.Title level={5} style={{ marginBottom: 16 }}>
              {t('resources:repositories.pluginsList')}
            </Typography.Title>
            <Table
              columns={containerColumnsWithRepo}
              dataSource={pluginContainers}
              rowKey="id"
              size="small"
              pagination={false}
              scroll={{ x: 'max-content' }}
              data-testid="machine-repo-list-plugins-table"
              onRow={(container) => ({
                onClick: (e) => {
                  const target = e.target as HTMLElement
                  if (target.closest('button') || target.closest('.ant-dropdown-trigger')) {
                    return
                  }
                  onContainerClick?.(container)
                },
                style: {
                  cursor: onContainerClick ? 'pointer' : 'default',
                  backgroundColor: highlightedContainer?.id === container.id ? 'rgba(24, 144, 255, 0.05)' : undefined,
                  transition: 'background-color 0.3s ease'
                },
                onMouseEnter: (e) => {
                  if (onContainerClick) {
                    e.currentTarget.style.backgroundColor = highlightedContainer?.id === container.id ? 'rgba(24, 144, 255, 0.05)' : 'rgba(0, 0, 0, 0.02)'
                  }
                },
                onMouseLeave: (e) => {
                  e.currentTarget.style.backgroundColor = highlightedContainer?.id === container.id ? 'rgba(24, 144, 255, 0.05)' : ''
                }
              })}
            />
          </div>
        )}
      </div>
    )
  }

  // System container columns
  const systemContainerColumns: ColumnsType<any> = [
    {
      title: t('resources:repositories.containerName'),
      dataIndex: 'name',
      key: 'name',
      ellipsis: true,
      render: (name: string) => (
        <Space>
          <CloudServerOutlined style={{ color: '#722ed1' }} />
          <strong>{name}</strong>
        </Space>
      ),
    },
    {
      title: t('resources:repositories.containerImage'),
      dataIndex: 'image',
      key: 'image',
      width: 250,
      ellipsis: true,
    },
    {
      title: t('resources:repositories.containerStatus'),
      dataIndex: 'state',
      key: 'state',
      render: (state: string, record: any) => (
        <Space>
          <Tag color={state === 'running' ? 'success' : 'default'}>
            {state}
          </Tag>
          {record.status && <Text type="secondary" style={{ fontSize: 12 }}>{record.status}</Text>}
        </Space>
      ),
    },
    {
      title: t('resources:repositories.containerCPU'),
      dataIndex: 'cpu_percent',
      key: 'cpu_percent',
      render: (cpu: string) => cpu || '-',
    },
    {
      title: t('resources:repositories.containerMemory'),
      dataIndex: 'memory_usage',
      key: 'memory_usage',
      render: (memory: string) => memory || '-',
    },
    {
      title: t('resources:repositories.containerPorts'),
      dataIndex: 'port_mappings',
      key: 'port_mappings',
      ellipsis: true,
      render: (portMappings: any[], record: any) => {
        // If we have structured port mappings, use them
        if (portMappings && Array.isArray(portMappings) && portMappings.length > 0) {
          return (
            <Space direction="vertical" size={0}>
              {portMappings.map((mapping, index) => (
                <Text key={index} style={{ fontSize: 12 }}>
                  {mapping.host_port ? (
                    <span>
                      {mapping.host}:{mapping.host_port} → {mapping.container_port}/{mapping.protocol}
                    </span>
                  ) : (
                    <span>{mapping.container_port}/{mapping.protocol}</span>
                  )}
                </Text>
              ))}
            </Space>
          )
        }
        // Fallback to raw ports string
        else if (record.ports) {
          return <Text style={{ fontSize: 12 }}>{record.ports}</Text>
        }
        return '-'
      },
    },
  ]

  const columns: ColumnsType<Repository> = [
    {
      title: t('resources:repositories.repositoryName'),
      dataIndex: 'name',
      key: 'name',
      ellipsis: true,
      render: (name: string, record: Repository) => {
        const isExpanded = expandedRows.includes(record.name)
        const hasExpandableContent = record.mounted && (record.has_services || record.container_count > 0 || record.plugin_count > 0)
        
        return (
          <Space>
            <span style={{ 
              display: 'inline-block',
              width: 12,
              transition: 'transform 0.3s ease',
              transform: isExpanded ? 'rotate(90deg)' : 'rotate(0deg)',
              visibility: hasExpandableContent ? 'visible' : 'hidden'
            }}>
              <RightOutlined style={{ fontSize: 12, color: '#999' }} />
            </span>
            <InboxOutlined style={{ color: '#556b2f' }} />
            <strong>{name}</strong>
          </Space>
        )
      },
    },
    {
      title: t('common:table.actions'),
      key: 'actions',
      width: 160,
      fixed: 'right',
      render: (_: any, record: Repository) => {
        // Build smart menu items based on repository state
        const menuItems = []
        
        // Up - always available
        menuItems.push({
          key: 'up',
          label: t('functions:functions.up.name'),
          icon: <PlayCircleOutlined style={{ color: '#52c41a' }} />,
          onClick: () => handleQuickAction(record, 'up')
        })
        
        // Down - only when mounted
        if (record.mounted) {
          menuItems.push({
            key: 'down',
            label: t('functions:functions.down.name'),
            icon: <PauseCircleOutlined style={{ color: '#ff4d4f' }} />,
            onClick: () => handleQuickAction(record, 'down', 4, 'unmount')
          })
        }
        
        // Push - always available
        menuItems.push({
          key: 'push',
          label: t('functions:functions.push.name'),
          icon: <CloudUploadOutlined />,
          onClick: () => handleRunFunction(record, 'push')
        })
        
        // Always add divider and advanced option at the end
        if (menuItems.length > 0) {
          menuItems.push({
            type: 'divider' as const
          })
        }
        
        menuItems.push({
          key: 'advanced',
          label: t('machines:advanced'),
          icon: <FunctionOutlined />,
          onClick: () => handleRunFunction(record)
        })
        
        return (
          <Space size="small">
            <Dropdown
              menu={{ items: menuItems }}
              trigger={['click']}
            >
              <Button
                type="primary"
                size="small"
                icon={<FunctionOutlined />}
                loading={managedQueueMutation.isPending}
                data-testid={`machine-repo-list-repo-actions-${record.name}`}
              >
                {t('machines:remote')}
              </Button>
            </Dropdown>
            {record.mounted && (
              <LocalActionsMenu
                machine={machine.machineName}
                repository={record.name}
                token={currentToken}
                teamName={machine.teamName}
                pluginContainers={containersData[record.name]?.containers || []}
                data-testid={`machine-repo-list-local-actions-${record.name}`}
              />
            )}
            {record.isUnmapped && onCreateRepository && (
              <Button
                type="default"
                size="small"
                icon={<KeyOutlined />}
                onClick={() => onCreateRepository(machine, record.originalGuid || record.name)}
                data-testid={`machine-repo-list-add-credential-${record.name}`}
              >
                {t('resources:repositories.addCredential')}
              </Button>
            )}
          </Space>
        )
      },
    },
  ]

  if (loading) {
    return (
      <div style={{ padding: '20px', textAlign: 'center' }} data-testid="machine-repo-list-loading">
        <Spin tip={t('resources:repositories.fetchingRepositories')} />
      </div>
    )
  }

  if (error) {
    return (
      <div style={{ padding: '20px' }} data-testid="machine-repo-list-error">
        <Alert
          message={t('common:messages.error')}
          description={error}
          type="error"
          showIcon
          action={
            <Button size="small" onClick={handleRefresh} data-testid="machine-repo-list-retry">
              {t('common:actions.retry')}
            </Button>
          }
        />
      </div>
    )
  }

  return (
    <div style={{ padding: '0 20px 20px 20px', overflowX: 'auto', position: 'relative' }} data-testid="machine-repo-list">
      {/* Loading Overlay */}
      {isLoading && (
        <div style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(255, 255, 255, 0.7)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 10,
          borderRadius: '4px'
        }}>
          <Space direction="vertical" align="center">
            <Spin size="large" />
            <Text type="secondary">{t('common:general.refreshing')}</Text>
          </Space>
        </div>
      )}
      
      {/* Machine Name Title when in grouped view */}
      {hideSystemInfo && (
        <div style={{ marginBottom: 16, paddingTop: 16, borderBottom: '1px solid #f0f0f0', paddingBottom: 12 }} data-testid="machine-repo-list-machine-header">
          <Space direction="vertical" size={4}>
            <Space>
              <DesktopOutlined style={{ fontSize: 20, color: '#556b2f' }} />
              <Typography.Title level={4} style={{ margin: 0, color: '#556b2f' }} data-testid="machine-repo-list-machine-name">
                {machine.machineName}
              </Typography.Title>
            </Space>
            <Space wrap size={8}>
              <Tag color="#8FBC8F" data-testid="machine-repo-list-team-tag">{machine.teamName}</Tag>
              <Tag color="green" data-testid="machine-repo-list-bridge-tag">{machine.bridgeName}</Tag>
              {machine.regionName && <Tag color="purple" data-testid="machine-repo-list-region-tag">{machine.regionName}</Tag>}
              <Tag color="blue" data-testid="machine-repo-list-queue-tag">{machine.queueCount} {t('machines:queueItems')}</Tag>
            </Space>
          </Space>
        </div>
      )}
      
      {/* Repositories Label */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, marginTop: hideSystemInfo ? 8 : 20 }} data-testid="machine-repo-list-repos-header">
        <Typography.Title level={5} style={{ marginBottom: 0 }} data-testid="machine-repo-list-repos-title">
          {t('resources:repositories.repositories')}
        </Typography.Title>
        {machine.vaultStatusTime && !loading && (
          <Text type="secondary" style={{ fontSize: '12px' }} title={`Raw: ${machine.vaultStatusTime}, Local: ${new Date(machine.vaultStatusTime).toLocaleString()}`} data-testid="machine-repo-list-last-updated">
            {t('machines:lastUpdated')}: {getLocalizedRelativeTime(machine.vaultStatusTime, t)}
          </Text>
        )}
      </div>
      
      {/* Repository Table */}
      <Table
        columns={columns}
        dataSource={repositories}
        rowKey="name"
        size="small"
        pagination={false}
        scroll={{ x: 'max-content' }}
        data-testid="machine-repo-list-table"
        expandable={{
          expandedRowRender: renderExpandedRow,
          expandedRowKeys: expandedRows,
          onExpandedRowsChange: (keys) => setExpandedRows(keys as string[]),
          rowExpandable: (record) => record.mounted && (record.has_services || record.container_count > 0 || record.plugin_count > 0),
          expandIcon: () => null, // Hide default expand icon
          expandRowByClick: false, // We'll handle this manually
        }}
        locale={{
          emptyText: t('resources:repositories.noRepositories')
        }}
        onRow={(record) => {
          const hasExpandableContent = record.mounted && (record.has_services || record.container_count > 0 || record.plugin_count > 0)
          return {
            onClick: (e) => {
              const target = e.target as HTMLElement
              // Don't trigger if clicking on buttons or dropdowns
              if (target.closest('button') || target.closest('.ant-dropdown-trigger')) {
                return
              }
              
              // Toggle expansion if the row has expandable content
              if (hasExpandableContent) {
                const isExpanded = expandedRows.includes(record.name)
                if (isExpanded) {
                  setExpandedRows(expandedRows.filter(key => key !== record.name))
                } else {
                  setExpandedRows([...expandedRows, record.name])
                  
                  // Trigger refresh when expanding
                  if (onRefreshMachines) {
                    setExpandingRepoKey(record.name)
                    setIsRefreshingRepo(true)
                    
                    // Start 1-second timer for loading indicator
                    const timer = setTimeout(() => {
                      setShowRepoLoadingIndicator(true)
                    }, 1000)
                    setRepoLoadingTimer(timer)
                    
                    // Trigger refresh
                    onRefreshMachines().finally(() => {
                      if (repoLoadingTimer) {
                        clearTimeout(repoLoadingTimer)
                      }
                      setIsRefreshingRepo(false)
                      setShowRepoLoadingIndicator(false)
                      setExpandingRepoKey(null)
                      setRepoLoadingTimer(null)
                    })
                  }
                }
              }
              
              // Still call onRepositoryClick if provided
              onRepositoryClick?.(record)
            },
            style: {
              cursor: hasExpandableContent || onRepositoryClick ? 'pointer' : 'default',
              backgroundColor: highlightedRepository?.name === record.name ? 'rgba(24, 144, 255, 0.05)' : undefined,
              transition: 'background-color 0.3s ease'
            },
            onMouseEnter: (e) => {
              if (hasExpandableContent || onRepositoryClick) {
                e.currentTarget.style.backgroundColor = highlightedRepository?.name === record.name ? 'rgba(24, 144, 255, 0.08)' : 'rgba(0, 0, 0, 0.02)'
              }
            },
            onMouseLeave: (e) => {
              e.currentTarget.style.backgroundColor = highlightedRepository?.name === record.name ? 'rgba(24, 144, 255, 0.05)' : ''
            }
          }
        }}
      />
      
      {/* System Containers Section */}
      {systemContainers.length > 0 && !hideSystemInfo && (
        <div data-testid="machine-repo-list-system-containers">
          <Typography.Title level={5} style={{ marginBottom: 16, marginTop: 32 }} data-testid="machine-repo-list-system-containers-title">
            {t('resources:repositories.systemContainers')}
          </Typography.Title>
          <div style={{ marginBottom: 32 }}>
            <Table
              columns={systemContainerColumns}
              dataSource={systemContainers}
              rowKey="id"
              size="small"
              pagination={false}
              scroll={{ x: 'max-content' }}
              data-testid="machine-repo-list-system-containers-table"
            />
          </div>
        </div>
      )}
      
      
      
      {/* Function Selection Modal */}
      <FunctionSelectionModal
        open={functionModalOpen}
        onCancel={() => {
          setFunctionModalOpen(false)
          setSelectedRepository(null)
          setSelectedFunction(null)
        }}
        onSubmit={handleFunctionSubmit}
        title={t('machines:runFunction')}
        data-testid="machine-repo-list-function-modal"
        subtitle={
          selectedRepository && (
            <Space direction="vertical" size="small" style={{ width: '100%' }}>
              <Space>
                <Text>{t('resources:repositories.repository')}:</Text>
                <Tag color="#8FBC8F">{selectedRepository.name}</Tag>
                <Text>•</Text>
                <Text>{t('machines:machine')}:</Text>
                <Tag color="#556b2f">{machine.machineName}</Tag>
              </Space>
              {selectedFunction === 'push' && (() => {
                const currentRepoData = teamRepositories.find(r => r.repositoryName === selectedRepository.name);
                if (currentRepoData?.grandGuid) {
                  const grandRepo = teamRepositories.find(r => r.repositoryGuid === currentRepoData.grandGuid);
                  if (grandRepo) {
                    return (
                      <Space>
                        <Text type="secondary">Original Repository:</Text>
                        <Tag color="blue">{grandRepo.repositoryName}</Tag>
                        <Text type="secondary">→</Text>
                        <Text type="secondary">Current:</Text>
                        <Tag color="#8FBC8F">{selectedRepository.name}</Tag>
                      </Space>
                    );
                  }
                }
                return null;
              })()}
            </Space>
          )
        }
        allowedCategories={['repository', 'backup', 'network']}
        loading={managedQueueMutation.isPending}
        showMachineSelection={false}
        teamName={machine.teamName}
        hiddenParams={['repo', 'grand']}
        defaultParams={{ 
          repo: (() => {
            const repo = teamRepositories.find(r => r.repositoryName === selectedRepository?.name);
            return repo?.repositoryGuid || '';
          })(),
          grand: teamRepositories.find(r => r.repositoryName === selectedRepository?.name)?.grandGuid || ''
        }}
        initialParams={
          selectedFunction === 'push' && selectedRepository ? (() => {
            // Find the current repository data
            const currentRepoData = teamRepositories.find(r => r.repositoryName === selectedRepository.name);
            
            // Find the grand repository if it exists
            let baseRepoName = selectedRepository.name;
            if (currentRepoData?.grandGuid) {
              const grandRepo = teamRepositories.find(r => r.repositoryGuid === currentRepoData.grandGuid);
              if (grandRepo) {
                baseRepoName = grandRepo.repositoryName;
              }
            }
            
            // Generate destination with the base name
            return {
              dest: `${baseRepoName}-${selectedRepository.mounted ? 'online' : 'offline'}-${new Date().toISOString().slice(0, 19).replace('T', '-').replace(/:/g, '-')}`,
              state: selectedRepository.mounted ? 'online' : 'offline'
            };
          })() : {}
        }
        preselectedFunction={selectedFunction || undefined}
        currentMachineName={machine.machineName}
        additionalContext={
          selectedFunction === 'push' && selectedRepository ? {
            sourceRepository: selectedRepository.name,
            grandRepository: (() => {
              const currentRepoData = teamRepositories.find(r => r.repositoryName === selectedRepository.name);
              if (currentRepoData?.grandGuid) {
                const grandRepo = teamRepositories.find(r => r.repositoryGuid === currentRepoData.grandGuid);
                return grandRepo?.repositoryName || null;
              }
              return null;
            })()
          } : undefined
        }
      />
      
      {/* Queue Item Trace Modal */}
      <QueueItemTraceModal
        taskId={queueTraceModal.taskId}
        visible={queueTraceModal.visible}
        onClose={() => {
          setQueueTraceModal({ visible: false, taskId: null })
          setCreatedRepositoryName(null) // Clear the created repository name
          // Trigger refresh when modal closes
          if (onActionComplete) {
            onActionComplete()
          }
        }}
        data-testid="machine-repo-list-queue-trace-modal"
        onTaskStatusChange={async (status, taskId) => {
          // If push task failed and we created a repository, delete it
          if (status === 'FAILED' && createdRepositoryName) {
            try {
              await deleteRepositoryMutation.mutateAsync({
                teamName: machine.teamName,
                repositoryName: createdRepositoryName
              })
              showMessage('info', t('resources:repositories.cleanedUpFailedPush'))
            } catch (deleteError) {
              // Failed to cleanup repository after failed push
            }
            setCreatedRepositoryName(null)
          }
        }}
      />
      
    </div>
  )
}