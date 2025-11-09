import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Spin, Alert, Tag, Space, Typography, Button, Dropdown, Tooltip, Modal, Input } from 'antd'
import { useTableStyles, useComponentStyles } from '@/hooks/useComponentStyles'
import { CheckCircleOutlined, FunctionOutlined, PlayCircleOutlined, StopOutlined, ExpandOutlined, CloudUploadOutlined, SaveOutlined, PauseCircleOutlined, ReloadOutlined, DeleteOutlined, DesktopOutlined, ClockCircleOutlined, DatabaseOutlined, DisconnectOutlined, KeyOutlined, AppstoreOutlined, CloudServerOutlined, RightOutlined, CopyOutlined, RiseOutlined, StarOutlined, EditOutlined, ShrinkOutlined, ControlOutlined, CaretDownOutlined, CaretRightOutlined, FolderOutlined, EyeOutlined } from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import * as S from './styles'
import { type QueueFunction } from '@/api/queries/queue'
import { useQueueVaultBuilder } from '@/hooks/useQueueVaultBuilder'
import { useManagedQueueItem } from '@/hooks/useManagedQueueItem'
import { Machine } from '@/types'
import { useTeams } from '@/api/queries/teams'
import { useRepositories, useCreateRepository, useDeleteRepository, usePromoteRepositoryToGrand, useUpdateRepositoryName } from '@/api/queries/repositories'
import { useMachines } from '@/api/queries/machines'
import { useStorage } from '@/api/queries/storage'
import type { ColumnsType } from 'antd/es/table'
import FunctionSelectionModal from '@/components/common/FunctionSelectionModal'
import { LocalActionsMenu } from '../LocalActionsMenu'
import { showMessage } from '@/utils/messages'
import { useAppSelector } from '@/store/store'

const { Text } = Typography

interface Repository {
  name: string
  repoTag?: string  // Repository tag (e.g., 'latest', 'fork-2025-01-09-14-30-00')
  size: number
  size_human: string
  modified: number
  modified_human: string
  mounted: boolean
  mount_path: string
  image_path: string
  accessible: boolean
  has_rediaccfile: boolean
  docker_available: boolean  // Docker daemon is running and accessible
  docker_running: boolean    // Containers are actually running (container_count > 0)
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

// Helper function to format repository display name as name:tag
const getRepositoryDisplayName = (repo: Repository): string => {
  return `${repo.name}:${repo.repoTag || 'latest'}`
}

// Data structure for grouped repositories
interface GroupedRepository {
  name: string                    // Repository name (e.g., "webapp")
  tags: Repository[]              // All tags for this name
  grandTag: Repository | null     // The grand repository (tag='latest', no parent)
  forkTags: Repository[]          // Fork repositories (tag!='latest' or has parent)
  isExpanded: boolean             // UI state for expand/collapse
}

// Extended Repository interface for table rendering
interface RepositoryTableRow extends Repository {
  key?: string
  _isGroupHeader?: boolean
  _groupData?: GroupedRepository
  _isTagRow?: boolean
  _indentLevel?: number
  _isLastInGroup?: boolean
}

// Helper to group repositories by name
const groupRepositoriesByName = (repos: Repository[], teamRepos: any[]): GroupedRepository[] => {
  // Group by name
  const grouped = repos.reduce((acc, repo) => {
    if (!acc[repo.name]) {
      acc[repo.name] = []
    }
    acc[repo.name].push(repo)
    return acc
  }, {} as Record<string, Repository[]>)

  // Transform to GroupedRepository structure
  return Object.entries(grouped).map(([name, tags]) => {
    // Find grand repository - one with no parent or parent equals self
    const grandTag = tags.find(r => {
      const tagData = teamRepos.find(tr =>
        tr.repositoryName === r.name &&
        (tr.repoTag || 'latest') === (r.repoTag || 'latest')
      )
      // Grand repo has no parentGuid or parentGuid equals repositoryGuid
      return tagData && (!tagData.parentGuid || tagData.parentGuid === tagData.repositoryGuid)
    }) || null

    // All other tags are forks
    const forkTags = tags.filter(r => r !== grandTag)

    return {
      name,
      tags,
      grandTag,
      forkTags,
      isExpanded: false  // Start collapsed
    }
  }).sort((a, b) => a.name.localeCompare(b.name))  // Sort by name
}

interface PortMapping {
  host: string
  host_port: string
  container_port: string
  protocol: string
}

interface Container {
  id: string
  name: string
  state: string
  status?: string
  image?: string
  ports?: string
  created?: string
  port_mappings?: PortMapping[]
  [key: string]: any // eslint-disable-line @typescript-eslint/no-explicit-any -- Allow additional properties from API
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
  onContainerClick?: (container: Container) => void
  highlightedContainer?: Container | null
  isLoading?: boolean
  onRefreshMachines?: () => Promise<any>
  refreshKey?: number // Used to trigger re-rendering when parent wants to force refresh
  onQueueItemCreated?: (taskId: string, machineName: string) => void // Callback to open parent's QueueItemTraceModal with machine context
}


export const MachineRepositoryList: React.FC<MachineRepositoryListProps> = ({ machine, onActionComplete, hideSystemInfo = false, onCreateRepository, onRepositoryClick, highlightedRepository, onContainerClick: _onContainerClick, highlightedContainer: _highlightedContainer, isLoading, onRefreshMachines: _onRefreshMachines, refreshKey, onQueueItemCreated }) => {
  const { t } = useTranslation(['resources', 'common', 'machines', 'functions'])
  const navigate = useNavigate()
  const [modal, contextHolder] = Modal.useModal()
  const userEmail = useAppSelector((state) => state.auth.user?.email || '')
  const tableStyles = useTableStyles()
  const componentStyles = useComponentStyles()
  const [_repositories, setRepositories] = useState<Repository[]>([])
  const [systemContainers] = useState<any[]>([])
  const [_systemInfo, setSystemInfo] = useState<SystemInfo | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedRepository, setSelectedRepository] = useState<Repository | null>(null)
  const [functionModalOpen, setFunctionModalOpen] = useState(false)
  const [selectedFunction, setSelectedFunction] = useState<string | null>(null)
  const [_servicesData, setServicesData] = useState<Record<string, any>>({})
  const [containersData, setContainersData] = useState<Record<string, any>>({})
  const [createdRepositoryName, setCreatedRepositoryName] = useState<string | null>(null)
  const [createdRepositoryTag, setCreatedRepositoryTag] = useState<string | null>(null)
  const [groupedRepositories, setGroupedRepositories] = useState<GroupedRepository[]>([])

