import React, { useEffect, useState } from 'react'
import { Table, Spin, Alert, Tag, Space, Typography, Button, Dropdown, Empty, Card, Row, Col, Statistic, Progress } from 'antd'
import { InboxOutlined, CheckCircleOutlined, CloseCircleOutlined, FunctionOutlined, PlayCircleOutlined, StopOutlined, ExpandOutlined, CloudUploadOutlined, PauseCircleOutlined, ReloadOutlined, DeleteOutlined, FileTextOutlined, LineChartOutlined, PlusOutlined, MinusOutlined, DesktopOutlined, ClockCircleOutlined, DatabaseOutlined, HddOutlined } from '@ant-design/icons'
import { useTranslation } from 'react-i18next'
import { type QueueFunction, useCreateQueueItem } from '@/api/queries/queue'
import { useQueueItemTrace } from '@/api/queries/queue'
import { useQuery } from '@tanstack/react-query'
import apiClient from '@/api/client'
import { useQueueVaultBuilder } from '@/hooks/useQueueVaultBuilder'
import { useManagedQueueItem } from '@/hooks/useManagedQueueItem'
import { Machine } from '@/types'
import { useTeams } from '@/api/queries/teams'
import { useRepositories } from '@/api/queries/repositories'
import { queueMonitoringService } from '@/services/queueMonitoringService'
import queueManagerService from '@/services/queueManagerService'
import { repositoryDataService } from '@/services/repositoryDataService'
import type { ColumnsType } from 'antd/es/table'
import FunctionSelectionModal from '@/components/common/FunctionSelectionModal'
import QueueItemTraceModal from '@/components/common/QueueItemTraceModal'
import { showMessage } from '@/utils/messages'

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
}

// Component to monitor a task and update state when complete
const TaskMonitor: React.FC<{
  taskId: string | null
  onComplete: (data: any) => void
  onError: (error: string) => void
}> = ({ taskId, onComplete, onError }) => {
  const { data: traceData } = useQueueItemTrace(taskId, !!taskId)
  
  useEffect(() => {
    if (!traceData) return
    
    if (traceData?.queueDetails?.status === 'COMPLETED') {
      if (traceData?.responseVaultContent?.vaultContent) {
        try {
          const vaultContent = JSON.parse(traceData.responseVaultContent.vaultContent)
          if (vaultContent.result) {
            const result = JSON.parse(vaultContent.result)
            if (result.stdout) {
              const parsedResult = JSON.parse(result.stdout)
              onComplete(parsedResult)
            } else if (result.command_output) {
              // Some functions return command_output instead of stdout
              const parsedResult = JSON.parse(result.command_output)
              onComplete(parsedResult)
            }
          }
        } catch (error) {
          // Failed to parse response: error
          onError('Failed to parse response')
        }
      } else {
        onError('No response data received')
      }
    } else if (traceData?.queueDetails?.status === 'FAILED' || traceData?.queueDetails?.status === 'CANCELED') {
      onError(traceData?.responseVaultContent?.error || 'Task failed')
    }
  }, [traceData, onComplete, onError])
  
  return null
}

