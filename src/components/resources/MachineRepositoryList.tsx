import React, { useEffect, useState } from 'react'
import { Table, Spin, Alert, Tag, Space, Typography, Button, Dropdown, Empty, Card, Row, Col, Progress } from 'antd'
import { InboxOutlined, CheckCircleOutlined, FunctionOutlined, PlayCircleOutlined, StopOutlined, ExpandOutlined, CloudUploadOutlined, CloudDownloadOutlined, PauseCircleOutlined, ReloadOutlined, DeleteOutlined, FileTextOutlined, LineChartOutlined, PlusOutlined, MinusOutlined, DesktopOutlined, ClockCircleOutlined, DatabaseOutlined, HddOutlined, ApiOutlined, DisconnectOutlined, GlobalOutlined } from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { type QueueFunction } from '@/api/queries/queue'
import { useQueueItemTrace } from '@/api/queries/queue'
import { useQueueVaultBuilder } from '@/hooks/useQueueVaultBuilder'
import { useManagedQueueItem } from '@/hooks/useManagedQueueItem'
import { Machine } from '@/types'
import { useTeams } from '@/api/queries/teams'
import { useRepositories, useCreateRepository, useDeleteRepository } from '@/api/queries/repositories'
import { useMachines } from '@/api/queries/machines'
import { useStorage } from '@/api/queries/storage'
import { queueMonitoringService } from '@/services/queueMonitoringService'
import queueManagerService from '@/services/queueManagerService'
import type { ColumnsType } from 'antd/es/table'
import FunctionSelectionModal from '@/components/common/FunctionSelectionModal'
import QueueItemTraceModal from '@/components/common/QueueItemTraceModal'
import { LocalCommandModal } from './LocalCommandModal'
import { DesktopLocalCommandModal } from './DesktopLocalCommandModal'
import { showMessage } from '@/utils/messages'
import { tokenService } from '@/services/tokenService'
import { useAppSelector } from '@/store/store'
import { getLocalizedRelativeTime } from '@/utils/timeUtils'
import { useDesktopMode } from '@/hooks/useDesktopMode'

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
  has_services: boolean
  service_count: number
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
}