  // Keep managed queue for function execution
  const managedQueueMutation = useManagedQueueItem()
  const { buildQueueVault } = useQueueVaultBuilder()
  const { data: teams } = useTeams()
  const { data: teamRepositories = [], isLoading: repositoriesLoading, refetch: refetchRepositories } = useRepositories(machine.teamName)
  const { data: machinesData = [] } = useMachines(machine.teamName)
  const { data: storageData = [] } = useStorage(machine.teamName)
  const createRepositoryMutation = useCreateRepository()
  const deleteRepositoryMutation = useDeleteRepository()
  const promoteRepositoryMutation = usePromoteRepositoryToGrand()
  const updateRepositoryNameMutation = useUpdateRepositoryName()

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
                        repoTag: matchingRepo.repoTag,  // Include the tag to distinguish grand from forks
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
                    result.containers.forEach((container: Container) => {
                      // Check if this container belongs to this repository
                      const belongsToRepo = container.repository === repo.name
                      
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

                // Sort repositories hierarchically: originals first, then their children
                const sortedRepositories = repositoriesWithPluginCounts.sort((a: Repository, b: Repository) => {
                  const aData = teamRepositories.find(r => r.repositoryName === a.name)
                  const bData = teamRepositories.find(r => r.repositoryName === b.name)

                  // Get family names (grand parent name or self)
                  const aFamily = aData?.grandGuid ? teamRepositories.find(r => r.repositoryGuid === aData.grandGuid)?.repositoryName || a.name : a.name
                  const bFamily = bData?.grandGuid ? teamRepositories.find(r => r.repositoryGuid === bData.grandGuid)?.repositoryName || b.name : b.name

                  // First sort by family
                  if (aFamily !== bFamily) {
                    return aFamily.localeCompare(bFamily)
                  }

                  // Within same family: originals (no parent) first, then clones
                  const aIsOriginal = !aData?.parentGuid
                  const bIsOriginal = !bData?.parentGuid

                  if (aIsOriginal !== bIsOriginal) {
                    return aIsOriginal ? -1 : 1
                  }

                  // Within same status (both original or both clones), sort alphabetically
                  return a.name.localeCompare(b.name)
                })

                setRepositories(sortedRepositories)

                // Group repositories by name for hierarchical display
                const grouped = groupRepositoriesByName(sortedRepositories, teamRepositories)
                setGroupedRepositories(grouped)

                // Process containers and services if included
                if (result.containers && Array.isArray(result.containers)) {
                  // Group containers by repository
                  const containersMap: Record<string, any> = {}
                  
                  // Initialize empty containers for all repositories
                  mappedRepositories.forEach((repo: Repository) => {
                    containersMap[repo.name] = { containers: [], error: null }
                  })
                  
                  result.containers.forEach((container: any) => {
                    // Check if container has a repository field
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
  }, [machine, repositoriesLoading, teamRepositories, refreshKey, setRepositories, setServicesData, setContainersData, setLoading, setError])

  const handleRefresh = () => {
    // Trigger parent component to refresh machine data
    if (onActionComplete) {
      onActionComplete()
    }
  }

  // Toggle expand/collapse for a repository group
  const toggleRepositoryGroup = (repoName: string) => {
    setGroupedRepositories(prev =>
      prev.map(group =>
        group.name === repoName
          ? { ...group, isExpanded: !group.isExpanded }
          : group
      )
    )
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
        repositoryVault: grandRepositoryVault,
        repositoryLoopbackIp: repositoryData.repoLoopbackIp,
        repositoryNetworkMode: repositoryData.repoNetworkMode,
        repositoryTag: repositoryData.repoTag
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
        if (onQueueItemCreated) {
          onQueueItemCreated(response.taskId, machine.machineName)
        }
      } else if (response?.isQueued) {
        showMessage('info', t('resources:repositories.highestPriorityQueued'))
      }
    } catch (error) {
      showMessage('error', t('resources:repositories.failedToCreateQueueItem'))
    }
  }

  const handleForkRepository = async (repository: Repository) => {
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

      // Generate fork tag with timestamp
      const timestamp = new Date().toISOString().slice(0, 19).replace('T', '-').replace(/:/g, '-')
      const forkTag = `fork-${timestamp}`  // e.g., fork-2025-01-09-14-30-00

      // Create a new repository credential for the fork (same name, different tag)
      try {
        await createRepositoryMutation.mutateAsync({
          teamName: machine.teamName,
          repositoryName: repository.name,  // SAME NAME
          repositoryTag: forkTag,  // NEW TAG
          parentRepoName: repository.name
        })

        // Store the created repository name and tag for potential cleanup
        setCreatedRepositoryName(repository.name)  // Track the name (not destFilename)
        setCreatedRepositoryTag(forkTag)  // NEW: Track the tag for cleanup

        // Immediately refresh the repositories list to get the new repository
        const { data: updatedRepos } = await refetchRepositories()

        // Find the newly created fork repository to get its GUID (same name, new tag)
        const newRepo = updatedRepos?.find(r => r.repositoryName === repository.name && r.repoTag === forkTag)

        if (!newRepo || !newRepo.repositoryGuid) {
          throw new Error('Could not find newly created fork repository')
        }

        // Build params for push function
        const state = repository.mounted ? 'online' : 'offline'
        const params: Record<string, any> = {
          repo: repositoryData.repositoryGuid,
          dest: newRepo.repositoryGuid,
          destinationType: 'machine',
          to: machine.machineName,
          state: state,
          grand: repositoryData.grandGuid || repositoryData.repositoryGuid || ''
        }

        // Build queue vault
        const queueVault = await buildQueueVault({
          teamName: machine.teamName,
          machineName: machine.machineName,
          bridgeName: machine.bridgeName,
          functionName: 'push',
          params,
          priority: 4,
          description: `Fork ${repository.name}:${repository.repoTag || 'latest'} to ${repository.name}:${forkTag}`,
          addedVia: 'machine-repository-list-fork',
          teamVault: team?.vaultContent || '{}',
          machineVault: machine.vaultContent || '{}',
          repositoryGuid: repositoryData.repositoryGuid,
          repositoryVault: grandRepositoryVault,
          repositoryLoopbackIp: newRepo.repoLoopbackIp,
          repositoryNetworkMode: newRepo.repoNetworkMode,
          repositoryTag: newRepo.repoTag,
          destinationMachineVault: machine.vaultContent
        })

        const response = await managedQueueMutation.mutateAsync({
          teamName: machine.teamName,
          machineName: machine.machineName,
          bridgeName: machine.bridgeName,
          queueVault,
          priority: 4
        })

        if (response?.taskId) {
          showMessage('success', t('resources:repositories.forkStarted', { dest: `${repository.name}:${forkTag}` }))
          if (onQueueItemCreated) {
            onQueueItemCreated(response.taskId, machine.machineName)
          }
        } else if (response?.isQueued) {
          showMessage('info', t('resources:repositories.highestPriorityQueued'))
        }

      } catch (createError) {
        // If we already created the repository but failed to start the fork, clean it up
        if (createdRepositoryName && createdRepositoryTag) {
          try {
            await deleteRepositoryMutation.mutateAsync({
              teamName: machine.teamName,
              repositoryName: createdRepositoryName,
              repositoryTag: createdRepositoryTag
            })
          } catch (deleteError) {
            // Failed to cleanup repository after error
          }
        }
        showMessage('error', t('resources:repositories.failedToForkRepository'))
        return
      }

    } catch (error) {
      showMessage('error', t('resources:repositories.failedToForkRepository'))
    }
  }

