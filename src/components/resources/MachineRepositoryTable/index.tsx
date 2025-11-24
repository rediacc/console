import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Alert, Tag, Space, Typography, Button, Dropdown, Tooltip, Modal, Input } from 'antd'
import { useTableStyles, useComponentStyles } from '@/hooks/useComponentStyles'
import { CheckCircleOutlined, FunctionOutlined, PlayCircleOutlined, StopOutlined, ExpandOutlined, CloudUploadOutlined, SaveOutlined, PauseCircleOutlined, ReloadOutlined, DeleteOutlined, DesktopOutlined, ClockCircleOutlined, DatabaseOutlined, DisconnectOutlined, KeyOutlined, AppstoreOutlined, CloudServerOutlined, RightOutlined, CopyOutlined, RiseOutlined, StarOutlined, EditOutlined, ShrinkOutlined, ControlOutlined, CaretDownOutlined, CaretRightOutlined, FolderOutlined, EyeOutlined } from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { useDialogState } from '@/hooks/useDialogState'
import * as S from './styles'
import { type QueueFunction } from '@/api/queries/queue'
import { useQueueAction } from '@/hooks/useQueueAction'
import { Machine } from '@/types'
import { useTeams } from '@/api/queries/teams'
import { useRepositories, useCreateRepository, useDeleteRepository, usePromoteRepositoryToGrand, useUpdateRepositoryName } from '@/api/queries/repositories'
import { useMachines } from '@/api/queries/machines'
import { useStorage } from '@/api/queries/storage'
import type { ColumnsType } from 'antd/es/table'
import type { MenuInfo } from 'rc-menu/lib/interface'
import FunctionSelectionModal from '@/components/common/FunctionSelectionModal'
import { LocalActionsMenu } from '../internal/LocalActionsMenu'
import { showMessage } from '@/utils/messages'
import { useAppSelector } from '@/store/store'
import { createSorter, createCustomSorter, createArrayLengthSorter } from '@/core'
import { parseVaultStatus } from '@/core/services/machine'
import LoadingWrapper from '@/components/common/LoadingWrapper'
import { createActionColumn, createStatusColumn, createTruncatedColumn } from '@/components/common/columns'
import { isValidGuid } from '@/core/utils/validation'
import {
  canBackupToStorage,
  isFork as coreIsFork,
  isCredential as coreIsCredential,
  prepareForkDeletion,
  prepareGrandDeletion,
  preparePromotion,
  getGrandVaultForOperation
} from '@/core'

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
        tr.repoTag === r.repoTag
      )
      // Grand repo has no parentGuid or parentGuid equals repositoryGuid
      return tagData && (!tagData.parentGuid || tagData.parentGuid === tagData.repositoryGuid)
    }) || null

    // All other tags are forks - sort them by tag name (chronologically since tags include timestamps)
    const forkTags = tags.filter(r => r !== grandTag).sort((a, b) => (a.repoTag || '').localeCompare(b.repoTag || ''))

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