export const MachineRepositoryList: React.FC<MachineRepositoryListProps> = ({ machine, onActionComplete, hideSystemInfo = false }) => {
  const { t } = useTranslation(['resources', 'common', 'machines', 'functions'])
  const userEmail = useAppSelector((state) => state.auth.user?.email || '')
  const { isDesktop } = useDesktopMode()
  const [currentToken, setCurrentToken] = useState<string>('')
  const [repositories, setRepositories] = useState<Repository[]>([])
  const [systemContainers, setSystemContainers] = useState<any[]>([])
  const [systemInfo, setSystemInfo] = useState<SystemInfo | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [taskId, setTaskId] = useState<string | null>(null)
  const [queueId, setQueueId] = useState<string | null>(null)
  const [isQueued, setIsQueued] = useState(false)
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
  const [localCommandModal, setLocalCommandModal] = useState<{
    visible: boolean
    repository: Repository | null
  }>({ visible: false, repository: null })
  const [createdRepositoryName, setCreatedRepositoryName] = useState<string | null>(null)
  
  // Keep managed queue for function execution
  const managedQueueMutation = useManagedQueueItem()
  const { buildQueueVault } = useQueueVaultBuilder()
  const { data: teams } = useTeams()
  const { data: teamRepositories = [], isLoading: repositoriesLoading, refetch: refetchRepositories } = useRepositories(machine.teamName)
  const { data: machinesData = [] } = useMachines(machine.teamName)
  const { data: storageData = [] } = useStorage(machine.teamName)
  const createRepositoryMutation = useCreateRepository()
  const deleteRepositoryMutation = useDeleteRepository()
  
  // Use queue trace to monitor the task
  const { data: traceData } = useQueueItemTrace(taskId, !!taskId)

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
                        name: matchingRepo.repositoryName
                      };
                    }
                  }
                  
                  return repo;
                });
                
                setRepositories(mappedRepositories)
                
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

  // Monitor queued item for task ID
  useEffect(() => {
    if (!queueId) return

    const unsubscribe = managedQueueMutation.subscribeToQueueItem?.(queueId, (item) => {
      if (item?.taskId) {
        // Got the task ID!
        setTaskId(item.taskId)
        setQueueId(null) // Clear queue ID
        setIsQueued(false)
        showMessage('info', t('resources:repositories.taskSubmitted'))
        
        // Start monitoring the task
        queueMonitoringService.addTask(
          item.taskId,
          machine.teamName,
          machine.machineName,
          'PENDING', // Initial status when task is created
          undefined, // retryCount
          undefined, // lastFailureReason
          machine.bridgeName,
          4 // regular priority for repository list tasks
        )
      } else if (item?.status === 'failed') {
        setError(t('resources:repositories.failedToSubmit'))
        setLoading(false)
        setQueueId(null)
        setIsQueued(false)
      } else if (item?.status === 'cancelled') {
        setError(t('resources:repositories.taskCancelled'))
        setLoading(false)
        setQueueId(null)
        setIsQueued(false)
      }
    })

    return () => {
      unsubscribe?.()
    }
  }, [queueId, managedQueueMutation, t])

  useEffect(() => {
    // Log task status for debugging
    if (traceData?.queueDetails?.status) {
      // Task status: traceData.queueDetails.status
    }
    
    // Check if task is completed
    if (traceData?.queueDetails?.status === 'COMPLETED') {
      // Ensure the queue manager is updated
      if (taskId) {
        // Task completed, updating queue manager
        queueManagerService.updateTaskStatus(taskId, 'completed')
      }
      
      // Check if we have response vault content
      if (!traceData?.responseVaultContent?.vaultContent) {
        // Task completed but no response vault content received
        // Full trace data: traceData
        setError('Task completed but no response data received. Check console for details.')
        setLoading(false)
        return
      }
      
      try {
        // Parse the response vault content
        const vaultContent = JSON.parse(traceData.responseVaultContent.vaultContent)
        // Parsed vault content: vaultContent
        
        // The result is nested in the response
        if (vaultContent.result) {
          const result = JSON.parse(vaultContent.result)
          // Parsed result: result
          
          // Parse the command output which contains the repositories
          if (result.command_output) {
            const commandOutput = JSON.parse(result.command_output)
            // Command output: commandOutput
            
            // Process system information if available
            if (commandOutput.system) {
              setSystemInfo(commandOutput.system)
            }
            
            if (commandOutput.repositories && Array.isArray(commandOutput.repositories)) {
              // Map repository GUIDs back to names if needed
              const mappedRepositories = commandOutput.repositories.map((repo: Repository) => {
                // Check if the name looks like a GUID
                const isGuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(repo.name);
                
                if (isGuid) {
                  // Find the matching repository by GUID
                  const matchingRepo = teamRepositories.find(r => r.repositoryGuid === repo.name);
                  if (matchingRepo) {
                    return {
                      ...repo,
                      name: matchingRepo.repositoryName
                    };
                  }
                }
                
                // If not a GUID or no match found, check if it's a repository name that needs GUID lookup
                const repoByName = teamRepositories.find(r => r.repositoryName === repo.name);
                if (!repoByName) {
                  // This might be a case where name is "A1" but it's actually a repository name
                }
                
                return repo;
              });
              
              setRepositories(mappedRepositories)
              
              // Process system containers if included in response
              if (commandOutput.system_containers && Array.isArray(commandOutput.system_containers)) {
                setSystemContainers(commandOutput.system_containers)
              } else {
                setSystemContainers([])
              }
              
              // Process services data if included in response
              if (commandOutput.services && Array.isArray(commandOutput.services)) {
                const servicesMap: Record<string, any> = {}
                
                // Initialize empty services array for all repositories
                mappedRepositories.forEach((repo: Repository) => {
                  servicesMap[repo.name] = { services: [] }
                })
                
                // Add services to their respective repositories
                commandOutput.services.forEach((service: any) => {
                  // Find the repository name for this service
                  const repoGuid = service.repository
                  
                  // Try to find the mapped repository by matching the GUID
                  const mappedRepo = mappedRepositories.find((repo: Repository) => {
                    // Check if this repository's original name was the GUID we're looking for
                    const originalRepo = commandOutput.repositories.find((r: any) => r.name === repoGuid)
                    if (!originalRepo) return false
                    
                    // Match by comparing properties that should be the same
                    return repo.mount_path === originalRepo.mount_path || 
                           repo.image_path === originalRepo.image_path ||
                           (repo.size === originalRepo.size && repo.modified === originalRepo.modified)
                  })
                  
                  if (mappedRepo && servicesMap[mappedRepo.name]) {
                    servicesMap[mappedRepo.name].services.push(service)
                  }
                })
                
                // Services data processed: servicesMap
                
                // Update all services data at once
                setServicesData(servicesMap)
              }
              
              // Process containers data if included in response
              if (commandOutput.containers && Array.isArray(commandOutput.containers)) {
                const containersMap: Record<string, any> = {}
                
                // Initialize empty containers array for all repositories
                mappedRepositories.forEach((repo: Repository) => {
                  containersMap[repo.name] = { containers: [] }
                })
                
                // Add containers to their respective repositories
                commandOutput.containers.forEach((container: any) => {
                  // Find the repository name for this container
                  const repoGuid = container.repository
                  
                  // Try to find the mapped repository by matching the GUID
                  const mappedRepo = mappedRepositories.find((repo: Repository) => {
                    // Check if this repository's original name was the GUID we're looking for
                    const originalRepo = commandOutput.repositories.find((r: any) => r.name === repoGuid)
                    if (!originalRepo) return false
                    
                    // Match by comparing properties that should be the same
                    return repo.mount_path === originalRepo.mount_path || 
                           repo.image_path === originalRepo.image_path ||
                           (repo.size === originalRepo.size && repo.modified === originalRepo.modified)
                  })
                  
                  if (mappedRepo && containersMap[mappedRepo.name]) {
                    containersMap[mappedRepo.name].containers.push(container)
                  }
                })
                
                // Containers data processed: containersMap
                
                // Update all containers data at once
                setContainersData(containersMap)
              }
            } else {
              setRepositories([])
            }
          } else {
            // No command_output in result
            setRepositories([])
            setError('No repository data in response')
          }
        } else {
          // No result in vault content
          setError('Invalid response format - missing result')
        }
        setLoading(false)
      } catch (err) {
        // Error parsing response: err
        setError('Failed to parse repository data: ' + (err as Error).message)
        setLoading(false)
      }
    } else if (traceData?.queueDetails?.status === 'FAILED' || traceData?.queueDetails?.permanentlyFailed) {
      // Ensure the queue manager is updated
      if (taskId) {
        // Task failed, updating queue manager
        queueManagerService.updateTaskStatus(taskId, 'failed')
      }
      
      setError(traceData.queueDetails.lastFailureReason || 'Failed to fetch repositories')
      setLoading(false)
    }
  }, [traceData])

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
              console.error('Failed to cleanup repository after error:', deleteError)
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
      width: 200,
      ellipsis: true,
      render: (name: string) => <Tag color="blue">{name}</Tag>,
    },
    {
      title: t('resources:repositories.activeState'),
      dataIndex: 'active_state',
      key: 'active_state',
      width: 120,
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
      width: 100,
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
      width: 100,
      render: (count: number) => <Tag>{count}</Tag>,
    },
  ]
    
    // Container columns (without actions column which will be added in renderExpandedRow)
    const containerColumns: ColumnsType<any> = [
      {
        title: t('resources:repositories.containerName'),
        dataIndex: 'name',
        key: 'name',
        width: 200,
        ellipsis: true,
        render: (name: string) => <Tag color="cyan">{name}</Tag>,
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
        width: 200,
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
        width: 100,
        render: (cpu: string) => cpu || '-',
      },
      {
        title: t('resources:repositories.containerMemory'),
        dataIndex: 'memory_usage',
        key: 'memory_usage',
        width: 120,
        render: (memory: string) => memory || '-',
      },
      {
        title: t('resources:repositories.containerPorts'),
        dataIndex: 'port_mappings',
        key: 'port_mappings',
        width: 200,
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
    
    // Container columns with repository context
    const containerColumnsWithRepo: ColumnsType<any> = [
      ...containerColumns.slice(0, -1), // All columns except actions
      {
        title: t('common:table.actions'),
        key: 'actions',
        width: 120,
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
              >
                {t('machines:remote')}
              </Button>
            </Dropdown>
          )
        },
      },
    ]
    
    return (
      <div style={{ padding: '16px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <Typography.Title level={5} style={{ margin: 0 }}>{t('resources:repositories.servicesAndContainers')}</Typography.Title>
          <Button
            type="text"
            size="small"
            icon={<ReloadOutlined />}
            onClick={() => {
              // Refresh button removed - data comes from machine vaultStatus
              showMessage('info', t('resources:repositories.refreshNotAvailable'))
            }}
          >
            {t('common:refresh')}
          </Button>
        </div>
        
        {/* Services Table */}
        <div style={{ marginBottom: 24 }}>
          <Typography.Title level={5} style={{ marginBottom: 16 }}>
            {t('resources:repositories.servicesList')}
          </Typography.Title>
          {services?.error ? (
            <Alert message={t('resources:repositories.errorLoadingServices')} description={services.error} type="error" />
          ) : services?.services && services.services.length > 0 ? (
            <Table
              columns={serviceColumns}
              dataSource={services.services}
              rowKey="name"
              size="small"
              pagination={false}
              scroll={{ x: 'max-content' }}
            />
          ) : (
            <Empty description={t('resources:repositories.noServices')} />
          )}
        </div>
        
        {/* Containers Table */}
        <div>
          <Typography.Title level={5} style={{ marginBottom: 16 }}>
            {t('resources:repositories.containersList')}
          </Typography.Title>
          {containers?.error ? (
            <Alert message={t('resources:repositories.errorLoadingContainers')} description={containers.error} type="error" />
          ) : containers?.containers && containers.containers.length > 0 ? (
            <Table
              columns={containerColumnsWithRepo}
              dataSource={containers.containers}
              rowKey="id"
              size="small"
              pagination={false}
              scroll={{ x: 'max-content' }}
            />
          ) : (
            <Empty description={t('resources:repositories.noContainers')} />
          )}
        </div>
      </div>
    )
  }

  // System container columns
  const systemContainerColumns: ColumnsType<any> = [
    {
      title: t('resources:repositories.containerName'),
      dataIndex: 'name',
      key: 'name',
      width: 200,
      ellipsis: true,
      render: (name: string) => <Tag color="purple">{name}</Tag>,
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
      width: 200,
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
      width: 100,
      render: (cpu: string) => cpu || '-',
    },
    {
      title: t('resources:repositories.containerMemory'),
      dataIndex: 'memory_usage',
      key: 'memory_usage',
      width: 120,
      render: (memory: string) => memory || '-',
    },
    {
      title: t('resources:repositories.containerPorts'),
      dataIndex: 'port_mappings',
      key: 'port_mappings',
      width: 200,
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
      title: '',
      key: 'expand',
      width: 50,
      fixed: 'left',
      render: (_: any, record: Repository) => {
        // Only show expand button if repository has services or containers
        if (!record.mounted || (!record.has_services && record.container_count === 0)) {
          return null
        }
        
        const isExpanded = expandedRows.includes(record.name)
        return (
          <Button
            type="text"
            size="small"
            icon={isExpanded ? <MinusOutlined /> : <PlusOutlined />}
            onClick={() => {
              if (isExpanded) {
                setExpandedRows(expandedRows.filter(key => key !== record.name))
              } else {
                setExpandedRows([...expandedRows, record.name])
              }
            }}
          />
        )
      },
    },
    {
      title: t('resources:repositories.repositoryName'),
      dataIndex: 'name',
      key: 'name',
      width: 200,
      ellipsis: true,
      render: (name: string) => (
        <Space>
          <InboxOutlined style={{ color: '#556b2f' }} />
          <strong>{name}</strong>
        </Space>
      ),
    },
    {
      title: t('resources:repositories.size'),
      dataIndex: 'size_human',
      key: 'size_human',
      width: 100,
      render: (size: string) => <Text>{size}</Text>,
    },
    {
      title: t('resources:repositories.diskSpace'),
      key: 'disk_space',
      width: 250,
      render: (_: any, record: Repository) => {
        if (!record.disk_space || !record.mounted) return '-'
        return (
          <Space direction="vertical" size={0}>
            <Text type="secondary" style={{ fontSize: '12px' }}>
              {t('resources:repositories.used')}: {record.disk_space.used} / {record.disk_space.total}
            </Text>
            <Progress 
              percent={parseInt(record.disk_space.use_percent)} 
              size="small" 
              status={parseInt(record.disk_space.use_percent) > 90 ? 'exception' : 'normal'}
              format={(percent) => `${percent}%`}
            />
          </Space>
        )
      },
    },
    {
      title: t('resources:repositories.status'),
      key: 'status',
      width: 400,
      render: (_: any, record: Repository) => (
        <Space direction="vertical" size={0}>
          <Space wrap>
            <Tag icon={<CheckCircleOutlined />} color="success">
              {t('resources:repositories.exists')}
            </Tag>
            {record.mounted && (
              <Tag color="blue">{t('resources:repositories.mounted')}</Tag>
            )}
            {record.accessible && (
              <Tag color="green">{t('resources:repositories.accessible')}</Tag>
            )}
            {record.has_rediaccfile && (
              <Tag color="purple">{t('resources:repositories.hasRediaccfile')}</Tag>
            )}
          </Space>
          {(record.docker_running || record.has_services) && (
            <Space wrap>
              {record.docker_running && (
                <Tag color="cyan">
                  Docker ({record.container_count} {t('resources:repositories.containers')})
                </Tag>
              )}
              {record.has_services && (
                <Tag color="orange">
                  {record.service_count} {t('resources:repositories.services')}
                </Tag>
              )}
            </Space>
          )}
          {record.mounted && record.mount_path && (
            <Text type="secondary" style={{ fontSize: '12px' }}>
              {t('resources:repositories.mountPath')}: {record.mount_path}
            </Text>
          )}
        </Space>
      ),
    },
    {
      title: t('resources:repositories.lastModified'),
      dataIndex: 'modified_human',
      key: 'modified_human',
      width: 200,
      render: (modified: string) => <Text type="secondary">{modified}</Text>,
    },
    {
      title: t('common:table.actions'),
      key: 'actions',
      width: 180,
      fixed: 'right',
      render: (_: any, record: Repository) => {
        // Build smart menu items based on repository state
        const menuItems = []
        
        // Mount and Up - if the repository is not mounted
        if (!record.mounted) {
          menuItems.push({
            key: 'mount',
            label: t('functions:functions.mount.name'),
            icon: <ApiOutlined />,
            onClick: () => handleQuickAction(record, 'mount')
          })
          menuItems.push({
            key: 'up',
            label: t('functions:functions.up.name'),
            icon: <PlayCircleOutlined style={{ color: '#52c41a' }} />,
            onClick: () => handleQuickAction(record, 'up', 4, 'mount')
          })
        }
        
        // Unmount - if mounted, accessible, and container_count is 0
        if (record.mounted && record.accessible && record.container_count === 0) {
          menuItems.push({
            key: 'unmount',
            label: t('functions:functions.unmount.name'),
            icon: <DisconnectOutlined />,
            onClick: () => handleQuickAction(record, 'unmount')
          })
        }
        
        // Up - if mounted, has Rediaccfile, and no containers running
        if (record.mounted && record.has_rediaccfile && record.container_count === 0) {
          menuItems.push({
            key: 'up',
            label: t('functions:functions.up.name'),
            icon: <PlayCircleOutlined style={{ color: '#52c41a' }} />,
            onClick: () => handleQuickAction(record, 'up')
          })
        }
        
        // Down and Unmount - if mounted, accessible, has_services, docker_running and container_count is not 0
        if (record.mounted && record.accessible && record.has_services && record.docker_running && record.container_count > 0) {
          menuItems.push({
            key: 'down',
            label: t('functions:functions.down.name'),
            icon: <StopOutlined style={{ color: '#ff4d4f' }} />,
            onClick: () => handleQuickAction(record, 'down')
          })
          menuItems.push({
            key: 'down-unmount',
            label: t('functions:functions.down.name') + ' + ' + t('functions:functions.unmount.name'),
            icon: <StopOutlined style={{ color: '#ff4d4f' }} />,
            onClick: () => handleQuickAction(record, 'down', 4, 'mount')
          })
        }
        
        // Resize - when not mounted
        if (!record.mounted) {
          menuItems.push({
            key: 'resize',
            label: t('functions:functions.resize.name'),
            icon: <ExpandOutlined />,
            onClick: () => handleRunFunction(record, 'resize')
          })
        }
        
        // Push - always available
        menuItems.push({
          key: 'push',
          label: t('functions:functions.push.name'),
          icon: <CloudUploadOutlined />,
          onClick: () => handleRunFunction(record, 'push')
        })
        
        // Pull - always available
        menuItems.push({
          key: 'pull',
          label: t('functions:functions.pull.name'),
          icon: <CloudDownloadOutlined />,
          onClick: () => handleRunFunction(record, 'pull')
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
            {record.mounted && (
              <Button
                size="small"
                icon={<DesktopOutlined />}
                onClick={() => setLocalCommandModal({ visible: true, repository: record })}
              >
                {t('resources:local')}
              </Button>
            )}
            <Dropdown
              menu={{ items: menuItems }}
              trigger={['click']}
            >
              <Button
                type="primary"
                size="small"
                icon={<FunctionOutlined />}
                loading={managedQueueMutation.isPending}
              >
                {t('machines:remote')}
              </Button>
            </Dropdown>
          </Space>
        )
      },
    },
  ]

  if (loading) {
    return (
      <div style={{ padding: '20px', textAlign: 'center' }}>
        <Spin tip={
          isQueued 
            ? t('resources:repositories.waitingInQueue')
            : t('resources:repositories.fetchingRepositories')
        } />
        {isQueued && queueId && (
          <div style={{ marginTop: 20 }}>
            <Text type="secondary">{t('resources:repositories.queuePosition')}: {managedQueueMutation.getQueuePosition?.(queueId) || '...'}</Text>
            <br />
            <Text type="secondary">{t('resources:repositories.checkQueueManager')}</Text>
          </div>
        )}
        {taskId && (
          <div style={{ marginTop: 20 }}>
            <Text type="secondary">Task ID: {taskId}</Text>
            <br />
            <Text type="secondary">
              {t('common:status.label')}: {traceData?.queueDetails?.status || t('common:status.initializing')}
              {traceData?.queueDetails?.status === 'PENDING' && ` (${t('common:status.waitingForExecution')})`}
              {traceData?.queueDetails?.status === 'ASSIGNED' && ` (${t('common:status.processing')})`}
              {traceData?.queueDetails?.status === 'PROCESSING' && ` (${t('common:status.running')})`}
            </Text>
          </div>
        )}
      </div>
    )
  }

  if (error) {
    return (
      <div style={{ padding: '20px' }}>
        <Alert
          message={t('common:messages.error')}
          description={error}
          type="error"
          showIcon
          action={
            <Button size="small" onClick={handleRefresh}>
              {t('common:actions.retry')}
            </Button>
          }
        />
      </div>
    )
  }

  return (
    <div style={{ padding: '0 20px 20px 20px', overflowX: 'auto' }}>
      {/* Machine Name Title when in grouped view */}
      {hideSystemInfo && (
        <div style={{ marginBottom: 16, paddingTop: 16, borderBottom: '1px solid #f0f0f0', paddingBottom: 12 }}>
          <Space direction="vertical" size={4}>
            <Space>
              <DesktopOutlined style={{ fontSize: 20, color: '#556b2f' }} />
              <Typography.Title level={4} style={{ margin: 0, color: '#556b2f' }}>
                {machine.machineName}
              </Typography.Title>
            </Space>
            <Space wrap size={8}>
              <Tag color="#8FBC8F">{machine.teamName}</Tag>
              <Tag color="green">{machine.bridgeName}</Tag>
              {machine.regionName && <Tag color="purple">{machine.regionName}</Tag>}
              <Tag color="blue">{machine.queueCount} {t('machines:queueItems')}</Tag>
            </Space>
          </Space>
        </div>
      )}
      
      {/* Repositories Label with Refresh Button */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, marginTop: hideSystemInfo ? 8 : 20 }}>
        <Typography.Title level={5} style={{ marginBottom: 0 }}>
          {t('resources:repositories.repositories')}
        </Typography.Title>
        <Space>
          {machine.vaultStatusTime && !loading && (
            <Text type="secondary" style={{ fontSize: '12px' }} title={`Raw: ${machine.vaultStatusTime}, Local: ${new Date(machine.vaultStatusTime).toLocaleString()}`}>
              {t('machines:lastUpdated')}: {getLocalizedRelativeTime(machine.vaultStatusTime, t)}
            </Text>
          )}
          <Button
            size="small"
            icon={<ReloadOutlined />}
            onClick={handleRefresh}
            loading={loading}
          >
            {t('common:actions.refresh')}
          </Button>
        </Space>
      </div>
      
      {/* Repository Table */}
      <Table
        columns={columns}
        dataSource={repositories}
        rowKey="name"
        size="small"
        pagination={false}
        scroll={{ x: 'max-content' }}
        expandable={{
          expandedRowRender: renderExpandedRow,
          expandedRowKeys: expandedRows,
          onExpandedRowsChange: (keys) => setExpandedRows(keys as string[]),
          rowExpandable: (record) => record.mounted && (record.has_services || record.container_count > 0),
          expandIcon: () => null, // Hide default expand icon since we have custom button
        }}
        locale={{
          emptyText: t('resources:repositories.noRepositories')
        }}
      />
      
      {/* System Containers Section */}
      {systemContainers.length > 0 && !hideSystemInfo && (
        <>
          <Typography.Title level={5} style={{ marginBottom: 16, marginTop: 32 }}>
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
            />
          </div>
        </>
      )}
      
      {/* System Information Section */}
      {systemInfo && !hideSystemInfo && (
        <>
          <Typography.Title level={5} style={{ marginBottom: 16, marginTop: systemContainers.length > 0 ? 0 : 32 }}>
            {t('resources:repositories.systemInfo')}
          </Typography.Title>
          <Card style={{ marginBottom: 20 }}>
          <Row gutter={[16, 16]}>
            <Col xs={24} sm={12} md={8}>
              <Card size="small" bordered={false} style={{ background: 'transparent', height: '100%' }}>
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, height: '100%' }}>
                  <div style={{ fontSize: 24, lineHeight: 1, paddingTop: 16 }}>
                    <DesktopOutlined />
                  </div>
                  <div style={{ flex: 1, paddingTop: 16 }}>
                    <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>
                      {t('resources:repositories.systemInfo')}
                    </Text>
                    <Text strong style={{ fontSize: 16, display: 'block' }}>{systemInfo.hostname}</Text>
                    <Space direction="vertical" size={0} style={{ marginTop: 4 }}>
                      <Text type="secondary" style={{ fontSize: 11 }}>{systemInfo.os_name}</Text>
                      <Text type="secondary" style={{ fontSize: 11 }}>Kernel: {systemInfo.kernel}</Text>
                      <Text type="secondary" style={{ fontSize: 11 }}>CPUs: {systemInfo.cpu_count} x {systemInfo.cpu_model}</Text>
                    </Space>
                  </div>
                </div>
              </Card>
            </Col>
            <Col xs={24} sm={12} md={8}>
              <Card size="small" bordered={false} style={{ background: 'transparent', height: '100%' }}>
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, height: '100%' }}>
                  <div style={{ fontSize: 24, lineHeight: 1, paddingTop: 16 }}>
                    <DatabaseOutlined />
                  </div>
                  <div style={{ flex: 1, paddingTop: 16 }}>
                    <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>
                      {t('resources:repositories.memory')}
                    </Text>
                    <Text strong style={{ fontSize: 16 }}>
                      {systemInfo.memory.used}
                      <Text type="secondary" style={{ fontSize: 14, fontWeight: 'normal' }}> / {systemInfo.memory.total}</Text>
                    </Text>
                    <Text type="secondary" style={{ display: 'block', fontSize: 11, marginTop: 4 }}>
                      {t('resources:repositories.available')}: {systemInfo.memory.available}
                    </Text>
                  </div>
                </div>
              </Card>
            </Col>
            <Col xs={24} sm={12} md={8}>
              <Card size="small" bordered={false} style={{ background: 'transparent', height: '100%' }}>
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, height: '100%' }}>
                  <div style={{ fontSize: 24, lineHeight: 1, paddingTop: 16 }}>
                    <ClockCircleOutlined />
                  </div>
                  <div style={{ flex: 1, paddingTop: 16 }}>
                    <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>
                      {t('resources:repositories.uptime')}
                    </Text>
                    <Text strong style={{ fontSize: 16 }}>{systemInfo.uptime}</Text>
                  </div>
                </div>
              </Card>
            </Col>
            <Col xs={24} sm={12} md={8}>
              <Card size="small" bordered={false} style={{ background: 'transparent', height: '100%' }}>
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, height: '100%' }}>
                  <div style={{ fontSize: 24, lineHeight: 1, paddingTop: 16 }}>
                    <GlobalOutlined />
                  </div>
                  <div style={{ flex: 1, paddingTop: 16 }}>
                    <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>
                      {t('resources:repositories.systemTime')}
                    </Text>
                    <Text strong style={{ fontSize: 16 }}>{systemInfo.system_time_human}</Text>
                    <Text type="secondary" style={{ display: 'block', fontSize: 11, marginTop: 2 }}>
                      {t('resources:repositories.timezone')}: {systemInfo.timezone}
                    </Text>
                  </div>
                </div>
              </Card>
            </Col>
            <Col xs={24} sm={12} md={8}>
              <Card size="small" bordered={false} style={{ background: 'transparent', height: '100%' }}>
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, height: '100%' }}>
                  <div style={{ fontSize: 24, lineHeight: 1, paddingTop: 16 }}>
                    <HddOutlined />
                  </div>
                  <div style={{ flex: 1, paddingTop: 16 }}>
                    <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>
                      {t('resources:repositories.rootDisk')}
                    </Text>
                    <Text strong style={{ fontSize: 16 }}>
                      {systemInfo.disk.used}
                      <Text type="secondary" style={{ fontSize: 14, fontWeight: 'normal' }}> / {systemInfo.disk.total}</Text>
                    </Text>
                    <Text type="secondary" style={{ display: 'block', fontSize: 11, marginTop: 2 }}>
                      {t('resources:repositories.available')}: {systemInfo.disk.available}
                    </Text>
                  </div>
                  <div style={{ width: 80, paddingTop: 16 }}>
                    <Progress 
                      percent={parseInt(systemInfo.disk.use_percent)} 
                      size="small" 
                      status={parseInt(systemInfo.disk.use_percent) > 90 ? 'exception' : 'normal'}
                      strokeWidth={4}
                      format={(percent) => `${percent}%`}
                    />
                  </div>
                </div>
              </Card>
            </Col>
            {systemInfo.datastore.path && (
              <Col xs={24} sm={12} md={8}>
                <Card size="small" bordered={false} style={{ background: 'transparent', height: '100%' }}>
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, height: '100%' }}>
                    <div style={{ fontSize: 24, lineHeight: 1, paddingTop: 16 }}>
                      <DatabaseOutlined />
                    </div>
                    <div style={{ flex: 1, paddingTop: 16 }}>
                      <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>
                        {t('resources:repositories.datastore')}
                      </Text>
                      <Text strong style={{ fontSize: 16 }}>
                        {systemInfo.datastore.used}
                        <Text type="secondary" style={{ fontSize: 14, fontWeight: 'normal' }}> / {systemInfo.datastore.total}</Text>
                      </Text>
                      <Text type="secondary" style={{ display: 'block', fontSize: 11, marginTop: 2, wordBreak: 'break-all' }}>
                        {systemInfo.datastore.path}
                      </Text>
                      <Text type="secondary" style={{ display: 'block', fontSize: 11 }}>
                        {t('resources:repositories.available')}: {systemInfo.datastore.available}
                      </Text>
                    </div>
                    <div style={{ width: 80, paddingTop: 16 }}>
                      <Progress 
                        percent={parseInt(systemInfo.datastore.use_percent)} 
                        size="small" 
                        status={parseInt(systemInfo.datastore.use_percent) > 90 ? 'exception' : 'normal'}
                        strokeWidth={4}
                        format={(percent) => `${percent}%`}
                      />
                    </div>
                  </div>
                </Card>
              </Col>
            )}
          </Row>
        </Card>
        </>
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
              console.error('Failed to cleanup repository after failed push:', deleteError)
            }
            setCreatedRepositoryName(null)
          }
        }}
      />
      
      {/* Local Command Modal - Desktop or Web version based on environment */}
      {localCommandModal.repository && (
        isDesktop ? (
          <DesktopLocalCommandModal
            visible={localCommandModal.visible}
            onClose={() => setLocalCommandModal({ visible: false, repository: null })}
            machine={machine.machineName}
            repository={localCommandModal.repository.name}
            token={currentToken}
            userEmail={userEmail}
            pluginContainers={containersData[localCommandModal.repository.name]?.containers || []}
          />
        ) : (
          <LocalCommandModal
            visible={localCommandModal.visible}
            onClose={() => setLocalCommandModal({ visible: false, repository: null })}
            machine={machine.machineName}
            repository={localCommandModal.repository.name}
            token={currentToken}
            userEmail={userEmail}
            pluginContainers={containersData[localCommandModal.repository.name]?.containers || []}
          />
        )
      )}
    </div>
  )
}