  const handleDeleteFork = async (repository: Repository) => {
    // Find the repository data
    const repositoryData = teamRepositories.find(r => r.repositoryName === repository.name)

    if (!repositoryData) {
      showMessage('error', t('resources:repositories.repositoryNotFound'))
      return
    }

    // Safety check: only allow deletion of clones (repositories with a parent)
    if (!repositoryData.grandGuid || repositoryData.grandGuid === repositoryData.repositoryGuid) {
      showMessage('error', t('resources:repositories.cannotDeleteGrandRepository'))
      return
    }

    // Show confirmation modal
    modal.confirm({
      title: t('resources:repositories.deleteCloneConfirmTitle'),
      content: t('resources:repositories.deleteCloneConfirmMessage', { name: repository.name }),
      okText: t('common:delete'),
      okType: 'danger',
      cancelText: t('common:cancel'),
      onOk: async () => {
        try {
          // Find team vault data
          const team = teams?.find(t => t.teamName === machine.teamName)

          // Find the grand repository vault
          let grandRepositoryVault = repositoryData.vaultContent
          if (repositoryData.grandGuid) {
            const grandRepository = teamRepositories.find(r => r.repositoryGuid === repositoryData.grandGuid)
            if (grandRepository && grandRepository.vaultContent) {
              grandRepositoryVault = grandRepository.vaultContent
            }
          }

          // Step 1: Queue the physical deletion via repo_rm
          const params: Record<string, any> = {
            repo: repositoryData.repositoryGuid,
            grand: repositoryData.grandGuid
          }

          const queueVault = await buildQueueVault({
            teamName: machine.teamName,
            machineName: machine.machineName,
            bridgeName: machine.bridgeName,
            functionName: 'rm',
            params,
            priority: 4,
            description: `Delete clone ${repository.name}`,
            addedVia: 'machine-repository-list-delete-clone',
            teamVault: team?.vaultContent || '{}',
            machineVault: machine.vaultContent || '{}',
            repositoryGuid: repositoryData.repositoryGuid,
            repositoryVault: grandRepositoryVault,
            repositoryLoopbackIp: repositoryData.repoLoopbackIp
          })

          const queueResponse = await managedQueueMutation.mutateAsync({
            teamName: machine.teamName,
            machineName: machine.machineName,
            bridgeName: machine.bridgeName,
            queueVault,
            priority: 4
          })

          if (queueResponse?.taskId) {
            showMessage('success', t('resources:repositories.deleteCloneQueued', { name: repository.name }))
            if (onQueueItemCreated) {
              onQueueItemCreated(queueResponse.taskId, machine.machineName)
            }

            // Step 2: Delete the credential from database after queuing
            try {
              await deleteRepositoryMutation.mutateAsync({
                teamName: machine.teamName,
                repositoryName: repository.name,
                repositoryTag: repository.repoTag || 'latest'
              })
              showMessage('success', t('resources:repositories.deleteForkSuccess'))
            } catch (credError) {
              showMessage('warning', t('resources:repositories.deleteCloneCredentialFailed'))
            }
          } else if (queueResponse?.isQueued) {
            showMessage('info', t('resources:repositories.highestPriorityQueued'))
          }

        } catch (error) {
          showMessage('error', t('resources:repositories.deleteCloneFailed'))
        }
      }
    })
  }

  const handlePromoteToGrand = async (repository: Repository) => {
    // Find the repository data
    const repositoryData = teamRepositories.find(r => r.repositoryName === repository.name)

    if (!repositoryData) {
      showMessage('error', t('resources:repositories.repositoryNotFound'))
      return
    }

    // Safety check: only allow promotion of clones (repositories with a parent)
    if (!repositoryData.grandGuid || repositoryData.grandGuid === repositoryData.repositoryGuid) {
      showMessage('error', t('resources:repositories.alreadyOriginalRepository'))
      return
    }

    // Find the current grand repository
    const currentGrand = teamRepositories.find(r => r.repositoryGuid === repositoryData.grandGuid)
    const currentGrandName = currentGrand?.repositoryName || 'original'

    // Find sibling clones (exclude the original repository itself)
    const siblingClones = teamRepositories.filter(r =>
      r.grandGuid === repositoryData.grandGuid &&
      r.repositoryGuid !== repositoryData.repositoryGuid &&
      r.grandGuid !== r.repositoryGuid  // Exclude original repositories
    )

    // Show confirmation modal
    modal.confirm({
      title: t('resources:repositories.promoteToGrandTitle'),
      content: (
        <div>
          <Typography.Paragraph>
            {t('resources:repositories.promoteToGrandMessage', {
              name: repository.name,
              grand: currentGrandName
            })}
          </Typography.Paragraph>
          {siblingClones.length > 0 && (
            <>
              <Typography.Paragraph>
                {t('resources:repositories.promoteWillUpdateSiblings', { count: siblingClones.length })}
              </Typography.Paragraph>
              <ul>
                {siblingClones.map(clone => (
                  <li key={clone.repositoryGuid}>{clone.repositoryName}</li>
                ))}
              </ul>
            </>
          )}
          <Alert
            message={t('resources:repositories.promoteWarning')}
            type="warning"
            showIcon
            style={{ marginTop: 16 }}
          />
        </div>
      ),
      okText: t('resources:repositories.promoteButton'),
      okType: 'primary',
      cancelText: t('common:cancel'),
      onOk: async () => {
        try {
          await promoteRepositoryMutation.mutateAsync({
            teamName: machine.teamName,
            repositoryName: repository.name
          })
          showMessage('success', t('resources:repositories.promoteSuccess', { name: repository.name }))
        } catch (error: unknown) {
          const errorMessage = (error as any)?.response?.data?.message || t('resources:repositories.promoteFailed')
          showMessage('error', errorMessage)
        }
      }
    })
  }

  const handleRenameRepository = async (repository: Repository) => {
    let newName = repository.name

    modal.confirm({
      title: t('resources:repositories.renameTitle'),
      content: (
        <div>
          <Typography.Paragraph>
            {t('resources:repositories.renameMessage', { name: repository.name })}
          </Typography.Paragraph>
          <Input
            defaultValue={repository.name}
            placeholder={t('resources:repositories.newRepositoryName')}
            onChange={(e) => { newName = e.target.value }}
            onPressEnter={(e) => {
              e.preventDefault()
              // Note: Modal closing on Enter needs to be handled differently with App.useApp()
            }}
            autoFocus
          />
        </div>
      ),
      okText: t('common:save'),
      cancelText: t('common:cancel'),
      onOk: async () => {
        // Validate new name
        const trimmedName = newName.trim()

        if (!trimmedName) {
          showMessage('error', t('resources:repositories.emptyNameError'))
          return Promise.reject()
        }

        if (trimmedName === repository.name) {
          showMessage('info', t('resources:repositories.nameUnchanged'))
          return Promise.reject()
        }

        // Check if name already exists
        const existingRepo = teamRepositories.find(r => r.repositoryName === trimmedName)
        if (existingRepo) {
          showMessage('error', t('resources:repositories.nameAlreadyExists', { name: trimmedName }))
          return Promise.reject()
        }

        try {
          await updateRepositoryNameMutation.mutateAsync({
            teamName: machine.teamName,
            currentRepositoryName: repository.name,
            newRepositoryName: trimmedName
          })
          showMessage('success', t('resources:repositories.renameSuccess', { oldName: repository.name, newName: trimmedName }))

          // Refresh repository list
          if (onActionComplete) {
            onActionComplete()
          }
        } catch (error: unknown) {
          const errorMessage = (error as any)?.response?.data?.message || t('resources:repositories.renameFailed')
          showMessage('error', errorMessage)
          return Promise.reject()
        }
      }
    })
  }