interface MachineRepositoryTableProps {
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


export const MachineRepositoryTable: React.FC<MachineRepositoryTableProps> = ({ machine, onActionComplete, hideSystemInfo = false, onCreateRepository, onRepositoryClick, highlightedRepository, onContainerClick: _onContainerClick, highlightedContainer: _highlightedContainer, isLoading, onRefreshMachines: _onRefreshMachines, refreshKey, onQueueItemCreated }) => {
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
  const functionModal = useDialogState<void>()
  const [selectedFunction, setSelectedFunction] = useState<string | null>(null)
  const [_servicesData, setServicesData] = useState<Record<string, any>>({})
  const [containersData, setContainersData] = useState<Record<string, any>>({})
  const [createdRepositoryName, setCreatedRepositoryName] = useState<string | null>(null)
  const [createdRepositoryTag, setCreatedRepositoryTag] = useState<string | null>(null)
  const [groupedRepositories, setGroupedRepositories] = useState<GroupedRepository[]>([])

  // Queue action hook for function execution
  const { executeAction, isExecuting } = useQueueAction()
  const { data: teams } = useTeams()
  const { data: teamRepositories = [], isLoading: repositoriesLoading, refetch: refetchRepositories } = useRepositories(machine.teamName)
  const { data: teamMachines = [] } = useMachines(machine.teamName)
  const { data: teamStorages = [] } = useStorage(machine.teamName)
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
        // Parse vaultStatus using core utility
        const parsed = parseVaultStatus(machine.vaultStatus)

        if (parsed.error) {
          // Invalid vaultStatus data format (e.g., jq errors)
          setError('Invalid repository data')
          setLoading(false)
        } else if (parsed.status === 'completed' && parsed.rawResult) {
          // Use existing vaultStatus data
          try {
            const result = JSON.parse(parsed.rawResult)
            if (result) {
              // Process system information if available
              if (result.system) {
                setSystemInfo(result.system)
              }
              
              if (result.repositories && Array.isArray(result.repositories)) {
                // Map repository GUIDs back to names if needed
                const mappedRepositories = result.repositories.map((repo: Repository) => {
                  // Check if the name looks like a GUID
                  const isGuid = isValidGuid(repo.name);

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
                  const aData = teamRepositories.find(r => r.repositoryName === a.name && r.repoTag === a.repoTag)
                  const bData = teamRepositories.find(r => r.repositoryName === b.name && r.repoTag === b.repoTag)

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
    functionModal.open()
  }

  const handleQuickAction = async (repository: Repository, functionName: string, priority: number = 4, option?: string) => {
    // Find the repository vault data - must match both name AND tag to distinguish forks from grand repos
    const repositoryData = teamRepositories.find(r =>
      r.repositoryName === repository.name &&
      r.repoTag === repository.repoTag
    )

    if (!repositoryData || !repositoryData.vaultContent) {
      showMessage('error', t('resources:repositories.noCredentialsFound', { name: repository.name }))
      return
    }

    // Get grand repository vault using core orchestration
    const grandRepositoryVault = getGrandVaultForOperation(
      repositoryData.repositoryGuid,
      repositoryData.grandGuid,
      teamRepositories
    ) || repositoryData.vaultContent

    // Build params with option if provided
    const params: Record<string, any> = {
      repo: repositoryData.repositoryGuid,
      grand: repositoryData.grandGuid || ''
    }

    // Add option parameter if provided
    if (option) {
      params.option = option
    }

    const result = await executeAction({
      teamName: machine.teamName,
      machineName: machine.machineName,
      bridgeName: machine.bridgeName,
      functionName,
      params,
      priority,
      description: `${functionName} ${repository.name}`,
      addedVia: 'machine-repository-list-quick',
      machineVault: machine.vaultContent || '{}',
      repositoryGuid: repositoryData.repositoryGuid,
      repositoryVault: grandRepositoryVault,
      repositoryLoopbackIp: repositoryData.repoLoopbackIp,
      repositoryNetworkMode: repositoryData.repoNetworkMode,
      repositoryTag: repositoryData.repoTag
    })

    if (result.success) {
      if (result.taskId) {
        showMessage('success', t('resources:repositories.queueItemCreated'))
        if (onQueueItemCreated) {
          onQueueItemCreated(result.taskId, machine.machineName)
        }
      } else if (result.isQueued) {
        showMessage('info', t('resources:repositories.highestPriorityQueued'))
      }
    } else {
      showMessage('error', result.error || t('resources:repositories.failedToCreateQueueItem'))
    }
  }

  const handleForkRepository = async (repository: Repository) => {
    try {
      // Find the repository vault data - must match both name AND tag to distinguish forks from grand repos
      const repositoryData = teamRepositories.find(r =>
        r.repositoryName === repository.name &&
        r.repoTag === repository.repoTag
      )

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

        const result = await executeAction({
          teamName: machine.teamName,
          machineName: machine.machineName,
          bridgeName: machine.bridgeName,
          functionName: 'push',
          params,
          priority: 4,
          description: `Fork ${repository.name}:${repository.repoTag || 'latest'} to ${repository.name}:${forkTag}`,
          addedVia: 'machine-repository-list-fork',
          machineVault: machine.vaultContent || '{}',
          repositoryGuid: repositoryData.repositoryGuid,
          repositoryVault: grandRepositoryVault,
          repositoryLoopbackIp: newRepo.repoLoopbackIp,
          repositoryNetworkMode: newRepo.repoNetworkMode,
          repositoryTag: newRepo.repoTag
        })

        if (result.success) {
          if (result.taskId) {
            showMessage('success', t('resources:repositories.forkStarted', { dest: `${repository.name}:${forkTag}` }))
            if (onQueueItemCreated) {
              onQueueItemCreated(result.taskId, machine.machineName)
            }
          } else if (result.isQueued) {
            showMessage('info', t('resources:repositories.highestPriorityQueued'))
          }
        } else {
          throw new Error(result.error || 'Failed to fork repository')
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
    // Use orchestration to prepare fork deletion context
    const context = prepareForkDeletion(repository.name, repository.repoTag, teamRepositories)

    if (context.status === 'error') {
      const errorKey = context.errorCode === 'NOT_FOUND'
        ? 'resources:repositories.repositoryNotFound'
        : 'resources:repositories.cannotDeleteGrandRepository'
      showMessage('error', t(errorKey))
      return
    }

    const parentName = context.parentName || repository.name

    // Show confirmation modal
    modal.confirm({
      title: t('resources:repositories.deleteCloneConfirmTitle'),
      content: t('resources:repositories.deleteCloneConfirmMessage', {
        name: repository.name,
        tag: repository.repoTag || 'latest',
        parentName
      }),
      okText: t('common:delete'),
      okType: 'danger',
      cancelText: t('common:cancel'),
      onOk: async () => {
        try {
          // Get the grand repository vault using orchestration helper
          const grandRepositoryVault = getGrandVaultForOperation(
            context.repositoryGuid!,
            context.grandGuid,
            teamRepositories
          ) || '{}'

          // Step 1: Queue the physical deletion via repo_rm
          const params: Record<string, any> = {
            repo: context.repositoryGuid,
            grand: context.grandGuid
          }

          const result = await executeAction({
            teamName: machine.teamName,
            machineName: machine.machineName,
            bridgeName: machine.bridgeName,
            functionName: 'rm',
            params,
            priority: 4,
            description: `Delete clone ${repository.name}`,
            addedVia: 'machine-repository-list-delete-clone',
            machineVault: machine.vaultContent || '{}',
            repositoryGuid: context.repositoryGuid,
            repositoryVault: grandRepositoryVault,
            repositoryLoopbackIp: context.repoLoopbackIp
          })

          if (result.success) {
            if (result.taskId) {
              showMessage('success', t('resources:repositories.deleteCloneQueued', { name: repository.name, tag: repository.repoTag || 'latest' }))
              if (onQueueItemCreated) {
                onQueueItemCreated(result.taskId, machine.machineName)
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
            } else if (result.isQueued) {
              showMessage('info', t('resources:repositories.highestPriorityQueued'))
            }
          } else {
            showMessage('error', result.error || t('resources:repositories.deleteCloneFailed'))
          }

        } catch (error) {
          showMessage('error', t('resources:repositories.deleteCloneFailed'))
        }
      }
    })
  }

  const handlePromoteToGrand = async (repository: Repository) => {
    // Use orchestration to prepare promotion context
    const context = preparePromotion(repository.name, repository.repoTag, teamRepositories)

    if (context.status === 'error') {
      const errorKey = context.errorCode === 'NOT_FOUND'
        ? 'resources:repositories.repositoryNotFound'
        : 'resources:repositories.alreadyOriginalRepository'
      showMessage('error', t(errorKey))
      return
    }

    const { siblingClones, currentGrandName } = context

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
    // Use orchestration to prepare grand deletion context
    const context = prepareGrandDeletion(repository.name, repository.repoTag, teamRepositories)

    if (context.status === 'error') {
      const errorKey = context.errorCode === 'NOT_FOUND'
        ? 'resources:repositories.repositoryNotFound'
        : 'resources:repositories.notAGrandRepository'
      showMessage('error', t(errorKey))
      return
    }

    // Check for child repositories (clones) before deletion
    if (context.status === 'blocked') {
      // Show error modal with clone list
      modal.error({
        title: t('resources:repositories.cannotDeleteHasClones'),
        content: (
          <div>
            <Typography.Paragraph>
              {t('resources:repositories.hasActiveClonesMessage', {
                name: repository.name,
                count: context.childClones.length
              })}
            </Typography.Paragraph>
            <Typography.Paragraph strong>
              {t('resources:repositories.clonesList')}
            </Typography.Paragraph>
            <ul>
              {context.childClones.map(clone => (
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
          // For grand repositories, use its own vault
          const grandRepositoryVault = getGrandVaultForOperation(
            context.repositoryGuid!,
            context.repositoryGuid, // Grand points to itself
            teamRepositories
          ) || '{}'

          // Step 1: Queue the physical deletion via repo_rm
          const params: Record<string, any> = {
            repo: context.repositoryGuid,
            grand: context.repositoryGuid // Grand points to itself
          }

          const result = await executeAction({
            teamName: machine.teamName,
            machineName: machine.machineName,
            bridgeName: machine.bridgeName,
            functionName: 'rm',
            params,
            priority: 4,
            description: `Delete repository ${repository.name}`,
            addedVia: 'machine-repository-list-delete-grand',
            machineVault: machine.vaultContent || '{}',
            repositoryGuid: context.repositoryGuid,
            repositoryVault: grandRepositoryVault,
            repositoryLoopbackIp: context.repoLoopbackIp
          })

          if (result.success) {
            if (result.taskId) {
              showMessage('success', t('resources:repositories.deleteGrandQueued', { name: repository.name }))
              if (onQueueItemCreated) {
                onQueueItemCreated(result.taskId, machine.machineName)
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
            } else if (result.isQueued) {
              showMessage('info', t('resources:repositories.highestPriorityQueued'))
            }
          } else {
            showMessage('error', result.error || t('resources:repositories.deleteGrandFailed'))
            return Promise.reject()
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
      // Find the repository vault data - must match both name AND tag to distinguish forks from grand repos
      const repositoryData = teamRepositories.find(r =>
        r.repositoryName === selectedRepository.name &&
        r.repoTag === selectedRepository.repoTag
      )

      if (!repositoryData || !repositoryData.vaultContent) {
        showMessage('error', t('resources:repositories.noCredentialsFound', { name: selectedRepository.name }))
        functionModal.close()
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

      // Handle deploy function (multiple machines)
      if (functionData.function.name === 'deploy' && functionData.params.machines) {
        const machinesArray = Array.isArray(functionData.params.machines)
          ? functionData.params.machines
          : [functionData.params.machines]

        // Validate destination filename before processing
        const destFilename = functionData.params.dest?.trim()

        if (!destFilename) {
          showMessage('error', 'Destination filename is required')
          functionModal.close()
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
          functionModal.close()
          setSelectedRepository(null)
          return
        }

        // Now deploy to each target machine using the same repository credential
        for (const targetMachine of machinesArray) {
          try {
            // Find the destination machine's vault data
            const destinationMachine = teamMachines.find(m => m.machineName === targetMachine)
            if (!destinationMachine) {
              showMessage('error', t('resources:repositories.destinationMachineNotFound', { machine: targetMachine }))
              continue
            }

            // Build queue vault for this specific destination
            const deployParams = {
              ...functionData.params,
              // Convert machines array to comma-separated string for bash script
              machines: machinesArray.join(','),
              to: targetMachine,
              dest: newRepo.repositoryGuid,
              repo: repositoryData.repositoryGuid,
              grand: repositoryData.grandGuid || repositoryData.repositoryGuid || ''
            }

            const result = await executeAction({
              teamName: machine.teamName,
              machineName: machine.machineName,
              bridgeName: machine.bridgeName,
              functionName: 'deploy',
              params: deployParams,
              priority: functionData.priority,
              description: `${functionData.description} → ${targetMachine}`,
              addedVia: 'machine-repository-list',
              machineVault: machine.vaultContent || '{}',
              destinationMachineVault: destinationMachine.vaultContent || '{}',
              repositoryGuid,
              repositoryVault,
              repositoryLoopbackIp: newRepo.repoLoopbackIp,
              repositoryNetworkMode: newRepo.repoNetworkMode,
              repositoryTag: newRepo.repoTag
            })

            if (result.success && result.taskId) {
              createdTaskIds.push(result.taskId)
            }
          } catch (error) {
            showMessage('error', t('resources:repositories.failedToDeployTo', { machine: targetMachine }))
          }
        }

        functionModal.close()
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
        // Use core validation to check if backup to storage is allowed
        const backupValidation = canBackupToStorage(repositoryData)
        if (!backupValidation.canBackup) {
          showMessage('error', t('resources:repositories.cannotBackupForkToStorage'))
          functionModal.close()
          setSelectedRepository(null)
          return
        }

        const storagesArray = Array.isArray(functionData.params.storages)
          ? functionData.params.storages
          : [functionData.params.storages]

        const createdTaskIds: string[] = []

        for (const targetStorage of storagesArray) {
          try {
            // Find the destination storage's vault data
            const destinationStorage = teamStorages.find(s => s.storageName === targetStorage)
            if (!destinationStorage) {
              showMessage('error', t('resources:repositories.destinationStorageNotFound', { storage: targetStorage }))
              continue
            }

            // Build queue vault for this specific storage
            const backupParams = {
              ...functionData.params,
              // Convert storages array to comma-separated string for bash script
              storages: storagesArray.join(','),
              to: targetStorage,
              repo: repositoryData.repositoryGuid,
              grand: repositoryData.grandGuid || repositoryData.repositoryGuid || ''
            }

            const result = await executeAction({
              teamName: machine.teamName,
              machineName: machine.machineName,
              bridgeName: machine.bridgeName,
              functionName: 'backup',
              params: backupParams,
              priority: functionData.priority,
              description: `${functionData.description} → ${targetStorage}`,
              addedVia: 'machine-repository-list',
              machineVault: machine.vaultContent || '{}',
              destinationStorageVault: destinationStorage.vaultContent || '{}',
              repositoryGuid,
              repositoryVault,
              repositoryLoopbackIp: repositoryData.repoLoopbackIp,
              repositoryNetworkMode: repositoryData.repoNetworkMode,
              repositoryTag: repositoryData.repoTag
            })

            if (result.success && result.taskId) {
              createdTaskIds.push(result.taskId)
            }
          } catch (error) {
            showMessage('error', t('resources:repositories.failedToBackupTo', { storage: targetStorage }))
          }
        }

        functionModal.close()
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
      const result = await executeAction({
        teamName: machine.teamName,
        machineName: machine.machineName,
        bridgeName: machine.bridgeName,
        functionName: functionData.function.name,
        params: finalParams,
        priority: functionData.priority,
        description: functionData.description,
        addedVia: 'machine-repository-list',
        machineVault: machine.vaultContent || '{}',
        repositoryGuid,
        repositoryVault,
        repositoryLoopbackIp: repositoryData.repoLoopbackIp,
        repositoryNetworkMode: repositoryData.repoNetworkMode,
        repositoryTag: repositoryData.repoTag
      })

      functionModal.close()
      setSelectedRepository(null)

      if (result.success) {
        if (result.taskId) {
          showMessage('success', t('resources:repositories.queueItemCreated'))
          if (onQueueItemCreated) {
            onQueueItemCreated(result.taskId, machine.machineName)
          }
        } else if (result.isQueued) {
          // Item was queued for highest priority management
          showMessage('info', t('resources:repositories.highestPriorityQueued'))
        }
      } else {
        throw new Error(result.error || t('resources:repositories.failedToCreateQueueItem'))
      }
    } catch (error) {
      // Show more specific error message if available
      const errorMessage = error instanceof Error ? error.message : t('resources:repositories.failedToCreateQueueItem')
      showMessage('error', errorMessage)
    }
  }

    

  const systemStatusColumn = createStatusColumn<Container>({
    title: t('resources:containers.status'),
    dataIndex: 'state',
    key: 'status',
    width: 80,
    statusMap: {
      running: { color: 'success', label: t('resources:containers.containerStatusRunning'), icon: <PlayCircleOutlined /> },
      paused: { color: 'warning', label: t('resources:containers.containerStatusPaused'), icon: <PauseCircleOutlined /> },
      restarting: { color: 'blue', label: t('resources:containers.containerStatusRestarting'), icon: <ReloadOutlined /> },
      stopped: { color: 'default', label: t('resources:containers.containerStatusStopped'), icon: <StopOutlined /> },
    },
    defaultConfig: { color: 'default', label: t('resources:containers.containerStatusStopped'), icon: <StopOutlined /> },
  })

  const systemStateColumn = createStatusColumn<Container>({
    title: t('resources:repositories.containerStatus'),
    dataIndex: 'state',
    key: 'state',
    statusMap: {
      running: { color: 'success', label: t('resources:containers.containerStatusRunning') },
      paused: { color: 'warning', label: t('resources:containers.containerStatusPaused') },
      restarting: { color: 'blue', label: t('resources:containers.containerStatusRestarting') },
      stopped: { color: 'default', label: t('resources:containers.containerStatusStopped') },
    },
    defaultConfig: { color: 'default', label: t('resources:containers.containerStatusStopped') },
  })

  const systemNameColumn = createTruncatedColumn<Container>({
    title: t('resources:repositories.containerName'),
    dataIndex: 'name',
    key: 'name',
    sorter: createSorter<Container>('name'),
  })

  const systemImageColumn = createTruncatedColumn<Container>({
    title: t('resources:repositories.containerImage'),
    dataIndex: 'image',
    key: 'image',
    width: 250,
    sorter: createSorter<Container>('image'),
  })

  // System container columns
  const systemContainerColumns: ColumnsType<Container> = [
    {
      ...systemStatusColumn,
      align: 'center',
      sorter: createCustomSorter<Container>((c) =>
        c.state === 'running' ? 0 : c.state === 'paused' ? 1 : 2
      ),
      render: (state: string) => systemStatusColumn.render?.(state === 'exited' ? 'stopped' : state),
    },
    {
      ...systemNameColumn,
      render: (name: string) => (
        <Space>
          <CloudServerOutlined style={{ color: '#722ed1' }} />
          <strong>{systemNameColumn.render?.(name)}</strong>
        </Space>
      ),
    },
    systemImageColumn,
    {
      ...systemStateColumn,
      render: (state: string, record: Container) => (
        <Space>
          {systemStateColumn.render?.(state === 'exited' ? 'stopped' : state)}
          {record.status && <Text type="secondary" style={{ fontSize: 12 }}>{record.status}</Text>}
        </Space>
      ),
    },
    {
      title: t('resources:repositories.containerCPU'),
      dataIndex: 'cpu_percent',
      key: 'cpu_percent',
      sorter: createSorter<Container>('cpu_percent'),
      render: (cpu: string) => cpu || '-',
    },
    {
      title: t('resources:repositories.containerMemory'),
      dataIndex: 'memory_usage',
      key: 'memory_usage',
      sorter: createSorter<Container>('memory_usage'),
      render: (memory: string) => memory || '-',
    },
    {
      title: t('resources:repositories.containerPorts'),
      dataIndex: 'port_mappings',
      key: 'port_mappings',
      ellipsis: true,
      sorter: createArrayLengthSorter<Container>('port_mappings'),
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

  const repositoryStatusColumn = createStatusColumn<RepositoryTableRow>({
    title: t('resources:repositories.status'),
    dataIndex: 'status',
    key: 'status',
    width: 80,
    statusMap: {
      'mounted-running': { color: 'success', label: t('resources:repositories.statusMountedRunning'), icon: <CheckCircleOutlined /> },
      mounted: { color: 'warning', label: t('resources:repositories.statusMountedNotRunning'), icon: <ClockCircleOutlined /> },
      unmounted: { color: 'default', label: t('resources:repositories.statusUnmounted'), icon: <DisconnectOutlined /> },
    },
    defaultConfig: { color: 'default', label: t('resources:repositories.statusUnmounted'), icon: <DisconnectOutlined /> },
  })

  const columns: ColumnsType<RepositoryTableRow> = [
    {
      ...repositoryStatusColumn,
      align: 'center',
      sorter: createCustomSorter<RepositoryTableRow>((r) => {
        if (r._isGroupHeader) return -1
        if (r.mounted && r.docker_running) return 0
        if (r.mounted) return 1
        return 2
      }),
      render: (_: unknown, record: RepositoryTableRow) => {
        if (record._isGroupHeader) {
          return null
        }
        const statusKey = record.mounted && record.docker_running
          ? 'mounted-running'
          : record.mounted
            ? 'mounted'
            : 'unmounted'
        return repositoryStatusColumn.render?.(statusKey)
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
            r.repoTag === record.repoTag
          )
          const isGrand = tagData && coreIsCredential(tagData)
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
            r.repoTag === record.repoTag
          )
          const isOriginal = repositoryData && coreIsCredential(repositoryData)

          return (
            <Space>
              {isOriginal ? <StarOutlined /> : <CopyOutlined />}
              <strong>{getRepositoryDisplayName(record)}</strong>
            </Space>
          )
        }
      },
    },
    createActionColumn<RepositoryTableRow>({
      title: t('common:table.actions'),
      width: 160,
      fixed: 'right',
      renderActions: (record) => {
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
                    loading={isExecuting}
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
          r.repoTag === record.repoTag
        )

        // Build smart menu items based on repository state
        const menuItems = []

        // PRIMARY ACTIONS AT TOP LEVEL

        // Up - always available
        menuItems.push({
          key: 'up',
          label: t('functions:functions.up.name'),
          icon: <PlayCircleOutlined style={componentStyles.icon.small} />,
          onClick: (info: MenuInfo) => {
            info.domEvent.stopPropagation()
            handleQuickAction(record, 'up', 4, 'mount')
          }
        })

        // Down - only when mounted
        if (record.mounted) {
          menuItems.push({
            key: 'down',
            label: t('functions:functions.down.name'),
            icon: <PauseCircleOutlined style={componentStyles.icon.small} />,
            onClick: (info: MenuInfo) => {
              info.domEvent.stopPropagation()
              handleQuickAction(record, 'down', 4, 'unmount')
            }
          })
        }

        // Validate - only when unmounted (tests complete lifecycle from clean state)
        if (!record.mounted) {
          menuItems.push({
            key: 'validate',
            label: t('functions:functions.validate.name'),
            icon: <CheckCircleOutlined style={componentStyles.icon.small} />,
            onClick: (info: MenuInfo) => {
              info.domEvent.stopPropagation()
              handleRunFunction(record, 'validate')
            }
          })
        }

        // Fork - always available (use 'Fork' instead of 'Clone' for consistency)
        menuItems.push({
          key: 'fork',
          label: t('functions:functions.fork.name'),
          icon: <CopyOutlined style={componentStyles.icon.small} />,
          onClick: (info: MenuInfo) => {
            info.domEvent.stopPropagation()
            handleForkRepository(record)
          }
        })

        // Deploy - always available
        menuItems.push({
          key: 'deploy',
          label: t('functions:functions.deploy.name'),
          icon: <CloudUploadOutlined style={componentStyles.icon.small} />,
          onClick: (info: MenuInfo) => {
            info.domEvent.stopPropagation()
            handleRunFunction(record, 'deploy')
          }
        })

        // Backup - only available for grand repositories (not forks)
        const repoIsFork = repositoryData ? coreIsFork(repositoryData) : false
        menuItems.push({
          key: 'backup',
          label: t('functions:functions.backup.name'),
          icon: <SaveOutlined style={componentStyles.icon.small} />,
          onClick: (info: MenuInfo) => {
            info.domEvent.stopPropagation()
            handleRunFunction(record, 'backup')
          },
          disabled: repoIsFork,
          title: repoIsFork ? t('resources:repositories.backupForkDisabledTooltip') : undefined
        })

        // Apply Template - always available
        menuItems.push({
          key: 'apply_template',
          label: t('functions:functions.apply_template.name'),
          icon: <AppstoreOutlined style={componentStyles.icon.small} />,
          onClick: (info: MenuInfo) => {
            info.domEvent.stopPropagation()
            handleRunFunction(record, 'apply_template')
          }
        })

        // ADVANCED SUBMENU FOR STORAGE OPERATIONS
        const advancedSubmenuItems = []

        // Mount/Unmount
        if (!record.mounted) {
          advancedSubmenuItems.push({
            key: 'mount',
            label: t('resources:repositories.mount'),
            icon: <DatabaseOutlined style={componentStyles.icon.small} />,
            onClick: (info: MenuInfo) => {
              info.domEvent.stopPropagation()
              handleQuickAction(record, 'mount', 4)
            }
          })
        } else {
          advancedSubmenuItems.push({
            key: 'unmount',
            label: t('resources:repositories.unmount'),
            icon: <DisconnectOutlined style={componentStyles.icon.small} />,
            onClick: (info: MenuInfo) => {
              info.domEvent.stopPropagation()
              handleQuickAction(record, 'unmount', 4)
            }
          })
        }

        // Resize - only when NOT mounted (offline operation)
        if (!record.mounted) {
          advancedSubmenuItems.push({
            key: 'resize',
            label: t('functions:functions.resize.name'),
            icon: <ShrinkOutlined style={componentStyles.icon.small} />,
            onClick: (info: MenuInfo) => {
              info.domEvent.stopPropagation()
              handleRunFunction(record, 'resize')
            }
          })
        }

        // Expand - only when mounted (online expansion)
        if (record.mounted) {
          advancedSubmenuItems.push({
            key: 'expand',
            label: t('functions:functions.expand.name'),
            icon: <ExpandOutlined style={componentStyles.icon.small} />,
            onClick: (info: MenuInfo) => {
              info.domEvent.stopPropagation()
              handleRunFunction(record, 'expand')
            }
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
          onClick: (info: MenuInfo) => {
            info.domEvent.stopPropagation()
            handleRunFunction(record)
          }
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
        if (repositoryData && coreIsFork(repositoryData)) {
          menuItems.push({
            key: 'promote-to-grand',
            label: t('resources:repositories.promoteToGrand'),
            icon: <RiseOutlined style={componentStyles.icon.small} />,
            onClick: (info: MenuInfo) => {
              info.domEvent.stopPropagation()
              handlePromoteToGrand(record)
            }
          })
          menuItems.push({
            key: 'delete-fork',
            label: t('resources:repositories.deleteFork'),
            icon: <DeleteOutlined style={componentStyles.icon.small} />,
            onClick: (info: MenuInfo) => {
              info.domEvent.stopPropagation()
              handleDeleteFork(record)
            },
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
          onClick: (info: MenuInfo) => {
            info.domEvent.stopPropagation()
            handleRenameRepository(record)
          }
        })

        // Delete Grand Repository - only for grand repositories (no parent)
        if (repositoryData && coreIsCredential(repositoryData)) {
          menuItems.push({
            key: 'delete-grand',
            label: t('resources:repositories.deleteGrand'),
            icon: <DeleteOutlined style={componentStyles.icon.small} />,
            onClick: (info: MenuInfo) => {
              info.domEvent.stopPropagation()
              handleDeleteGrandRepository(record)
            },
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
                  loading={isExecuting}
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
                  style={componentStyles.controlSurface}
                  data-testid={`machine-repo-list-add-credential-${record.name}`}
                  aria-label={t('resources:repositories.addCredential')}
                />
              </Tooltip>
            )}
          </Space>
        )
      },
    }),
  ]

  if (loading) {
    return (
      <div style={{ padding: '20px' }} data-testid="machine-repo-list-loading">
        <LoadingWrapper
          loading
          centered
          minHeight={200}
          tip={t('resources:repositories.fetchingRepositories') as string}
        >
          <div />
        </LoadingWrapper>
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
          <LoadingWrapper
            loading
            centered
            minHeight={120}
            tip={t('common:general.refreshing') as string}
          >
            <div />
          </LoadingWrapper>
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
              r.repoTag === record.repoTag
            )
            const isForkRow = repositoryData && coreIsFork(repositoryData)
            return isForkRow ? 'repository-fork-row' : 'repository-grand-row'
          }

          // Regular single repository rows
          const repositoryData = teamRepositories.find(r =>
            r.repositoryName === record.name &&
            r.repoTag === record.repoTag
          )
          const isClone = repositoryData && coreIsFork(repositoryData)
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
                if (target.closest('button') || target.closest('.ant-dropdown')) {
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
              if (target.closest('button') || target.closest('.ant-dropdown')) {
                return
              }

              // Row clicks always navigate to containers page
              // Only the eye button should trigger detail panel (via onRepositoryClick)
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
        open={functionModal.isOpen}
        onCancel={() => {
          functionModal.close()
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
                const currentRepoData = teamRepositories.find(r => r.repositoryName === selectedRepository.name && r.repoTag === selectedRepository.repoTag);
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
        loading={isExecuting}
        showMachineSelection={false}
        teamName={machine.teamName}
        hiddenParams={['repo', 'grand']}
        defaultParams={{
          repo: (() => {
            const repo = teamRepositories.find(r => r.repositoryName === selectedRepository?.name && r.repoTag === selectedRepository?.repoTag);
            return repo?.repositoryGuid || '';
          })(),
          grand: teamRepositories.find(r => r.repositoryName === selectedRepository?.name && r.repoTag === selectedRepository?.repoTag)?.grandGuid || ''
        }}
        initialParams={
          selectedFunction === 'push' && selectedRepository ? (() => {
            // Find the current repository data
            const currentRepoData = teamRepositories.find(r => r.repositoryName === selectedRepository.name && r.repoTag === selectedRepository.repoTag);

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
              const currentRepoData = teamRepositories.find(r => r.repositoryName === selectedRepository.name && r.repoTag === selectedRepository.repoTag);
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