export const MachineRepositoryList: React.FC<MachineRepositoryListProps> = ({ machine, onActionComplete }) => {
  const { t } = useTranslation(['resources', 'common', 'machines', 'functions'])
  const [repositories, setRepositories] = useState<Repository[]>([])
  const [systemContainers, setSystemContainers] = useState<any[]>([])
  const [systemInfo, setSystemInfo] = useState<SystemInfo | null>(null)
  const [loading, setLoading] = useState(true)
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
  const [loadingServices, setLoadingServices] = useState<Record<string, boolean>>({})
  const [loadingContainers, setLoadingContainers] = useState<Record<string, boolean>>({})
  const [servicesTaskIds, setServicesTaskIds] = useState<Record<string, string>>({})
  const [containersTaskIds, setContainersTaskIds] = useState<Record<string, string>>({})
  
  // Use direct queue item creation for list operations (not managed)
  const createQueueItemMutation = useCreateQueueItem()
  // Keep managed queue for function execution
  const managedQueueMutation = useManagedQueueItem()
  const { buildQueueVault } = useQueueVaultBuilder()
  const { data: teams } = useTeams()
  const { data: teamRepositories = [], isLoading: repositoriesLoading } = useRepositories(machine.teamName)
  
  // Use queue trace to monitor the task
  const { data: traceData } = useQueueItemTrace(taskId, !!taskId)

  useEffect(() => {
    // Only fetch when repositories are loaded
    if (!repositoriesLoading && machine) {
      fetchRepositories()
    }
  }, [machine, repositoriesLoading])

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
        
        // Start monitoring the task with bridge info for priority 1 tasks
        queueMonitoringService.addTask(
          item.taskId,
          machine.teamName,
          machine.machineName,
          'PENDING', // Initial status when task is created
          undefined, // retryCount
          undefined, // lastFailureReason
          machine.bridgeName, // bridgeName for priority 1 tracking
          1 // priority 1 for repository list tasks
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
                  const matchingRepo = teamRepositories.find(r => r.repositoryGuid === repoGuid)
                  if (matchingRepo) {
                    const repoName = matchingRepo.repositoryName
                    if (servicesMap[repoName]) {
                      servicesMap[repoName].services.push(service)
                    }
                  }
                })
                
                // Services data processed: servicesMap
                
                // Update all services data at once
                setServicesData(servicesMap)
                // Clear loading states for all repositories
                const loadingStates: Record<string, boolean> = {}
                mappedRepositories.forEach((repo: Repository) => {
                  loadingStates[repo.name] = false
                })
                setLoadingServices(loadingStates)
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
                  const matchingRepo = teamRepositories.find(r => r.repositoryGuid === repoGuid)
                  if (matchingRepo) {
                    const repoName = matchingRepo.repositoryName
                    if (containersMap[repoName]) {
                      containersMap[repoName].containers.push(container)
                    }
                  }
                })
                
                // Containers data processed: containersMap
                
                // Update all containers data at once
                setContainersData(containersMap)
                // Clear loading states for all repositories
                const loadingStates: Record<string, boolean> = {}
                mappedRepositories.forEach((repo: Repository) => {
                  loadingStates[repo.name] = false
                })
                setLoadingContainers(loadingStates)
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

  const fetchRepositories = async () => {
    try {
      setLoading(true)
      setError(null)
      
      // Find team vault data
      const team = teams?.find(t => t.teamName === machine.teamName)
      
      // Collect all repository credentials from team repositories
      const allRepositoryCredentials: Record<string, string> = {}
      teamRepositories.forEach(repo => {
        if (repo.vaultContent) {
          try {
            const vaultData = JSON.parse(repo.vaultContent)
            if (vaultData.credential) {
              // Use repositoryGuid as the key instead of repositoryName
              allRepositoryCredentials[repo.repositoryGuid] = vaultData.credential
            }
          } catch (e) {
            // Silently skip repositories with invalid vault data
            // Silently skip repositories with invalid vault data
          }
        }
      })
      
      
      // Build queue vault for the list function
      const queueVault = await buildQueueVault({
        teamName: machine.teamName,
        machineName: machine.machineName,
        bridgeName: machine.bridgeName,
        functionName: 'list',
        params: {},
        priority: 1, // Highest priority for UI tasks
        description: `List repositories on ${machine.machineName}`,
        addedVia: 'machine-repository-list',
        teamVault: team?.vaultContent || '{}',
        machineVault: machine.vaultContent || '{}',
        allRepositoryCredentials
      })
      
      // Use managed queue for priority 1 tasks so they appear in Queue Manager
      const response = await managedQueueMutation.mutateAsync({
        teamName: machine.teamName,
        machineName: machine.machineName,
        bridgeName: machine.bridgeName,
        queueVault,
        priority: 1
      })
      
      // Queue item response: response
      
      if (response?.taskId) {
        // Task ID received: response.taskId
        setTaskId(response.taskId)
        // Start monitoring the task
        showMessage('info', 'Repository list request submitted. Monitoring task...')
        
        // Start monitoring the task with bridge info for priority 1 tasks
        queueMonitoringService.addTask(
          response.taskId,
          machine.teamName,
          machine.machineName,
          'PENDING', // Initial status when task is created
          undefined, // retryCount
          undefined, // lastFailureReason
          machine.bridgeName, // bridgeName for priority 1 tracking
          1 // priority 1 for repository list tasks
        )
      } else if (response?.isQueued && response?.queueId) {
        // Item was queued for highest priority management
        showMessage('info', t('resources:repositories.requestQueued'))
        setQueueId(response.queueId)
        setIsQueued(true)
        // Keep loading state while we wait for task ID
      } else {
        // No taskId in response: response
        setError('Failed to create queue item')
        setLoading(false)
      }
    } catch (err: any) {
      setError(err.message || 'Failed to fetch repositories')
      setLoading(false)
    }
  }

  const handleRunFunction = (repository: Repository, functionName?: string) => {
    setSelectedRepository(repository)
    setSelectedFunction(functionName || null)
    setFunctionModalOpen(true)
  }

  const handleQuickAction = async (repository: Repository, functionName: string, priority: number = 4) => {
    try {
      // Find team vault data
      const team = teams?.find(t => t.teamName === machine.teamName)
      
      // Find the repository vault data
      const repositoryData = teamRepositories.find(r => r.repositoryName === repository.name)
      
      if (!repositoryData || !repositoryData.vaultContent) {
        showMessage('error', t('resources:repositories.noCredentialsFound', { name: repository.name }))
        return
      }
      
      // Build queue vault
      const queueVault = await buildQueueVault({
        teamName: machine.teamName,
        machineName: machine.machineName,
        bridgeName: machine.bridgeName,
        functionName: functionName,
        params: {
          repo: repositoryData.repositoryGuid,
          grand: repositoryData.grandGuid || ''
        },
        priority: priority,
        description: `${functionName} ${repository.name}`,
        addedVia: 'machine-repository-list-quick',
        teamVault: team?.vaultContent || '{}',
        machineVault: machine.vaultContent || '{}',
        repositoryGuid: repositoryData.repositoryGuid,
        repositoryVault: repositoryData.vaultContent
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

  const fetchServicesData = async (repository: Repository) => {
    setLoadingServices(prev => ({ ...prev, [repository.name]: true }))
    try {
      // Find team vault data
      const team = teams?.find(t => t.teamName === machine.teamName)
      
      // Find the repository vault data
      const repositoryData = teamRepositories.find(r => r.repositoryName === repository.name)
      
      if (!repositoryData || !repositoryData.vaultContent) {
        showMessage('error', t('resources:repositories.noCredentialsFound', { name: repository.name }))
        setLoadingServices(prev => ({ ...prev, [repository.name]: false }))
        return
      }
      
      // Build queue vault for service_list
      const queueVault = await buildQueueVault({
        teamName: machine.teamName,
        machineName: machine.machineName,
        bridgeName: machine.bridgeName,
        functionName: 'service_list',
        params: {
          repo: repositoryData.repositoryGuid
        },
        priority: 4,
        description: `List services for ${repository.name}`,
        addedVia: 'machine-repository-list-services',
        teamVault: team?.vaultContent || '{}',
        machineVault: machine.vaultContent || '{}',
        repositoryGuid: repositoryData.repositoryGuid,
        repositoryVault: repositoryData.vaultContent
      })
      
      const response = await managedQueueMutation.mutateAsync({
        teamName: machine.teamName,
        machineName: machine.machineName,
        bridgeName: machine.bridgeName,
        queueVault,
        priority: 4
      })
      
      if (response?.taskId) {
        setServicesTaskIds(prev => ({ ...prev, [repository.name]: response.taskId }))
      }
    } catch (error) {
      // Failed to fetch services: error
      showMessage('error', t('resources:repositories.errorLoadingServices'))
      setLoadingServices(prev => ({ ...prev, [repository.name]: false }))
    }
  }

  const fetchContainersData = async (repository: Repository) => {
    setLoadingContainers(prev => ({ ...prev, [repository.name]: true }))
    try {
      // Find team vault data
      const team = teams?.find(t => t.teamName === machine.teamName)
      
      // Find the repository vault data
      const repositoryData = teamRepositories.find(r => r.repositoryName === repository.name)
      
      if (!repositoryData || !repositoryData.vaultContent) {
        showMessage('error', t('resources:repositories.noCredentialsFound', { name: repository.name }))
        setLoadingContainers(prev => ({ ...prev, [repository.name]: false }))
        return
      }
      
      // Build queue vault for container_list
      const queueVault = await buildQueueVault({
        teamName: machine.teamName,
        machineName: machine.machineName,
        bridgeName: machine.bridgeName,
        functionName: 'container_list',
        params: {
          repo: repositoryData.repositoryGuid
        },
        priority: 4,
        description: `List containers for ${repository.name}`,
        addedVia: 'machine-repository-list-containers',
        teamVault: team?.vaultContent || '{}',
        machineVault: machine.vaultContent || '{}',
        repositoryGuid: repositoryData.repositoryGuid,
        repositoryVault: repositoryData.vaultContent
      })
      
      const response = await managedQueueMutation.mutateAsync({
        teamName: machine.teamName,
        machineName: machine.machineName,
        bridgeName: machine.bridgeName,
        queueVault,
        priority: 4
      })
      
      if (response?.taskId) {
        setContainersTaskIds(prev => ({ ...prev, [repository.name]: response.taskId }))
      }
    } catch (error) {
      // Failed to fetch containers: error
      showMessage('error', t('resources:repositories.errorLoadingContainers'))
      setLoadingContainers(prev => ({ ...prev, [repository.name]: false }))
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
        repositoryVault: repositoryData.vaultContent
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
        
        // Refresh containers data after action
        setTimeout(() => {
          fetchContainersData(repository)
        }, 2000)
      } else if (response?.isQueued) {
        showMessage('info', t('resources:repositories.highestPriorityQueued'))
      }
    } catch (error) {
      showMessage('error', t('resources:repositories.failedToCreateQueueItem'))
    }
  }

  const handleSystemContainerAction = async (container: any, action: string) => {
    try {
      // Find team vault data
      const team = teams?.find(t => t.teamName === machine.teamName)
      
      // Build params based on action
      const params: Record<string, any> = {
        container: container.id || container.name,
        system: 'true' // Indicate this is a system container
      }
      
      // Add action-specific params
      if (action === 'container_remove') {
        params.force = 'false' // Default to safe remove
      } else if (action === 'container_logs') {
        params.lines = '100'
        params.follow = 'false'
      }
      
      // Build queue vault for system container action
      const queueVault = await buildQueueVault({
        teamName: machine.teamName,
        machineName: machine.machineName,
        bridgeName: machine.bridgeName,
        functionName: action,
        params,
        priority: 4,
        description: `${action} system container ${container.name}`,
        addedVia: 'machine-repository-list-system-container-action',
        teamVault: team?.vaultContent || '{}',
        machineVault: machine.vaultContent || '{}'
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
        
        // Refresh repositories data after action to get updated system containers
        setTimeout(() => {
          fetchRepositories()
        }, 2000)
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
      
      // Build queue vault
      const queueVault = await buildQueueVault({
        teamName: machine.teamName,
        machineName: machine.machineName,
        bridgeName: machine.bridgeName,
        functionName: functionData.function.name,
        params: functionData.params,
        priority: functionData.priority,
        description: functionData.description,
        addedVia: 'machine-repository-list',
        teamVault: team?.vaultContent || '{}',
        machineVault: machine.vaultContent || '{}',
        repositoryGuid: repositoryData.repositoryGuid,
        repositoryVault: repositoryData.vaultContent
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
      // Error is handled by the mutation
      showMessage('error', t('resources:repositories.failedToCreateQueueItem'))
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
    
    // Container columns
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
          menuItems.push({ type: 'divider' })
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
    
  const renderExpandedRow = (record: Repository) => {
    const services = servicesData[record.name]
    const containers = containersData[record.name]
    const isLoadingServices = loadingServices[record.name]
    const isLoadingContainers = loadingContainers[record.name]
    
    return (
      <div style={{ padding: '16px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <Typography.Title level={5} style={{ margin: 0 }}>{t('resources:repositories.servicesAndContainers')}</Typography.Title>
          <Button
            type="text"
            size="small"
            icon={<ReloadOutlined />}
            onClick={() => {
              // Refresh both services and containers data
              if (record.has_services) {
                fetchServicesData(record)
              }
              if (record.docker_running && record.accessible) {
                fetchContainersData(record)
              }
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
          {isLoadingServices ? (
            <div style={{ textAlign: 'center', padding: 20 }}>
              <Spin tip={t('resources:repositories.loadingServices')} />
            </div>
          ) : services?.error ? (
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
          {isLoadingContainers ? (
            <div style={{ textAlign: 'center', padding: 20 }}>
              <Spin tip={t('resources:repositories.loadingContainers')} />
            </div>
          ) : containers?.error ? (
            <Alert message={t('resources:repositories.errorLoadingContainers')} description={containers.error} type="error" />
          ) : containers?.containers && containers.containers.length > 0 ? (
            <Table
              columns={containerColumns}
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
                // Only fetch if we don't already have the data from the initial list call
                if (record.has_services && !servicesData[record.name]) {
                  fetchServicesData(record)
                }
                if (record.docker_running && record.accessible && !containersData[record.name]) {
                  fetchContainersData(record)
                }
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
      width: 120,
      fixed: 'right',
      render: (_: any, record: Repository) => {
        // Build smart menu items based on repository state
        const menuItems = []
        
        // Mount - if the repository is not mounted
        if (!record.mounted) {
          menuItems.push({
            key: 'mount',
            label: t('functions:functions.mount.name'),
            icon: <PlayCircleOutlined />,
            onClick: () => handleQuickAction(record, 'mount')
          })
        }
        
        // Unmount - if mounted, accessible, and container_count is 0
        if (record.mounted && record.accessible && record.container_count === 0) {
          menuItems.push({
            key: 'unmount',
            label: t('functions:functions.unmount.name'),
            icon: <StopOutlined />,
            onClick: () => handleQuickAction(record, 'unmount')
          })
        }
        
        // Up - if mounted, accessible, has_services, docker_running and container_count is 0
        if (record.mounted && record.accessible && record.has_services && record.docker_running && record.container_count === 0) {
          menuItems.push({
            key: 'up',
            label: t('functions:functions.up.name'),
            icon: <PlayCircleOutlined style={{ color: '#52c41a' }} />,
            onClick: () => handleQuickAction(record, 'up')
          })
        }
        
        // Down - if mounted, accessible, has_services, docker_running and container_count is not 0
        if (record.mounted && record.accessible && record.has_services && record.docker_running && record.container_count > 0) {
          menuItems.push({
            key: 'down',
            label: t('functions:functions.down.name'),
            icon: <StopOutlined style={{ color: '#ff4d4f' }} />,
            onClick: () => handleQuickAction(record, 'down')
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
        
        // Always add divider and advanced option at the end
        if (menuItems.length > 0) {
          menuItems.push({
            type: 'divider'
          })
        }
        
        menuItems.push({
          key: 'advanced',
          label: t('machines:advanced'),
          icon: <FunctionOutlined />,
          onClick: () => handleRunFunction(record)
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
            <Button size="small" onClick={fetchRepositories}>
              {t('common:actions.retry')}
            </Button>
          }
        />
      </div>
    )
  }

  return (
    <div style={{ padding: '0 20px 20px 20px', overflowX: 'auto' }}>
      {/* System Information Section */}
      {systemInfo && (
        <Card style={{ marginBottom: 20, marginTop: 20 }}>
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
      )}
      
      {/* System Containers Section */}
      {systemContainers.length > 0 && (
        <>
          <Typography.Title level={5} style={{ marginBottom: 16, marginTop: 20 }}>
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
      
      {/* Repositories Label */}
      <Typography.Title level={5} style={{ marginBottom: 16, marginTop: systemContainers.length > 0 ? 0 : 20 }}>
        {t('resources:repositories.repositories')}
      </Typography.Title>
      
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
      
      {/* Task Monitors for Services */}
      {Object.entries(servicesTaskIds).map(([repoName, taskId]) => (
        <TaskMonitor
          key={`service-${repoName}`}
          taskId={taskId}
          onComplete={(data) => {
            setServicesData(prev => ({ ...prev, [repoName]: data }))
            setLoadingServices(prev => ({ ...prev, [repoName]: false }))
            setServicesTaskIds(prev => {
              const newIds = { ...prev }
              delete newIds[repoName]
              return newIds
            })
          }}
          onError={(error) => {
            setServicesData(prev => ({ ...prev, [repoName]: { error } }))
            setLoadingServices(prev => ({ ...prev, [repoName]: false }))
            setServicesTaskIds(prev => {
              const newIds = { ...prev }
              delete newIds[repoName]
              return newIds
            })
          }}
        />
      ))}
      
      {/* Task Monitors for Containers */}
      {Object.entries(containersTaskIds).map(([repoName, taskId]) => (
        <TaskMonitor
          key={`container-${repoName}`}
          taskId={taskId}
          onComplete={(data) => {
            setContainersData(prev => ({ ...prev, [repoName]: data }))
            setLoadingContainers(prev => ({ ...prev, [repoName]: false }))
            setContainersTaskIds(prev => {
              const newIds = { ...prev }
              delete newIds[repoName]
              return newIds
            })
          }}
          onError={(error) => {
            setContainersData(prev => ({ ...prev, [repoName]: { error } }))
            setLoadingContainers(prev => ({ ...prev, [repoName]: false }))
            setContainersTaskIds(prev => {
              const newIds = { ...prev }
              delete newIds[repoName]
              return newIds
            })
          }}
        />
      ))}
      
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
            <Space>
              <Text>{t('resources:repositories.repository')}:</Text>
              <Tag color="#8FBC8F">{selectedRepository.name}</Tag>
              <Text>•</Text>
              <Text>{t('machines:machine')}:</Text>
              <Tag color="#556b2f">{machine.machineName}</Tag>
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
        preselectedFunction={selectedFunction}
      />
      
      {/* Queue Item Trace Modal */}
      <QueueItemTraceModal
        taskId={queueTraceModal.taskId}
        visible={queueTraceModal.visible}
        onClose={() => {
          setQueueTraceModal({ visible: false, taskId: null })
          // Refresh repositories when modal is closed
          fetchRepositories()
        }}
      />
    </div>
  )
}