  const handleDeleteGrandRepository = async (repository: Repository) => {
    // Find the repository data
    const repositoryData = teamRepositories.find(r => r.repositoryName === repository.name)

    if (!repositoryData) {
      showMessage('error', t('resources:repositories.repositoryNotFound'))
      return
    }

    // Safety check: only allow deletion of grand repositories (no parent)
    if (repositoryData.grandGuid && repositoryData.grandGuid !== repositoryData.repositoryGuid) {
      showMessage('error', t('resources:repositories.notAGrandRepository'))
      return
    }

    // Check for child repositories (clones) before deletion
    const childClones = teamRepositories.filter(r =>
      r.grandGuid === repositoryData.repositoryGuid &&
      r.repositoryGuid !== repositoryData.repositoryGuid
    )

    if (childClones.length > 0) {
      // Show error modal with clone list
      modal.error({
        title: t('resources:repositories.cannotDeleteHasClones'),
        content: (
          <div>
            <Typography.Paragraph>
              {t('resources:repositories.hasActiveClonesMessage', {
                name: repository.name,
                count: childClones.length
              })}
            </Typography.Paragraph>
            <Typography.Paragraph strong>
              {t('resources:repositories.clonesList')}
            </Typography.Paragraph>
            <ul>
              {childClones.map(clone => (
                <li key={clone.repositoryGuid}>{clone.repositoryName}</li>
              ))}
            </ul>
            <Typography.Paragraph>
              {t('resources:repositories.deleteOptionsMessage')}
            </Typography.Paragraph>
          </div>
        ),
        okText: t('common:close')
      })
      return
    }

    // State for confirmation input
    let confirmationInput = ''

    // Show advanced confirmation modal
    modal.confirm({
      title: t('resources:repositories.deleteGrandConfirmTitle'),
      content: (
        <div>
          <Alert
            message={t('resources:repositories.deleteGrandWarning')}
            description={t('resources:repositories.deleteGrandWarningDesc', { name: repository.name })}
            type="warning"
            showIcon
            style={{ marginBottom: 16 }}
          />
          <Typography.Text strong>
            {t('resources:repositories.deleteGrandConfirmPrompt', { name: repository.name })}
          </Typography.Text>
          <input
            type="text"
            placeholder={repository.name}
            style={{
              width: '100%',
              marginTop: 8,
              padding: '8px',
              border: '1px solid #d9d9d9',
              borderRadius: '4px'
            }}
            onChange={(e) => {
              confirmationInput = e.target.value
            }}
          />
        </div>
      ),
      okText: t('common:delete'),
      okType: 'danger',
      cancelText: t('common:cancel'),
      onOk: async () => {
        // Verify confirmation input matches repository name
        if (confirmationInput !== repository.name) {
          showMessage('error', t('resources:repositories.deleteGrandConfirmationMismatch'))
          return Promise.reject()
        }

        try {
          // Find team vault data
          const team = teams?.find(t => t.teamName === machine.teamName)

          // For grand repositories, use its own vault
          const grandRepositoryVault = repositoryData.vaultContent

          // Step 1: Queue the physical deletion via repo_rm
          const params: Record<string, any> = {
            repo: repositoryData.repositoryGuid,
            grand: repositoryData.repositoryGuid // Grand points to itself
          }

          const queueVault = await buildQueueVault({
            teamName: machine.teamName,
            machineName: machine.machineName,
            bridgeName: machine.bridgeName,
            functionName: 'rm',
            params,
            priority: 4,
            description: `Delete repository ${repository.name}`,
            addedVia: 'machine-repository-list-delete-grand',
            teamVault: team?.vaultContent || '{}',
            machineVault: machine.vaultContent || '{}',
            repositoryGuid: repositoryData.repositoryGuid,
            repositoryVault: grandRepositoryVault,
            repositoryLoopbackIp: repositoryData.repoLoopbackIp
          })

          const queueResponse = await managedQueueMutation.mutateAsync({
            teamName: machine.teamName,
            machineName: machine.machineName,
            bridgeName: machine.bridgeName,
            queueVault,
            priority: 4
          })

          if (queueResponse?.taskId) {
            showMessage('success', t('resources:repositories.deleteGrandQueued', { name: repository.name }))
            if (onQueueItemCreated) {
              onQueueItemCreated(queueResponse.taskId, machine.machineName)
            }

            // Step 2: Delete the credential from database after queuing
            try {
              await deleteRepositoryMutation.mutateAsync({
                teamName: machine.teamName,
                repositoryName: repository.name,
                repositoryTag: repository.repoTag || 'latest'
              })
              showMessage('success', t('resources:repositories.deleteGrandSuccess'))
            } catch (credError) {
              showMessage('warning', t('resources:repositories.deleteGrandCredentialFailed'))
            }
          } else if (queueResponse?.isQueued) {
            showMessage('info', t('resources:repositories.highestPriorityQueued'))
          }

        } catch (error) {
          showMessage('error', t('resources:repositories.deleteGrandFailed'))
          return Promise.reject()
        }
      }
    })
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

      const finalParams = { ...functionData.params }
      const repositoryGuid = repositoryData.repositoryGuid
      const repositoryVault = grandRepositoryVault
      const destinationMachineVault = undefined
      const destinationStorageVault = undefined
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

      // Handle deploy function (multiple machines)
      if (functionData.function.name === 'deploy' && functionData.params.machines) {
        const machinesArray = Array.isArray(functionData.params.machines)
          ? functionData.params.machines
          : [functionData.params.machines]

        // Validate destination filename before processing
        const destFilename = functionData.params.dest?.trim()

        if (!destFilename) {
          showMessage('error', 'Destination filename is required')
          setFunctionModalOpen(false)
          setSelectedRepository(null)
          return
        }

        const createdTaskIds: string[] = []

        // Generate deploy tag with timestamp (similar to fork)
        const timestamp = new Date().toISOString().slice(0, 19).replace('T', '-').replace(/:/g, '-')
        const deployTag = `deploy-${timestamp}`  // e.g., deploy-2025-01-09-14-30-00

        // Create repository credential ONCE (not per machine - it's team-wide)
        let newRepo
        try {
          await createRepositoryMutation.mutateAsync({
            teamName: machine.teamName,
            repositoryName: destFilename,
            repositoryTag: deployTag,
            parentRepoName: selectedRepository.name
          })

          // Refresh repositories list
          const { data: updatedRepos } = await refetchRepositories()
          newRepo = updatedRepos?.find(r => r.repositoryName === destFilename && r.repoTag === deployTag)

          if (!newRepo || !newRepo.repositoryGuid) {
            throw new Error('Could not find newly created repository')
          }
        } catch (createError) {
          showMessage('error', t('resources:repositories.failedToCreateRepository'))
          setFunctionModalOpen(false)
          setSelectedRepository(null)
          return
        }

        // Now deploy to each target machine using the same repository credential
        for (const targetMachine of machinesArray) {
          try {
            // Get destination machine vault
            const destinationMachine = machinesData?.find(m => m.machineName === targetMachine)
            let targetMachineVault = undefined
            if (destinationMachine && destinationMachine.vaultContent) {
              targetMachineVault = destinationMachine.vaultContent
            }

            // Build queue vault for this specific destination
            const deployParams = {
              ...functionData.params,
              to: targetMachine,
              dest: newRepo.repositoryGuid,
              repo: repositoryData.repositoryGuid,
              grand: repositoryData.grandGuid || repositoryData.repositoryGuid || ''
            }

            const queueVault = await buildQueueVault({
              teamName: machine.teamName,
              machineName: machine.machineName,
              bridgeName: machine.bridgeName,
              functionName: 'deploy',
              params: deployParams,
              priority: functionData.priority,
              description: `${functionData.description} → ${targetMachine}`,
              addedVia: 'machine-repository-list',
              teamVault: team?.vaultContent || '{}',
              machineVault: machine.vaultContent || '{}',
              repositoryGuid,
              repositoryVault,
              repositoryLoopbackIp: newRepo.repoLoopbackIp,
              repositoryNetworkMode: newRepo.repoNetworkMode,
              repositoryTag: newRepo.repoTag,
              destinationMachineVault: targetMachineVault
            })

            const response = await managedQueueMutation.mutateAsync({
              teamName: machine.teamName,
              machineName: machine.machineName,
              bridgeName: machine.bridgeName,
              queueVault,
              priority: functionData.priority
            })

            if (response?.taskId) {
              createdTaskIds.push(response.taskId)
            }
          } catch (error) {
            showMessage('error', t('resources:repositories.failedToDeployTo', { machine: targetMachine }))
          }
        }

        setFunctionModalOpen(false)
        setSelectedRepository(null)

        if (createdTaskIds.length > 0) {
          // Show summary message
          if (createdTaskIds.length === machinesArray.length) {
            // All succeeded
            showMessage('success', t('resources:repositories.deploymentQueued', { count: createdTaskIds.length }))
          } else {
            // Some succeeded, some failed
            showMessage('warning', t('resources:repositories.deploymentPartialSuccess', {
              success: createdTaskIds.length,
              total: machinesArray.length
            }))
          }
          if (onQueueItemCreated && createdTaskIds[0]) {
            onQueueItemCreated(createdTaskIds[0], machine.machineName)
          }
        } else {
          // All failed
          showMessage('error', t('resources:repositories.allDeploymentsFailed'))
        }
        return
      }

      // Handle backup function (multiple storages)
      if (functionData.function.name === 'backup' && functionData.params.storages) {
        const storagesArray = Array.isArray(functionData.params.storages)
          ? functionData.params.storages
          : [functionData.params.storages]

        const createdTaskIds: string[] = []

        for (const targetStorage of storagesArray) {
          try {
            // Get destination storage vault
            const destinationStorage = storageData?.find(s => s.storageName === targetStorage)
            let targetStorageVault = undefined
            if (destinationStorage && destinationStorage.vaultContent) {
              targetStorageVault = destinationStorage.vaultContent
            }

            // Build queue vault for this specific storage
            const backupParams = {
              ...functionData.params,
              to: targetStorage,
              repo: repositoryData.repositoryGuid,
              grand: repositoryData.grandGuid || repositoryData.repositoryGuid || ''
            }

            const queueVault = await buildQueueVault({
              teamName: machine.teamName,
              machineName: machine.machineName,
              bridgeName: machine.bridgeName,
              functionName: 'backup',
              params: backupParams,
              priority: functionData.priority,
              description: `${functionData.description} → ${targetStorage}`,
              addedVia: 'machine-repository-list',
              teamVault: team?.vaultContent || '{}',
              machineVault: machine.vaultContent || '{}',
              repositoryGuid,
              repositoryVault,
              repositoryLoopbackIp: repositoryData.repoLoopbackIp,
              repositoryNetworkMode: repositoryData.repoNetworkMode,
              repositoryTag: repositoryData.repoTag,
              destinationStorageVault: targetStorageVault
            })

            const response = await managedQueueMutation.mutateAsync({
              teamName: machine.teamName,
              machineName: machine.machineName,
              bridgeName: machine.bridgeName,
              queueVault,
              priority: functionData.priority
            })

            if (response?.taskId) {
              createdTaskIds.push(response.taskId)
            }
          } catch (error) {
            showMessage('error', t('resources:repositories.failedToBackupTo', { storage: targetStorage }))
          }
        }

        setFunctionModalOpen(false)
        setSelectedRepository(null)

        if (createdTaskIds.length > 0) {
          // Show summary message
          if (createdTaskIds.length === storagesArray.length) {
            // All succeeded
            showMessage('success', t('resources:repositories.backupQueued', { count: createdTaskIds.length }))
          } else {
            // Some succeeded, some failed
            showMessage('warning', t('resources:repositories.backupPartialSuccess', {
              success: createdTaskIds.length,
              total: storagesArray.length
            }))
          }
          if (onQueueItemCreated && createdTaskIds[0]) {
            onQueueItemCreated(createdTaskIds[0], machine.machineName)
          }
        } else {
          // All failed
          showMessage('error', t('resources:repositories.allBackupsFailed'))
        }
        return
      }

      // Handle pull function
      if (functionData.function.name === 'pull') {
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
        repositoryLoopbackIp: repositoryData.repoLoopbackIp,
        repositoryNetworkMode: repositoryData.repoNetworkMode,
        repositoryTag: repositoryData.repoTag,
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
        if (onQueueItemCreated) {
          onQueueItemCreated(response.taskId, machine.machineName)
        }
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

    

  // System container columns
  const systemContainerColumns: ColumnsType<Container> = [
    {
      title: t('resources:containers.status'),
      dataIndex: 'state',
      key: 'status',
      width: 80,
      align: 'center',
      render: (_: unknown, record: Container) => {
        let icon: React.ReactNode
        let color: string
        let tooltipText: string

        if (record.state === 'running') {
          icon = <PlayCircleOutlined />
          color = '#52c41a' // green
          tooltipText = t('resources:containers.containerStatusRunning')
        } else if (record.state === 'paused') {
          icon = <PauseCircleOutlined />
          color = '#faad14' // orange/yellow
          tooltipText = t('resources:containers.containerStatusPaused')
        } else if (record.state === 'restarting') {
          icon = <ReloadOutlined />
          color = '#1890ff' // blue
          tooltipText = t('resources:containers.containerStatusRestarting')
        } else {
          // Stopped/exited or other states
          icon = <StopOutlined />
          color = '#d9d9d9' // gray
          tooltipText = t('resources:containers.containerStatusStopped')
        }

        return (
          <Tooltip title={tooltipText}>
            <span style={{ fontSize: 18, color }}>
              {icon}
            </span>
          </Tooltip>
        )
      },
    },
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
      render: (state: string, record: Container) => (
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
      render: (portMappings: PortMapping[], record: Container) => {
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

  // Transform GroupedRepository[] into flat table data with hierarchy markers
  const getTableDataSource = (): RepositoryTableRow[] => {
    const tableData: RepositoryTableRow[] = []

    groupedRepositories.forEach((group) => {
      // Only show group header if there are multiple tags (grand + forks)
      const hasMultipleTags = group.tags.length > 1

      if (hasMultipleTags) {
        // Add group header row
        tableData.push({
          ...(group.grandTag || group.tags[0]),  // Use grand or first tag as base
          _isGroupHeader: true,
          _groupData: group,
          _indentLevel: 0,
          key: `group-${group.name}`
        } as RepositoryTableRow)

        // Add tag rows if expanded
        if (group.isExpanded) {
          // Grand tag first
          if (group.grandTag) {
            tableData.push({
              ...group.grandTag,
              _isTagRow: true,
              _indentLevel: 1,
              _isLastInGroup: group.forkTags.length === 0,
              key: `tag-${group.name}-${group.grandTag.repoTag || 'latest'}`
            } as RepositoryTableRow)
          }

          // Then fork tags
          group.forkTags.forEach((fork, forkIndex) => {
            tableData.push({
              ...fork,
              _isTagRow: true,
              _indentLevel: 1,
              _isLastInGroup: forkIndex === group.forkTags.length - 1,
              key: `tag-${fork.name}-${fork.repoTag || 'latest'}`
            } as RepositoryTableRow)
          })
        }
      } else {
        // Single tag - show directly without grouping
        const singleTag = group.tags[0]
        tableData.push({
          ...singleTag,
          key: `single-${singleTag.name}-${singleTag.repoTag || 'latest'}`
        } as RepositoryTableRow)
      }
    })

    return tableData
  }

  const columns: ColumnsType<RepositoryTableRow> = [
    {
      title: t('resources:repositories.status'),
      dataIndex: 'status',
      key: 'status',
      width: 80,
      align: 'center',
      render: (_: any, record: RepositoryTableRow) => {
        // Don't show status for group headers
        if (record._isGroupHeader) {
          return null
        }

        // Determine status based on mounted and docker_running
        let icon: React.ReactNode
        let color: string
        let tooltipText: string

        if (record.mounted && record.docker_running) {
          // Mounted & Running - Optimal
          icon = <CheckCircleOutlined />
          color = '#52c41a' // green
          tooltipText = t('resources:repositories.statusMountedRunning')
        } else if (record.mounted && !record.docker_running) {
          // Mounted but not running - Partial
          icon = <ClockCircleOutlined />
          color = '#faad14' // orange/yellow
          tooltipText = t('resources:repositories.statusMountedNotRunning')
        } else {
          // Unmounted - Offline
          icon = <DisconnectOutlined />
          color = '#d9d9d9' // gray
          tooltipText = t('resources:repositories.statusUnmounted')
        }

        return (
          <Tooltip title={tooltipText}>
            <span style={{ fontSize: 18, color }}>
              {icon}
            </span>
          </Tooltip>
        )
      },
    },
    {
      title: t('resources:repositories.repositoryName'),
      dataIndex: 'name',
      key: 'name',
      ellipsis: true,
      render: (_name: string, record: RepositoryTableRow) => {
        const isGroupHeader = record._isGroupHeader
        const groupData = record._groupData
        const isTagRow = record._isTagRow
        const indentLevel = record._indentLevel || 0

        if (isGroupHeader && groupData) {
          // Render group header (repository name with expand/collapse)
          return (
            <Space style={{ paddingLeft: `${indentLevel * 20}px` }}>
              <span
                onClick={(e) => {
                  e.stopPropagation()
                  toggleRepositoryGroup(groupData.name)
                }}
                style={{ cursor: 'pointer', userSelect: 'none', display: 'flex', alignItems: 'center' }}
              >
                {groupData.isExpanded ? <CaretDownOutlined /> : <CaretRightOutlined />}
              </span>
              <FolderOutlined />
              <strong>{groupData.name}</strong>
              <Text type="secondary">({groupData.tags.length} tag{groupData.tags.length > 1 ? 's' : ''})</Text>
            </Space>
          )
        } else if (isTagRow) {
          // Render tag row (indented, with tree connector)
          const tagData = teamRepositories.find(r =>
            r.repositoryName === record.name &&
            (r.repoTag || 'latest') === (record.repoTag || 'latest')
          )
          const isGrand = tagData && (!tagData.parentGuid || tagData.parentGuid === tagData.repositoryGuid)
          const treeConnector = record._isLastInGroup ? '└─' : '├─'

          return (
            <Space style={{ paddingLeft: `${indentLevel * 20}px` }}>
              <span style={{ color: '#999', marginRight: 4 }}>
                {treeConnector}
              </span>
              {isGrand ? <StarOutlined style={{ color: '#faad14' }} /> : <CopyOutlined />}
              <Text>{record.repoTag || 'latest'}</Text>
              {isGrand && <Tag color="blue">Grand</Tag>}
            </Space>
          )
        } else {
          // Regular single repository row (no grouping)
          // Look up repository data to determine if it's a clone or original
          const repositoryData = teamRepositories.find(r =>
            r.repositoryName === record.name &&
            (r.repoTag || 'latest') === (record.repoTag || 'latest')
          )
          const isOriginal = repositoryData && repositoryData.grandGuid && repositoryData.grandGuid === repositoryData.repositoryGuid

          return (
            <Space>
              {isOriginal ? <StarOutlined /> : <CopyOutlined />}
              <strong>{getRepositoryDisplayName(record)}</strong>
            </Space>
          )
        }
      },
    },
    {
      title: t('common:table.actions'),
      key: 'actions',
      width: 160,
      fixed: 'right',
      render: (_: any, record: RepositoryTableRow) => {
        const isGroupHeader = record._isGroupHeader
        const groupData = record._groupData

        // Group header actions (apply to grand repository if exists)
        if (isGroupHeader && groupData) {
          const target = groupData.grandTag
          if (!target) return null

          // Actions for group header (enhanced with navigation and quick actions)
          const menuItems = []

          // View Containers - navigate to grand tag containers
          menuItems.push({
            key: 'view-containers',
            label: t('machines:viewContainers'),
            icon: <RightOutlined style={componentStyles.icon.small} />,
            onClick: () => navigate(`/machines/${machine.machineName}/repositories/${groupData.name}/containers`, {
              state: { machine, repository: target }
            })
          })

          // Expand/Collapse Tags
          menuItems.push({
            key: 'expand-collapse',
            label: groupData.isExpanded ? 'Collapse Tags' : 'Expand Tags',
            icon: groupData.isExpanded ? <CaretRightOutlined style={componentStyles.icon.small} /> : <CaretDownOutlined style={componentStyles.icon.small} />,
            onClick: () => toggleRepositoryGroup(groupData.name)
          })

          // Divider before quick actions
          menuItems.push({
            type: 'divider' as const
          })

          // Quick actions for grand tag
          menuItems.push({
            key: 'fork-grand',
            label: t('functions:functions.fork.name'),
            icon: <CopyOutlined style={componentStyles.icon.small} />,
            onClick: () => handleForkRepository(target)
          })

          menuItems.push({
            key: 'deploy-grand',
            label: t('functions:functions.deploy.name'),
            icon: <CloudUploadOutlined style={componentStyles.icon.small} />,
            onClick: () => handleRunFunction(target, 'deploy')
          })

          menuItems.push({
            key: 'backup-grand',
            label: t('functions:functions.backup.name'),
            icon: <SaveOutlined style={componentStyles.icon.small} />,
            onClick: () => handleRunFunction(target, 'backup')
          })

          return (
            <Space size="small">
              {/* Eye button - opens detail panel for grand tag */}
              <Tooltip title={t('common:viewDetails')}>
                <Button
                  type="default"
                  size="small"
                  icon={<EyeOutlined />}
                  onClick={(e) => {
                    e.stopPropagation()
                    if (target) {
                      onRepositoryClick?.(target)
                    }
                  }}
                  data-testid={`machine-repo-view-details-group-${groupData.name}`}
                  aria-label={t('common:viewDetails')}
                />
              </Tooltip>

              <Dropdown
                menu={{ items: menuItems }}
                trigger={['click']}
              >
                <Tooltip title={t('machines:remote')}>
                  <Button
                    type="primary"
                    size="small"
                    icon={<FunctionOutlined />}
                    loading={managedQueueMutation.isPending}
                    data-testid={`machine-repo-list-group-actions-${groupData.name}`}
                    aria-label={t('machines:remote')}
                  />
                </Tooltip>
              </Dropdown>
            </Space>
          )
        }

        // Tag row or single repository - show full actions
        // Look up repository data from database to get grandGuid
        const repositoryData = teamRepositories.find(r =>
          r.repositoryName === record.name &&
          (r.repoTag || 'latest') === (record.repoTag || 'latest')
        )

        // Build smart menu items based on repository state
        const menuItems = []

        // PRIMARY ACTIONS AT TOP LEVEL

        // Up - always available
        menuItems.push({
          key: 'up',
          label: t('functions:functions.up.name'),
          icon: <PlayCircleOutlined style={componentStyles.icon.small} />,
          onClick: () => handleQuickAction(record, 'up', 4, 'mount')
        })

        // Down - only when mounted
        if (record.mounted) {
          menuItems.push({
            key: 'down',
            label: t('functions:functions.down.name'),
            icon: <PauseCircleOutlined style={componentStyles.icon.small} />,
            onClick: () => handleQuickAction(record, 'down', 4, 'unmount')
          })
        }

        // Validate - only when unmounted (tests complete lifecycle from clean state)
        if (!record.mounted) {
          menuItems.push({
            key: 'validate',
            label: t('functions:functions.validate.name'),
            icon: <CheckCircleOutlined style={componentStyles.icon.small} />,
            onClick: () => handleRunFunction(record, 'validate')
          })
        }

        // Fork - always available (use 'Fork' instead of 'Clone' for consistency)
        menuItems.push({
          key: 'fork',
          label: t('functions:functions.fork.name'),
          icon: <CopyOutlined style={componentStyles.icon.small} />,
          onClick: () => handleForkRepository(record)
        })

        // Deploy - always available
        menuItems.push({
          key: 'deploy',
          label: t('functions:functions.deploy.name'),
          icon: <CloudUploadOutlined style={componentStyles.icon.small} />,
          onClick: () => handleRunFunction(record, 'deploy')
        })

        // Backup - always available
        menuItems.push({
          key: 'backup',
          label: t('functions:functions.backup.name'),
          icon: <SaveOutlined style={componentStyles.icon.small} />,
          onClick: () => handleRunFunction(record, 'backup')
        })

        // Apply Template - always available
        menuItems.push({
          key: 'apply_template',
          label: t('functions:functions.apply_template.name'),
          icon: <AppstoreOutlined style={componentStyles.icon.small} />,
          onClick: () => handleRunFunction(record, 'apply_template')
        })

        // ADVANCED SUBMENU FOR STORAGE OPERATIONS
        const advancedSubmenuItems = []

        // Mount/Unmount
        if (!record.mounted) {
          advancedSubmenuItems.push({
            key: 'mount',
            label: t('resources:repositories.mount'),
            icon: <DatabaseOutlined style={componentStyles.icon.small} />,
            onClick: () => handleQuickAction(record, 'mount', 4)
          })
        } else {
          advancedSubmenuItems.push({
            key: 'unmount',
            label: t('resources:repositories.unmount'),
            icon: <DisconnectOutlined style={componentStyles.icon.small} />,
            onClick: () => handleQuickAction(record, 'unmount', 4)
          })
        }

        // Resize - only when NOT mounted (offline operation)
        if (!record.mounted) {
          advancedSubmenuItems.push({
            key: 'resize',
            label: t('functions:functions.resize.name'),
            icon: <ShrinkOutlined style={componentStyles.icon.small} />,
            onClick: () => handleRunFunction(record, 'resize')
          })
        }

        // Expand - only when mounted (online expansion)
        if (record.mounted) {
          advancedSubmenuItems.push({
            key: 'expand',
            label: t('functions:functions.expand.name'),
            icon: <ExpandOutlined style={componentStyles.icon.small} />,
            onClick: () => handleRunFunction(record, 'expand')
          })
        }

        // Add divider and experimental to advanced submenu
        if (advancedSubmenuItems.length > 0) {
          advancedSubmenuItems.push({
            type: 'divider' as const
          })
        }

        advancedSubmenuItems.push({
          key: 'experimental',
          label: t('machines:experimental'),
          icon: <FunctionOutlined style={componentStyles.icon.small} />,
          onClick: () => handleRunFunction(record)
        })

        // Add Advanced submenu if there are items
        if (advancedSubmenuItems.length > 0) {
          menuItems.push({
            key: 'advanced',
            label: t('resources:repositories.advanced'),
            icon: <ControlOutlined style={componentStyles.icon.small} />,
            children: advancedSubmenuItems
          })
        }

        // Promote to Original and Delete - only for forks (repositories with a parent)
        if (repositoryData && repositoryData.grandGuid && repositoryData.grandGuid !== repositoryData.repositoryGuid) {
          menuItems.push({
            key: 'promote-to-grand',
            label: t('resources:repositories.promoteToGrand'),
            icon: <RiseOutlined style={componentStyles.icon.small} />,
            onClick: () => handlePromoteToGrand(record)
          })
          menuItems.push({
            key: 'delete-fork',
            label: t('resources:repositories.deleteFork'),
            icon: <DeleteOutlined style={componentStyles.icon.small} />,
            onClick: () => handleDeleteFork(record),
            danger: true
          })
        }

        // Always add divider before management actions
        if (menuItems.length > 0) {
          menuItems.push({
            type: 'divider' as const
          })
        }

        // Rename - always available
        menuItems.push({
          key: 'rename',
          label: t('resources:repositories.rename'),
          icon: <EditOutlined style={componentStyles.icon.small} />,
          onClick: () => handleRenameRepository(record)
        })

        // Delete Grand Repository - only for grand repositories (no parent)
        if (repositoryData && repositoryData.grandGuid && repositoryData.grandGuid === repositoryData.repositoryGuid) {
          menuItems.push({
            key: 'delete-grand',
            label: t('resources:repositories.deleteGrand'),
            icon: <DeleteOutlined style={componentStyles.icon.small} />,
            onClick: () => handleDeleteGrandRepository(record),
            danger: true
          })
        }

        return (
          <Space size="small">
            {/* Eye button - opens detail panel */}
            <Tooltip title={t('common:viewDetails')}>
              <Button
                type="default"
                size="small"
                icon={<EyeOutlined />}
                onClick={(e) => {
                  e.stopPropagation()
                  onRepositoryClick?.(record)
                }}
                data-testid={`machine-repo-view-details-${record.name}-${record.repoTag || 'latest'}`}
                aria-label={t('common:viewDetails')}
              />
            </Tooltip>

            <Dropdown
              menu={{ items: menuItems }}
              trigger={['click']}
            >
              <Tooltip title={t('machines:remote')}>
                <Button
                  type="primary"
                  size="small"
                  icon={<FunctionOutlined />}
                  loading={managedQueueMutation.isPending}
                  data-testid={`machine-repo-list-repo-actions-${record.name}`}
                  aria-label={t('machines:remote')}
                />
              </Tooltip>
            </Dropdown>
            {record.mounted && (
              <LocalActionsMenu
                machine={machine.machineName}
                repository={record.name}
                teamName={machine.teamName}
                userEmail={userEmail}
                pluginContainers={containersData[record.name]?.containers || []}
              />
            )}
            {record.isUnmapped && onCreateRepository && (
              <Tooltip title={t('resources:repositories.addCredential')}>
                <Button
                  type="default"
                  size="small"
                  icon={<KeyOutlined />}
                  onClick={() => onCreateRepository(machine, record.originalGuid || record.name)}
                  style={componentStyles.touchTarget}
                  data-testid={`machine-repo-list-add-credential-${record.name}`}
                  aria-label={t('resources:repositories.addCredential')}
                />
              </Tooltip>
            )}
          </Space>
        )
      },
    },
  ]

  if (loading) {
    return (
      <div style={{ padding: '20px', textAlign: 'center' }} data-testid="machine-repo-list-loading">
        <Spin />
        <div style={{ marginTop: 16, color: 'var(--ant-color-text-secondary)' }}>
          {t('resources:repositories.fetchingRepositories')}
        </div>
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
            <Tooltip title={t('common:actions.retry')}>
              <Button 
                size="small" 
                onClick={handleRefresh} 
                data-testid="machine-repo-list-retry"
                aria-label={t('common:actions.retry')}
              />
            </Tooltip>
          }
        />
      </div>
    )
  }

  return (
    <S.Container data-testid="machine-repo-list">
      {/* Loading Overlay */}
      {isLoading && (
        <S.LoadingOverlay>
          <Space direction="vertical" align="center">
            <Spin size="large" />
            <Text type="secondary">{t('common:general.refreshing')}</Text>
          </Space>
        </S.LoadingOverlay>
      )}
      
      {/* Machine Name Title when in grouped view */}
      {hideSystemInfo && (
        <S.MachineHeader data-testid="machine-repo-list-machine-header">
          <Space direction="vertical" size={4}>
            <Space>
              <S.MachineIcon as={DesktopOutlined} />
              <S.MachineTitle as={Typography.Title} level={4} data-testid="machine-repo-list-machine-name">
                {machine.machineName}
              </S.MachineTitle>
            </Space>
            <Space wrap size={8}>
              <Tag color="#8FBC8F" data-testid="machine-repo-list-team-tag">{machine.teamName}</Tag>
              <Tag color="green" data-testid="machine-repo-list-bridge-tag">{machine.bridgeName}</Tag>
              {machine.regionName && <Tag color="purple" data-testid="machine-repo-list-region-tag">{machine.regionName}</Tag>}
              <Tag color="blue" data-testid="machine-repo-list-queue-tag">{machine.queueCount} {t('machines:queueItems')}</Tag>
            </Space>
          </Space>
        </S.MachineHeader>
      )}

      {/* Warning for missing SSH keys in team vault */}
      {(() => {
        const team = teams?.find(t => t.teamName === machine.teamName)
        if (!team?.vaultContent) return null

        try {
          const teamVault = JSON.parse(team.vaultContent)
          const missingSSHKeys = !teamVault.SSH_PRIVATE_KEY || !teamVault.SSH_PUBLIC_KEY

          return missingSSHKeys ? (
            <Alert
              type="warning"
              showIcon
              closable
              message={t('common:vaultEditor.missingSshKeysWarning')}
              description={t('common:vaultEditor.missingSshKeysDescription')}
              style={{ marginBottom: 16 }}
            />
          ) : null
        } catch {
          return null
        }
      })()}

      {/* Repository Table */}
      <S.StyledTable
        columns={columns}
        dataSource={getTableDataSource()}
        rowKey={(record: RepositoryTableRow) => record.key || `${record.name}-${record.repoTag || 'latest'}`}
        size="small"
        pagination={false}
        scroll={{ x: 'max-content' }}
        style={tableStyles.tableContainer}
        data-testid="machine-repo-list-table"
        rowClassName={(record: RepositoryTableRow) => {
          // Group headers have special styling
          if (record._isGroupHeader) {
            return 'repository-group-header'
          }

          // Apply subtle background to fork/clone rows
          if (record._isTagRow) {
            const repositoryData = teamRepositories.find(r =>
              r.repositoryName === record.name &&
              (r.repoTag || 'latest') === (record.repoTag || 'latest')
            )
            const isFork = repositoryData && repositoryData.grandGuid && repositoryData.grandGuid !== repositoryData.repositoryGuid
            return isFork ? 'repository-fork-row' : 'repository-grand-row'
          }

          // Regular single repository rows
          const repositoryData = teamRepositories.find(r =>
            r.repositoryName === record.name &&
            (r.repoTag || 'latest') === (record.repoTag || 'latest')
          )
          const isClone = repositoryData && repositoryData.grandGuid && repositoryData.grandGuid !== repositoryData.repositoryGuid
          return isClone ? 'repository-clone-row' : ''
        }}
        locale={{
          emptyText: t('resources:repositories.noRepositories')
        }}
        onRow={(record: RepositoryTableRow) => {
          // Group headers don't have expandable content
          if (record._isGroupHeader) {
            return {
              onClick: (e: React.MouseEvent<HTMLElement>) => {
                const target = e.target as HTMLElement
                // Don't trigger if clicking on buttons or dropdowns
                if (target.closest('button') || target.closest('.ant-dropdown-trigger')) {
                  return
                }
                // Group expansion is handled by the expand icon in the name column
              },
              style: {
                cursor: 'default',
                backgroundColor: 'rgba(0, 0, 0, 0.02)',
                fontWeight: 500
              }
            }
          }

          return {
            onClick: (e: React.MouseEvent<HTMLElement>) => {
              const target = e.target as HTMLElement
              // Don't trigger if clicking on buttons or dropdowns
              if (target.closest('button') || target.closest('.ant-dropdown-trigger')) {
                return
              }

              // Navigate to containers page
              navigate(`/machines/${machine.machineName}/repositories/${record.name}/containers`, {
                state: { machine, repository: record }
              })
            },
            style: {
              cursor: 'pointer',
              backgroundColor: highlightedRepository?.name === record.name ? 'rgba(24, 144, 255, 0.05)' : undefined,
              transition: 'background-color 0.3s ease'
            },
            onMouseEnter: (e: React.MouseEvent<HTMLElement>) => {
              e.currentTarget.style.backgroundColor = highlightedRepository?.name === record.name ? 'rgba(24, 144, 255, 0.08)' : 'rgba(0, 0, 0, 0.02)'
            },
            onMouseLeave: (e: React.MouseEvent<HTMLElement>) => {
              e.currentTarget.style.backgroundColor = highlightedRepository?.name === record.name ? 'rgba(24, 144, 255, 0.05)' : ''
            }
          }
        }}
      />
      
      {/* System Containers Section */}
      {systemContainers.length > 0 && !hideSystemInfo && (
        <S.SystemContainersWrapper data-testid="machine-repo-list-system-containers">
          <S.SystemContainersTitle as={Typography.Title} level={5} data-testid="machine-repo-list-system-containers-title">
            {t('resources:repositories.systemContainers')}
          </S.SystemContainersTitle>
          <S.StyledTable
            columns={systemContainerColumns}
            dataSource={systemContainers}
            rowKey="id"
            size="small"
            pagination={false}
            scroll={{ x: 'max-content' }}
            style={tableStyles.tableContainer}
            data-testid="machine-repo-list-system-containers-table"
          />
        </S.SystemContainersWrapper>
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
                if (currentRepoData?.parentGuid) {
                  const parentRepo = teamRepositories.find(r => r.repositoryGuid === currentRepoData.parentGuid);
                  if (parentRepo) {
                    return (
                      <Space>
                        <Text type="secondary">Parent Repository:</Text>
                        <Tag color="blue">{parentRepo.repositoryName}</Tag>
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
            parentRepository: (() => {
              const currentRepoData = teamRepositories.find(r => r.repositoryName === selectedRepository.name);
              if (currentRepoData?.parentGuid) {
                const parentRepo = teamRepositories.find(r => r.repositoryGuid === currentRepoData.parentGuid);
                return parentRepo?.repositoryName || null;
              }
              return null;
            })()
          } : undefined
        }
      />

      {/* Modal contextHolder - required for Modal.useModal() to work */}
      {contextHolder}
    </S.Container>
  )
}