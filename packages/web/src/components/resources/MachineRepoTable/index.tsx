import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Alert, Tag, Space, Typography, Button, Tooltip, Modal, Input } from 'antd'
import type { TableProps } from 'antd'
import type { MenuProps } from 'antd'
import { isAxiosError } from 'axios'
import { useTableStyles } from '@/hooks/useComponentStyles'
import { CheckCircleOutlined, FunctionOutlined, PlayCircleOutlined, StopOutlined, ExpandOutlined, CloudUploadOutlined, SaveOutlined, PauseCircleOutlined, ReloadOutlined, DeleteOutlined, DesktopOutlined, ClockCircleOutlined, DatabaseOutlined, DisconnectOutlined, KeyOutlined, AppstoreOutlined, CloudServerOutlined, RightOutlined, CopyOutlined, RiseOutlined, StarOutlined, EditOutlined, ShrinkOutlined, ControlOutlined, CaretDownOutlined, CaretRightOutlined, FolderOutlined, EyeOutlined } from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { useDialogState } from '@/hooks/useDialogState'
import * as S from './styles'
import { type QueueFunction } from '@/api/queries/queue'
import { useQueueAction } from '@/hooks/useQueueAction'
import { Machine } from '@/types'
import type { Repo as TeamRepo } from '@rediacc/shared/types'
import { useTeams } from '@/api/queries/teams'
import { useRepos, useCreateRepo, useDeleteRepo, usePromoteRepoToGrand, useUpdateRepoName } from '@/api/queries/repos'
import { useMachines } from '@/api/queries/machines'
import { useStorage } from '@/api/queries/storage'
import type { ColumnsType } from 'antd/es/table'
import type { MenuInfo } from 'rc-menu/lib/interface'
import FunctionSelectionModal from '@/components/common/FunctionSelectionModal'
import { ActionButtonGroup } from '@/components/common/ActionButtonGroup'
import { LocalActionsMenu } from '../internal/LocalActionsMenu'
import { showMessage } from '@/utils/messages'
import { DESIGN_TOKENS } from '@/utils/styleConstants'
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

const RepoTableComponent = S.StyledTable as React.ComponentType<TableProps<RepoTableRow>>
const SystemTableComponent = S.StyledTable as React.ComponentType<TableProps<Container>>

interface Repo {
  name: string
  repoTag?: string  // Repo tag (e.g., 'latest', 'fork-2025-01-09-14-30-00')
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

// Helper function to format Repo display name as name:tag
const getRepoDisplayName = (repo: Repo): string => {
  return `${repo.name}:${repo.repoTag || 'latest'}`
}

const getAxiosErrorMessage = (error: unknown, fallback: string) => {
  if (isAxiosError(error)) {
    const responseMessage = (error.response?.data as { message?: string } | undefined)?.message
    return responseMessage || error.message || fallback
  }
  return fallback
}

// Data structure for grouped repos
interface GroupedRepo {
  name: string                    // Repo name (e.g., "webapp")
  tags: Repo[]              // All tags for this name
  grandTag: Repo | null     // The grand Repo (tag='latest', no parent)
  forkTags: Repo[]          // Fork repos (tag!='latest' or has parent)
  isExpanded: boolean             // UI state for expand/collapse
}

// Extended Repo interface for table rendering
interface RepoTableRow extends Repo {
  key?: string
  _isGroupHeader?: boolean
  _groupData?: GroupedRepo
  _isTagRow?: boolean
  _indentLevel?: number
  _isLastInGroup?: boolean
  actionId?: string
}

// Helper to group repos by name
const groupReposByName = (repos: Repo[], teamRepos: TeamRepo[]): GroupedRepo[] => {
  // Group by name
  const grouped = repos.reduce((acc, repo) => {
    if (!acc[repo.name]) {
      acc[repo.name] = []
    }
    acc[repo.name].push(repo)
    return acc
  }, {} as Record<string, Repo[]>)

  // Transform to GroupedRepo structure
  return Object.entries(grouped).map(([name, tags]) => {
    // Find grand Repo - one with no parent or parent equals self
    const grandTag = tags.find(r => {
      const tagData = teamRepos.find(tr =>
        tr.repoName === r.name &&
        tr.repoTag === r.repoTag
      )
      // Grand repo has no parentGuid or parentGuid equals repoGuid
      return tagData && (!tagData.parentGuid || tagData.parentGuid === tagData.repoGuid)
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
  Repo?: string
  [key: string]: unknown
}

interface RepoService {
  Repo?: string
  service_name?: string
  unit_file?: string
  [key: string]: unknown
}

interface RepoServicesState {
  services: RepoService[]
  error: string | null
}

interface RepoContainersState {
  containers: Container[]
  error: string | null
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

interface MachineRepoTableProps {
  machine: Machine
  onActionComplete?: () => void
  hideSystemInfo?: boolean
  onCreateRepo?: (machine: Machine, repoGuid: string) => void
  onRepoClick?: (Repo: Repo) => void
  highlightedRepo?: Repo | null
  onContainerClick?: (container: Container) => void
  highlightedContainer?: Container | null
  isLoading?: boolean
  onRefreshMachines?: () => Promise<void>
  refreshKey?: number // Used to trigger re-rendering when parent wants to force refresh
  onQueueItemCreated?: (taskId: string, machineName: string) => void // Callback to open parent's QueueItemTraceModal with machine context
}


export const MachineRepoTable: React.FC<MachineRepoTableProps> = ({ machine, onActionComplete, hideSystemInfo = false, onCreateRepo, onRepoClick, highlightedRepo, onContainerClick: _onContainerClick, highlightedContainer: _highlightedContainer, isLoading, onRefreshMachines: _onRefreshMachines, refreshKey, onQueueItemCreated }) => {
  const { t } = useTranslation(['resources', 'common', 'machines', 'functions'])
  const navigate = useNavigate()
  const [modal, contextHolder] = Modal.useModal()
  const userEmail = useAppSelector((state) => state.auth.user?.email || '')
  const tableStyles = useTableStyles()
  const [_repos, setRepos] = useState<Repo[]>([])
  const [systemContainers] = useState<Container[]>([])
  const [_systemInfo, setSystemInfo] = useState<SystemInfo | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedRepo, setSelectedRepo] = useState<Repo | null>(null)
  const functionModal = useDialogState<void>()
  const [selectedFunction, setSelectedFunction] = useState<string | null>(null)
  const [_servicesData, setServicesData] = useState<Record<string, RepoServicesState>>({})
  const [containersData, setContainersData] = useState<Record<string, RepoContainersState>>({})
  const [createdRepoName, setCreatedRepoName] = useState<string | null>(null)
  const [createdRepoTag, setCreatedRepoTag] = useState<string | null>(null)
  const [groupedRepos, setGroupedRepos] = useState<GroupedRepo[]>([])

  // Queue action hook for function execution
  const { executeAction, isExecuting } = useQueueAction()
  const { data: teams } = useTeams()
  const { data: teamRepos = [], isLoading: reposLoading, refetch: refetchRepos } = useRepos(machine.teamName)
  const { data: teamMachines = [] } = useMachines(machine.teamName)
  const { data: teamStorages = [] } = useStorage(machine.teamName)
  const createRepoMutation = useCreateRepo()
  const deleteRepoMutation = useDeleteRepo()
  const promoteRepoMutation = usePromoteRepoToGrand()
  const updateRepoNameMutation = useUpdateRepoName()

  // IMPORTANT: This component uses a hybrid approach:
  // 1. teamRepos (from API) - provides Repo credentials and metadata
  // 2. vaultStatus data - provides machine-specific Repo status (mounted, size, containers, etc.)
  // 
  // The vaultStatus is populated by the bridge after each operation via list_system() function.
  // While this data can become stale, it provides valuable machine-specific information
  // that isn't available through the direct API (like mount status, disk usage, container counts).
  useEffect(() => {
    // Use cached vaultStatus data from the machine object
    if (!reposLoading && machine) {
      if (machine.vaultStatus) {
        // Parse vaultStatus using core utility
        const parsed = parseVaultStatus(machine.vaultStatus)

        if (parsed.error) {
          // Invalid vaultStatus data format (e.g., jq errors)
          setError('Invalid Repo data')
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
              
              if (result.repos && Array.isArray(result.repos)) {
                // Map Repo GUIDs back to names if needed
                const mappedRepos = result.repos.map((repo: Repo) => {
                  // Check if the name looks like a GUID
                  const isGuid = isValidGuid(repo.name);

                  if (isGuid) {
                    // Find the matching Repo by GUID
                    const matchingRepo = teamRepos.find(r => r.repoGuid === repo.name);
                    if (matchingRepo) {
                      return {
                        ...repo,
                        name: matchingRepo.repoName,
                        repoTag: matchingRepo.repoTag,  // Include the tag to distinguish grand from forks
                        isUnmapped: false
                      };
                    } else {
                      // No matching Repo found, mark as unmapped
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
                
                // Count plugin containers for each Repo before setting
                const reposWithPluginCounts = mappedRepos.map((repo: Repo) => {
                  // Initialize plugin count
                  let pluginCount = 0
                  
                  // Count containers that are plugins (name starts with "plugin-")
                  if (result.containers && Array.isArray(result.containers)) {
                    result.containers.forEach((container: Container) => {
                      // Check if this container belongs to this Repo
                      const belongsToRepo = container.Repo === repo.name
                      
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

                // Sort repos hierarchically: originals first, then their children
                const sortedRepos = reposWithPluginCounts.sort((a: Repo, b: Repo) => {
                  const aData = teamRepos.find(r => r.repoName === a.name && r.repoTag === a.repoTag)
                  const bData = teamRepos.find(r => r.repoName === b.name && r.repoTag === b.repoTag)

                  // Get family names (grand parent name or self)
                  const aFamily = aData?.grandGuid ? teamRepos.find(r => r.repoGuid === aData.grandGuid)?.repoName || a.name : a.name
                  const bFamily = bData?.grandGuid ? teamRepos.find(r => r.repoGuid === bData.grandGuid)?.repoName || b.name : b.name

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

                setRepos(sortedRepos)

                // Group repos by name for hierarchical display
                const grouped = groupReposByName(sortedRepos, teamRepos)
                setGroupedRepos(grouped)

                // Process containers and services if included
                if (result.containers && Array.isArray(result.containers)) {
                  // Group containers by Repo
                  const containersMap: Record<string, RepoContainersState> = {}
                  
                  // Initialize empty containers for all repos
                  mappedRepos.forEach((repo: Repo) => {
                    containersMap[repo.name] = { containers: [], error: null }
                  })
                  
                  result.containers.forEach((container: Container) => {
                    // Check if container has a Repo field
                    if (container.Repo) {
                      const repoGuid = container.Repo
                      // Find the mapped Repo that corresponds to this GUID
                      const mappedRepo = mappedRepos.find((repo: Repo) => {
                        // Find the original Repo with this GUID
                        const originalRepo = result.repos.find((r: Repo) => r.name === repoGuid)
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
                  // Group services by Repo
                  const servicesMap: Record<string, RepoServicesState> = {}
                  
                  // Initialize empty services for all repos
                  mappedRepos.forEach((repo: Repo) => {
                    servicesMap[repo.name] = { services: [], error: null }
                  })
                  
                  // Add services to their respective repos
                  result.services.forEach((service: RepoService) => {
                    // Check if service has a Repo field (newer format)
                    if (service.Repo) {
                      const repoGuid = service.Repo
                      // Find the mapped Repo that corresponds to this GUID
                      const mappedRepo = mappedRepos.find((repo: Repo) => {
                        // Find the original Repo with this GUID
                        const originalRepo = result.repos.find((r: Repo) => r.name === repoGuid)
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
                        // Find the mapped Repo
                        const mappedRepo = mappedRepos.find((repo: Repo) => {
                        const originalRepo = result.repos.find((r: Repo) => r.name === repoGuid)
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
                setRepos([])
              }
              
              setLoading(false)
            }
          } catch {
            setError('Failed to parse Repo data')
            setLoading(false)
          }
        }
      } else {
        // No vaultStatus data available
        setRepos([])
        setLoading(false)
      }
    }
  }, [machine, reposLoading, teamRepos, refreshKey, setRepos, setServicesData, setContainersData, setLoading, setError])

  const handleRefresh = () => {
    // Trigger parent component to refresh machine data
    if (onActionComplete) {
      onActionComplete()
    }
  }

  // Toggle expand/collapse for a Repo group
  const toggleRepoGroup = (repoName: string) => {
    setGroupedRepos(prev =>
      prev.map(group =>
        group.name === repoName
          ? { ...group, isExpanded: !group.isExpanded }
          : group
      )
    )
  }

  const handleRunFunction = (Repo: Repo, functionName?: string) => {
    setSelectedRepo(Repo)
    setSelectedFunction(functionName || null)
    functionModal.open()
  }

  const handleQuickAction = async (Repo: Repo, functionName: string, priority: number = 4, option?: string) => {
    // Find the Repo vault data - must match both name AND tag to distinguish forks from grand repos
    const RepoData = teamRepos.find(r =>
      r.repoName === Repo.name &&
      r.repoTag === Repo.repoTag
    )

    if (!RepoData || !RepoData.vaultContent) {
      showMessage('error', t('resources:repos.noCredentialsFound', { name: Repo.name }))
      return
    }

    // Get grand Repo vault using core orchestration
    const grandRepoVault = getGrandVaultForOperation(
      RepoData.repoGuid,
      RepoData.grandGuid,
      teamRepos
    ) || RepoData.vaultContent

    // Build params with option if provided
    const params: Record<string, unknown> = {
      repo: RepoData.repoGuid,
      grand: RepoData.grandGuid || ''
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
      addedVia: 'machine-Repo-list-quick',
      machineVault: machine.vaultContent || '{}',
      repoGuid: RepoData.repoGuid,
      repoVault: grandRepoVault,
      repoNetworkId: RepoData.repoNetworkId,
      repoNetworkMode: RepoData.repoNetworkMode,
      repoTag: RepoData.repoTag
    })

    if (result.success) {
      if (result.taskId) {
        showMessage('success', t('resources:repos.queueItemCreated'))
        if (onQueueItemCreated) {
          onQueueItemCreated(result.taskId, machine.machineName)
        }
      } else if (result.isQueued) {
        showMessage('info', t('resources:repos.highestPriorityQueued'))
      }
    } else {
      showMessage('error', result.error || t('resources:repos.failedToCreateQueueItem'))
    }
  }

  const handleForkRepo = async (Repo: Repo) => {
    try {
      // Find the Repo vault data - must match both name AND tag to distinguish forks from grand repos
      const RepoData = teamRepos.find(r =>
        r.repoName === Repo.name &&
        r.repoTag === Repo.repoTag
      )

      if (!RepoData || !RepoData.vaultContent) {
        showMessage('error', t('resources:repos.noCredentialsFound', { name: Repo.name }))
        return
      }

      // Find the grand Repo vault if grandGuid exists
      let grandRepoVault = RepoData.vaultContent
      if (RepoData.grandGuid) {
        const grandRepo = teamRepos.find(r => r.repoGuid === RepoData.grandGuid)
        if (grandRepo && grandRepo.vaultContent) {
          grandRepoVault = grandRepo.vaultContent
        }
      }

      // Generate fork tag with timestamp
      const timestamp = new Date().toISOString().slice(0, 19).replace('T', '-').replace(/:/g, '-')
      const forkTag = `fork-${timestamp}`  // e.g., fork-2025-01-09-14-30-00

      // Create a new Repo credential for the fork (same name, different tag)
      try {
        await createRepoMutation.mutateAsync({
          teamName: machine.teamName,
          repoName: Repo.name,  // SAME NAME
          repoTag: forkTag,  // NEW TAG
          parentRepoName: Repo.name
        })

        // Store the created Repo name and tag for potential cleanup
        setCreatedRepoName(Repo.name)  // Track the name (not destFilename)
        setCreatedRepoTag(forkTag)  // NEW: Track the tag for cleanup

        // Immediately refresh the repos list to get the new Repo
        const { data: updatedRepos } = await refetchRepos()

        // Find the newly created fork Repo to get its GUID (same name, new tag)
        const newRepo = updatedRepos?.find(r => r.repoName === Repo.name && r.repoTag === forkTag)

        if (!newRepo || !newRepo.repoGuid) {
          throw new Error('Could not find newly created fork Repo')
        }

        // Build params for push function
        const state = Repo.mounted ? 'online' : 'offline'
        const params: Record<string, unknown> = {
          repo: RepoData.repoGuid,
          dest: newRepo.repoGuid,
          destinationType: 'machine',
          to: machine.machineName,
          state: state,
          grand: RepoData.grandGuid || RepoData.repoGuid || ''
        }

        const result = await executeAction({
          teamName: machine.teamName,
          machineName: machine.machineName,
          bridgeName: machine.bridgeName,
          functionName: 'push',
          params,
          priority: 4,
          addedVia: 'machine-Repo-list-fork',
          machineVault: machine.vaultContent || '{}',
          repoGuid: RepoData.repoGuid,
          repoVault: grandRepoVault,
          repoNetworkId: newRepo.repoNetworkId,
          repoNetworkMode: newRepo.repoNetworkMode,
          repoTag: newRepo.repoTag
        })

        if (result.success) {
          if (result.taskId) {
            showMessage('success', t('resources:repos.forkStarted', { dest: `${Repo.name}:${forkTag}` }))
            if (onQueueItemCreated) {
              onQueueItemCreated(result.taskId, machine.machineName)
            }
          } else if (result.isQueued) {
            showMessage('info', t('resources:repos.highestPriorityQueued'))
          }
        } else {
          throw new Error(result.error || 'Failed to fork Repo')
        }

      } catch {
        // If we already created the Repo but failed to start the fork, clean it up
        if (createdRepoName && createdRepoTag) {
          try {
            await deleteRepoMutation.mutateAsync({
              teamName: machine.teamName,
              repoName: createdRepoName,
              repoTag: createdRepoTag
            })
          } catch {
            // Failed to cleanup Repo after error
          }
        }
        showMessage('error', t('resources:repos.failedToForkRepo'))
        return
      }

    } catch {
      showMessage('error', t('resources:repos.failedToForkRepo'))
    }
  }

  const handleDeleteFork = async (Repo: Repo) => {
    // Use orchestration to prepare fork deletion context
    const context = prepareForkDeletion(Repo.name, Repo.repoTag, teamRepos)

    if (context.status === 'error') {
      const errorKey = context.errorCode === 'NOT_FOUND'
        ? 'resources:repos.RepoNotFound'
        : 'resources:repos.cannotDeleteGrandRepo'
      showMessage('error', t(errorKey))
      return
    }

    const parentName = context.parentName || Repo.name

    // Show confirmation modal
    modal.confirm({
      title: t('resources:repos.deleteCloneConfirmTitle'),
      content: t('resources:repos.deleteCloneConfirmMessage', {
        name: Repo.name,
        tag: Repo.repoTag || 'latest',
        parentName
      }),
      okText: t('common:delete'),
      okType: 'danger',
      cancelText: t('common:cancel'),
      onOk: async () => {
        try {
          // Get the grand Repo vault using orchestration helper
          const grandRepoVault = getGrandVaultForOperation(
            context.repoGuid!,
            context.grandGuid,
            teamRepos
          ) || '{}'

          // Step 1: Queue the physical deletion via repo_rm
          const params: Record<string, unknown> = {
            repo: context.repoGuid,
            grand: context.grandGuid
          }

          const result = await executeAction({
            teamName: machine.teamName,
            machineName: machine.machineName,
            bridgeName: machine.bridgeName,
            functionName: 'rm',
            params,
            priority: 4,
            addedVia: 'machine-Repo-list-delete-clone',
            machineVault: machine.vaultContent || '{}',
            repoGuid: context.repoGuid,
            repoVault: grandRepoVault,
            repoNetworkId: context.repoNetworkId
          })

          if (result.success) {
            if (result.taskId) {
              showMessage('success', t('resources:repos.deleteCloneQueued', { name: Repo.name, tag: Repo.repoTag || 'latest' }))
              if (onQueueItemCreated) {
                onQueueItemCreated(result.taskId, machine.machineName)
              }

              // Step 2: Delete the credential from database after queuing
              try {
                await deleteRepoMutation.mutateAsync({
                  teamName: machine.teamName,
                  repoName: Repo.name,
                  repoTag: Repo.repoTag || 'latest'
                })
                showMessage('success', t('resources:repos.deleteForkSuccess'))
              } catch {
                showMessage('warning', t('resources:repos.deleteCloneCredentialFailed'))
              }
            } else if (result.isQueued) {
              showMessage('info', t('resources:repos.highestPriorityQueued'))
            }
          } else {
            showMessage('error', result.error || t('resources:repos.deleteCloneFailed'))
          }

        } catch {
          showMessage('error', t('resources:repos.deleteCloneFailed'))
        }
      }
    })
  }

  const handlePromoteToGrand = async (Repo: Repo) => {
    // Use orchestration to prepare promotion context
    const context = preparePromotion(Repo.name, Repo.repoTag, teamRepos)

    if (context.status === 'error') {
      const errorKey = context.errorCode === 'NOT_FOUND'
        ? 'resources:repos.RepoNotFound'
        : 'resources:repos.alreadyOriginalRepo'
      showMessage('error', t(errorKey))
      return
    }

    const { siblingClones, currentGrandName } = context

    // Show confirmation modal
    modal.confirm({
      title: t('resources:repos.promoteToGrandTitle'),
      content: (
        <div>
          <Typography.Paragraph>
            {t('resources:repos.promoteToGrandMessage', {
              name: Repo.name,
              grand: currentGrandName
            })}
          </Typography.Paragraph>
          {siblingClones.length > 0 && (
            <>
              <Typography.Paragraph>
                {t('resources:repos.promoteWillUpdateSiblings', { count: siblingClones.length })}
              </Typography.Paragraph>
              <ul>
                {siblingClones.map(clone => (
                  <li key={clone.repoGuid}>{clone.repoName}</li>
                ))}
              </ul>
            </>
          )}
          <Alert
            message={t('resources:repos.promoteWarning')}
            type="warning"
            showIcon
            style={{ marginTop: 16 }}
          />
        </div>
      ),
      okText: t('resources:repos.promoteButton'),
      okType: 'primary',
      cancelText: t('common:cancel'),
      onOk: async () => {
        try {
        await promoteRepoMutation.mutateAsync({
          teamName: machine.teamName,
          repoName: Repo.name
        })
          showMessage('success', t('resources:repos.promoteSuccess', { name: Repo.name }))
        } catch (error: unknown) {
          const errorMessage = getAxiosErrorMessage(error, t('resources:repos.promoteFailed'))
          showMessage('error', errorMessage)
        }
      }
    })
  }

  const handleRenameRepo = async (Repo: Repo) => {
    let newName = Repo.name

    modal.confirm({
      title: t('resources:repos.renameTitle'),
      content: (
        <div>
          <Typography.Paragraph>
            {t('resources:repos.renameMessage', { name: Repo.name })}
          </Typography.Paragraph>
          <Input
            defaultValue={Repo.name}
            placeholder={t('resources:repos.newRepoName')}
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
          showMessage('error', t('resources:repos.emptyNameError'))
          return Promise.reject()
        }

        if (trimmedName === Repo.name) {
          showMessage('info', t('resources:repos.nameUnchanged'))
          return Promise.reject()
        }

        // Check if name already exists
        const existingRepo = teamRepos.find(r => r.repoName === trimmedName)
        if (existingRepo) {
          showMessage('error', t('resources:repos.nameAlreadyExists', { name: trimmedName }))
          return Promise.reject()
        }

        try {
          await updateRepoNameMutation.mutateAsync({
            teamName: machine.teamName,
            currentRepoName: Repo.name,
            newRepoName: trimmedName
          })
          showMessage('success', t('resources:repos.renameSuccess', { oldName: Repo.name, newName: trimmedName }))

          // Refresh Repo list
          if (onActionComplete) {
            onActionComplete()
          }
        } catch (error: unknown) {
          const errorMessage = getAxiosErrorMessage(error, t('resources:repos.renameFailed'))
          showMessage('error', errorMessage)
          return Promise.reject()
        }
      }
    })
  }

  const handleDeleteGrandRepo = async (Repo: Repo) => {
    // Use orchestration to prepare grand deletion context
    const context = prepareGrandDeletion(Repo.name, Repo.repoTag, teamRepos)

    if (context.status === 'error') {
      const errorKey = context.errorCode === 'NOT_FOUND'
        ? 'resources:repos.RepoNotFound'
        : 'resources:repos.notAGrandRepo'
      showMessage('error', t(errorKey))
      return
    }

    // Check for child repos (clones) before deletion
    if (context.status === 'blocked') {
      // Show error modal with clone list
      modal.error({
        title: t('resources:repos.cannotDeleteHasClones'),
        content: (
          <div>
            <Typography.Paragraph>
              {t('resources:repos.hasActiveClonesMessage', {
                name: Repo.name,
                count: context.childClones.length
              })}
            </Typography.Paragraph>
            <Typography.Paragraph strong>
              {t('resources:repos.clonesList')}
            </Typography.Paragraph>
            <ul>
              {context.childClones.map(clone => (
                <li key={clone.repoGuid}>{clone.repoName}</li>
              ))}
            </ul>
            <Typography.Paragraph>
              {t('resources:repos.deleteOptionsMessage')}
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
      title: t('resources:repos.deleteGrandConfirmTitle'),
      content: (
        <div>
          <Alert
            message={t('resources:repos.deleteGrandWarning')}
            description={t('resources:repos.deleteGrandWarningDesc', { name: Repo.name })}
            type="warning"
            showIcon
            style={{ marginBottom: 16 }}
          />
          <Typography.Text strong>
            {t('resources:repos.deleteGrandConfirmPrompt', { name: Repo.name })}
          </Typography.Text>
          <input
            type="text"
            placeholder={Repo.name}
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
        // Verify confirmation input matches Repo name
        if (confirmationInput !== Repo.name) {
          showMessage('error', t('resources:repos.deleteGrandConfirmationMismatch'))
          return Promise.reject()
        }

        try {
          // For grand repos, use its own vault
          const grandRepoVault = getGrandVaultForOperation(
            context.repoGuid!,
            context.repoGuid, // Grand points to itself
            teamRepos
          ) || '{}'

          // Step 1: Queue the physical deletion via repo_rm
          const params: Record<string, unknown> = {
            repo: context.repoGuid,
            grand: context.repoGuid // Grand points to itself
          }

          const result = await executeAction({
            teamName: machine.teamName,
            machineName: machine.machineName,
            bridgeName: machine.bridgeName,
            functionName: 'rm',
            params,
            priority: 4,
            addedVia: 'machine-Repo-list-delete-grand',
            machineVault: machine.vaultContent || '{}',
            repoGuid: context.repoGuid,
            repoVault: grandRepoVault,
            repoNetworkId: context.repoNetworkId
          })

          if (result.success) {
            if (result.taskId) {
              showMessage('success', t('resources:repos.deleteGrandQueued', { name: Repo.name }))
              if (onQueueItemCreated) {
                onQueueItemCreated(result.taskId, machine.machineName)
              }

              // Step 2: Delete the credential from database after queuing
              try {
                await deleteRepoMutation.mutateAsync({
                  teamName: machine.teamName,
                  repoName: Repo.name,
                  repoTag: Repo.repoTag || 'latest'
                })
                showMessage('success', t('resources:repos.deleteGrandSuccess'))
              } catch {
                showMessage('warning', t('resources:repos.deleteGrandCredentialFailed'))
              }
            } else if (result.isQueued) {
              showMessage('info', t('resources:repos.highestPriorityQueued'))
            }
          } else {
            showMessage('error', result.error || t('resources:repos.deleteGrandFailed'))
            return Promise.reject()
          }

        } catch {
          showMessage('error', t('resources:repos.deleteGrandFailed'))
          return Promise.reject()
        }
      }
    })
  }


  const handleFunctionSubmit = async (functionData: {
    function: QueueFunction
    params: Record<string, unknown>
    priority: number
    description: string
  }) => {
    if (!selectedRepo) return

    try {
      // Find the Repo vault data - must match both name AND tag to distinguish forks from grand repos
      const RepoData = teamRepos.find(r =>
        r.repoName === selectedRepo.name &&
        r.repoTag === selectedRepo.repoTag
      )

      if (!RepoData || !RepoData.vaultContent) {
        showMessage('error', t('resources:repos.noCredentialsFound', { name: selectedRepo.name }))
        functionModal.close()
        setSelectedRepo(null)
        return
      }
      
      // Find the grand Repo vault if grandGuid exists
      let grandRepoVault = RepoData.vaultContent
      if (RepoData.grandGuid) {
        const grandRepo = teamRepos.find(r => r.repoGuid === RepoData.grandGuid)
        if (grandRepo && grandRepo.vaultContent) {
          grandRepoVault = grandRepo.vaultContent
        }
      }

      const finalParams = { ...functionData.params }
      const repoGuid = RepoData.repoGuid
      const repoVault = grandRepoVault

      // Handle deploy function (multiple machines)
      if (functionData.function.name === 'deploy' && functionData.params.machines) {
        const machinesArray = Array.isArray(functionData.params.machines)
          ? functionData.params.machines
          : [functionData.params.machines]

        // Validate destination filename before processing
        const destinationParam = functionData.params.dest
        const destFilename = typeof destinationParam === 'string' ? destinationParam.trim() : ''

        if (!destFilename) {
          showMessage('error', 'Destination filename is required')
          functionModal.close()
          setSelectedRepo(null)
          return
        }

        const createdTaskIds: string[] = []

        // Generate deploy tag with timestamp (similar to fork)
        const timestamp = new Date().toISOString().slice(0, 19).replace('T', '-').replace(/:/g, '-')
        const deployTag = `deploy-${timestamp}`  // e.g., deploy-2025-01-09-14-30-00

        // Create Repo credential ONCE (not per machine - it's team-wide)
        let newRepo
        try {
        await createRepoMutation.mutateAsync({
          teamName: machine.teamName,
          repoName: destFilename,
          repoTag: deployTag,
          parentRepoName: selectedRepo.name
        })

          // Refresh repos list
          const { data: updatedRepos } = await refetchRepos()
          newRepo = updatedRepos?.find(r => r.repoName === destFilename && r.repoTag === deployTag)

          if (!newRepo || !newRepo.repoGuid) {
            throw new Error('Could not find newly created Repo')
          }
        } catch {
          showMessage('error', t('resources:repos.failedToCreateRepo'))
          functionModal.close()
          setSelectedRepo(null)
          return
        }

        // Now deploy to each target machine using the same Repo credential
        for (const targetMachine of machinesArray) {
          try {
            // Find the destination machine's vault data
            const destinationMachine = teamMachines.find(m => m.machineName === targetMachine)
            if (!destinationMachine) {
              showMessage('error', t('resources:repos.destinationMachineNotFound', { machine: targetMachine }))
              continue
            }

            // Build queue vault for this specific destination
            const deployParams = {
              ...functionData.params,
              // Convert machines array to comma-separated string for bash script
              machines: machinesArray.join(','),
              to: targetMachine,
              dest: newRepo.repoGuid,
              repo: RepoData.repoGuid,
              grand: RepoData.grandGuid || RepoData.repoGuid || '',
              state: selectedRepo.mounted ? 'online' : 'offline'
            }

            const result = await executeAction({
              teamName: machine.teamName,
              machineName: machine.machineName,
              bridgeName: machine.bridgeName,
              functionName: 'deploy',
              params: deployParams,
              priority: functionData.priority,
              addedVia: 'machine-Repo-list',
              machineVault: machine.vaultContent || '{}',
              destinationMachineVault: destinationMachine.vaultContent || '{}',
              repoGuid,
              repoVault,
              repoNetworkId: newRepo.repoNetworkId,
              repoNetworkMode: newRepo.repoNetworkMode,
              repoTag: newRepo.repoTag
            })

            if (result.success && result.taskId) {
              createdTaskIds.push(result.taskId)
            }
          } catch {
            showMessage('error', t('resources:repos.failedToDeployTo', { machine: targetMachine }))
          }
        }

        functionModal.close()
        setSelectedRepo(null)

        if (createdTaskIds.length > 0) {
          // Show summary message
          if (createdTaskIds.length === machinesArray.length) {
            // All succeeded
            showMessage('success', t('resources:repos.deploymentQueued', { count: createdTaskIds.length }))
          } else {
            // Some succeeded, some failed
            showMessage('warning', t('resources:repos.deploymentPartialSuccess', {
              success: createdTaskIds.length,
              total: machinesArray.length
            }))
          }
          if (onQueueItemCreated && createdTaskIds[0]) {
            onQueueItemCreated(createdTaskIds[0], machine.machineName)
          }
        } else {
          // All failed
          showMessage('error', t('resources:repos.allDeploymentsFailed'))
        }
        return
      }

      // Handle backup function (multiple storages)
      if (functionData.function.name === 'backup' && functionData.params.storages) {
        // Use core validation to check if backup to storage is allowed
        const backupValidation = canBackupToStorage(RepoData)
        if (!backupValidation.canBackup) {
          showMessage('error', t('resources:repos.cannotBackupForkToStorage'))
          functionModal.close()
          setSelectedRepo(null)
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
              showMessage('error', t('resources:repos.destinationStorageNotFound', { storage: targetStorage }))
              continue
            }

            // Build queue vault for this specific storage
            const backupParams = {
              ...functionData.params,
              // Convert storages array to comma-separated string for bash script
              storages: storagesArray.join(','),
              to: targetStorage,
              dest: RepoData.repoGuid,
              repo: RepoData.repoGuid,
              grand: RepoData.grandGuid || RepoData.repoGuid || '',
              state: selectedRepo.mounted ? 'online' : 'offline'
            }

            const result = await executeAction({
              teamName: machine.teamName,
              machineName: machine.machineName,
              bridgeName: machine.bridgeName,
              functionName: 'backup',
              params: backupParams,
              priority: functionData.priority,
              addedVia: 'machine-Repo-list',
              machineVault: machine.vaultContent || '{}',
              destinationStorageVault: destinationStorage.vaultContent || '{}',
              repoGuid,
              repoVault,
              repoNetworkId: RepoData.repoNetworkId,
              repoNetworkMode: RepoData.repoNetworkMode,
              repoTag: RepoData.repoTag
            })

            if (result.success && result.taskId) {
              createdTaskIds.push(result.taskId)
            }
          } catch {
            showMessage('error', t('resources:repos.failedToBackupTo', { storage: targetStorage }))
          }
        }

        functionModal.close()
        setSelectedRepo(null)

        if (createdTaskIds.length > 0) {
          // Show summary message
          if (createdTaskIds.length === storagesArray.length) {
            // All succeeded
            showMessage('success', t('resources:repos.backupQueued', { count: createdTaskIds.length }))
          } else {
            // Some succeeded, some failed
            showMessage('warning', t('resources:repos.backupPartialSuccess', {
              success: createdTaskIds.length,
              total: storagesArray.length
            }))
          }
          if (onQueueItemCreated && createdTaskIds[0]) {
            onQueueItemCreated(createdTaskIds[0], machine.machineName)
          }
        } else {
          // All failed
          showMessage('error', t('resources:repos.allBackupsFailed'))
        }
        return
      }

      // Handle pull function
      if (functionData.function.name === 'pull') {
        // For pull function, set the repo and grand parameters
        finalParams.repo = RepoData.repoGuid
        finalParams.grand = RepoData.grandGuid || RepoData.repoGuid || ''
      }

      // Build queue vault
      const result = await executeAction({
        teamName: machine.teamName,
        machineName: machine.machineName,
        bridgeName: machine.bridgeName,
        functionName: functionData.function.name,
        params: finalParams,
        priority: functionData.priority,
        addedVia: 'machine-Repo-list',
        machineVault: machine.vaultContent || '{}',
        repoGuid,
        repoVault,
        repoNetworkId: RepoData.repoNetworkId,
        repoNetworkMode: RepoData.repoNetworkMode,
        repoTag: RepoData.repoTag
      })

      functionModal.close()
      setSelectedRepo(null)

      if (result.success) {
        if (result.taskId) {
          showMessage('success', t('resources:repos.queueItemCreated'))
          if (onQueueItemCreated) {
            onQueueItemCreated(result.taskId, machine.machineName)
          }
        } else if (result.isQueued) {
          // Item was queued for highest priority management
          showMessage('info', t('resources:repos.highestPriorityQueued'))
        }
      } else {
        throw new Error(result.error || t('resources:repos.failedToCreateQueueItem'))
      }
    } catch (error) {
      // Show more specific error message if available
      const errorMessage = error instanceof Error ? error.message : t('resources:repos.failedToCreateQueueItem')
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
    title: t('resources:repos.containerStatus'),
    dataIndex: 'state',
    key: 'state',
    statusMap: {
      running: { color: 'success', label: t('resources:containers.containerStatusRunning'), icon: <PlayCircleOutlined /> },
      paused: { color: 'warning', label: t('resources:containers.containerStatusPaused'), icon: <PauseCircleOutlined /> },
      restarting: { color: 'blue', label: t('resources:containers.containerStatusRestarting'), icon: <ReloadOutlined /> },
      stopped: { color: 'default', label: t('resources:containers.containerStatusStopped'), icon: <StopOutlined /> },
    },
    defaultConfig: { color: 'default', label: t('resources:containers.containerStatusStopped'), icon: <StopOutlined /> },
  })

  const systemNameColumn = createTruncatedColumn<Container>({
    title: t('resources:repos.containerName'),
    dataIndex: 'name',
    key: 'name',
    sorter: createSorter<Container>('name'),
  })

  const systemImageColumn = createTruncatedColumn<Container>({
    title: t('resources:repos.containerImage'),
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
      render: (state: string, record: Container, index) =>
        systemStatusColumn.render?.(
          state === 'exited' ? 'stopped' : state,
          record,
          index
        ) as React.ReactNode,
    },
    {
      ...systemNameColumn,
      render: (name: string, record: Container, index) => (
        <Space>
          <CloudServerOutlined style={{ color: '#722ed1' }} />
          <strong>{systemNameColumn.render?.(name, record, index) as React.ReactNode}</strong>
        </Space>
      ),
    },
    systemImageColumn,
    {
      ...systemStateColumn,
      render: (state: string, record: Container, index) => (
        <Space>
          {systemStateColumn.render?.(
            state === 'exited' ? 'stopped' : state,
            record,
            index
          ) as React.ReactNode}
          {record.status && <Text type="secondary" style={{ fontSize: 12 }}>{record.status}</Text>}
        </Space>
      ),
    },
    {
      title: t('resources:repos.containerCPU'),
      dataIndex: 'cpu_percent',
      key: 'cpu_percent',
      sorter: createSorter<Container>('cpu_percent'),
      render: (cpu: string) => cpu || '-',
    },
    {
      title: t('resources:repos.containerMemory'),
      dataIndex: 'memory_usage',
      key: 'memory_usage',
      sorter: createSorter<Container>('memory_usage'),
      render: (memory: string) => memory || '-',
    },
    {
      title: t('resources:repos.containerPorts'),
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
                      {mapping.host}:{mapping.host_port} â†’ {mapping.container_port}/{mapping.protocol}
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

  // Transform GroupedRepo[] into flat table data with hierarchy markers
  const getTableDataSource = (): RepoTableRow[] => {
    const tableData: RepoTableRow[] = []

    groupedRepos.forEach((group) => {
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
        } as RepoTableRow)

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
            } as RepoTableRow)
          }

          // Then fork tags
          group.forkTags.forEach((fork, forkIndex) => {
            tableData.push({
              ...fork,
              _isTagRow: true,
              _indentLevel: 1,
              _isLastInGroup: forkIndex === group.forkTags.length - 1,
              key: `tag-${fork.name}-${fork.repoTag || 'latest'}`
            } as RepoTableRow)
          })
        }
      } else {
        // Single tag - show directly without grouping
        const singleTag = group.tags[0]
        tableData.push({
          ...singleTag,
          key: `single-${singleTag.name}-${singleTag.repoTag || 'latest'}`
        } as RepoTableRow)
      }
    })

    return tableData
  }

  const RepoStatusColumn = createStatusColumn<RepoTableRow>({
    title: t('resources:repos.status'),
    dataIndex: 'status',
    key: 'status',
    width: 80,
    statusMap: {
      'mounted-running': { color: 'success', label: t('resources:repos.statusMountedRunning'), icon: <CheckCircleOutlined /> },
      mounted: { color: 'warning', label: t('resources:repos.statusMountedNotRunning'), icon: <ClockCircleOutlined /> },
      unmounted: { color: 'default', label: t('resources:repos.statusUnmounted'), icon: <DisconnectOutlined /> },
    },
    defaultConfig: { color: 'default', label: t('resources:repos.statusUnmounted'), icon: <DisconnectOutlined /> },
  })

  const columns: ColumnsType<RepoTableRow> = [
    {
      ...RepoStatusColumn,
      align: 'center',
      sorter: createCustomSorter<RepoTableRow>((r) => {
        if (r._isGroupHeader) return -1
        if (r.mounted && r.docker_running) return 0
        if (r.mounted) return 1
        return 2
      }),
      render: (_: unknown, record: RepoTableRow, index) => {
        if (record._isGroupHeader) {
          return null
        }
        const statusKey = record.mounted && record.docker_running
          ? 'mounted-running'
          : record.mounted
            ? 'mounted'
            : 'unmounted'
        return RepoStatusColumn.render?.(statusKey, record, index) as React.ReactNode
      },
    },
    {
      title: t('resources:repos.repoName'),
      dataIndex: 'name',
      key: 'name',
      ellipsis: true,
      render: (_name: string, record: RepoTableRow) => {
        const isGroupHeader = record._isGroupHeader
        const groupData = record._groupData
        const isTagRow = record._isTagRow
        const indentLevel = record._indentLevel || 0

        if (isGroupHeader && groupData) {
          // Render group header (Repo name with expand/collapse)
          return (
            <Space style={{ paddingLeft: `${indentLevel * 20}px` }}>
              <span
                onClick={(e) => {
                  e.stopPropagation()
                  toggleRepoGroup(groupData.name)
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
          const tagData = teamRepos.find(r =>
            r.repoName === record.name &&
            r.repoTag === record.repoTag
          )
          const isGrand = tagData && coreIsCredential(tagData)
          const treeConnector = record._isLastInGroup ? 'â””â”€' : 'â”œâ”€'

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
          // Regular single Repo row (no grouping)
          // Look up Repo data to determine if it's a clone or original
          const RepoData = teamRepos.find(r =>
            r.repoName === record.name &&
            r.repoTag === record.repoTag
          )
          const isOriginal = RepoData && coreIsCredential(RepoData)

          return (
            <Space>
              {isOriginal ? <StarOutlined /> : <CopyOutlined />}
              <strong>{getRepoDisplayName(record)}</strong>
            </Space>
          )
        }
      },
    },
    createActionColumn<RepoTableRow>({
      title: t('common:table.actions'),
      width: DESIGN_TOKENS.DIMENSIONS.CARD_WIDTH,
      fixed: 'right',
      renderActions: (record) => {
        const groupData = record._groupData

        if (record._isGroupHeader && groupData) {
          const target = groupData.grandTag
          if (!target) {
            return null
          }

          const actionRecord: RepoTableRow = {
            ...record,
            actionId: groupData.name,
          }

          const menuItems: MenuProps['items'] = [
            {
              key: 'view-containers',
              label: t('machines:viewContainers'),
              icon: <RightOutlined />,
              onClick: () =>
                navigate(`/machines/${machine.machineName}/repos/${groupData.name}/containers`, {
                  state: { machine, Repo: target },
                }),
            },
            {
              key: 'expand-collapse',
              label: groupData.isExpanded ? 'Collapse Tags' : 'Expand Tags',
              icon: groupData.isExpanded ? <CaretRightOutlined /> : <CaretDownOutlined />,
              onClick: () => toggleRepoGroup(groupData.name),
            },
            { type: 'divider' as const },
            {
              key: 'fork-grand',
              label: t('functions:functions.fork.name'),
              icon: <CopyOutlined />,
              onClick: () => handleForkRepo(target),
            },
            {
              key: 'deploy-grand',
              label: t('functions:functions.deploy.name'),
              icon: <CloudUploadOutlined />,
              onClick: () => handleRunFunction(target, 'deploy'),
            },
            {
              key: 'backup-grand',
              label: t('functions:functions.backup.name'),
              icon: <SaveOutlined />,
              onClick: () => handleRunFunction(target, 'backup'),
            },
          ]

          return (
            <ActionButtonGroup
              buttons={[
                {
                  type: 'view',
                  icon: <EyeOutlined />,
                  tooltip: 'common:viewDetails',
                  variant: 'default',
                  onClick: () => onRepoClick?.(target),
                  testId: () => `machine-repo-view-details-group-${groupData.name}`,
                },
                {
                  type: 'remote',
                  icon: <FunctionOutlined />,
                  tooltip: 'machines:remote',
                  variant: 'primary',
                  dropdownItems: menuItems,
                  loading: isExecuting,
                  testId: () => `machine-repo-list-group-actions-${groupData.name}`,
                },
              ]}
              record={actionRecord}
              idField="actionId"
              t={t}
            />
          )
        }

        const RepoData = teamRepos.find(
          (r) => r.repoName === record.name && r.repoTag === record.repoTag
        )

        const menuItems: MenuProps['items'] = []

        menuItems.push({
          key: 'up',
          label: t('functions:functions.up.name'),
          icon: <PlayCircleOutlined />,
          onClick: (info: MenuInfo) => {
            info.domEvent.stopPropagation()
            handleQuickAction(record, 'up', 4, 'mount')
          },
        })

        if (record.mounted) {
          menuItems.push({
            key: 'down',
            label: t('functions:functions.down.name'),
            icon: <PauseCircleOutlined />,
            onClick: (info: MenuInfo) => {
              info.domEvent.stopPropagation()
              handleQuickAction(record, 'down', 4, 'unmount')
            },
          })
        }

        if (!record.mounted) {
          menuItems.push({
            key: 'validate',
            label: t('functions:functions.validate.name'),
            icon: <CheckCircleOutlined />,
            onClick: (info: MenuInfo) => {
              info.domEvent.stopPropagation()
              handleRunFunction(record, 'validate')
            },
          })
        }

        menuItems.push({
          key: 'fork',
          label: t('functions:functions.fork.name'),
          icon: <CopyOutlined />,
          onClick: (info: MenuInfo) => {
            info.domEvent.stopPropagation()
            handleForkRepo(record)
          },
        })

        menuItems.push({
          key: 'deploy',
          label: t('functions:functions.deploy.name'),
          icon: <CloudUploadOutlined />,
          onClick: (info: MenuInfo) => {
            info.domEvent.stopPropagation()
            handleRunFunction(record, 'deploy')
          },
        })

        const repoIsFork = RepoData ? coreIsFork(RepoData) : false
        menuItems.push({
          key: 'backup',
          label: t('functions:functions.backup.name'),
          icon: <SaveOutlined />,
          onClick: (info: MenuInfo) => {
            info.domEvent.stopPropagation()
            handleRunFunction(record, 'backup')
          },
          disabled: repoIsFork,
          title: repoIsFork ? t('resources:repos.backupForkDisabledTooltip') : undefined,
        })

        menuItems.push({
          key: 'apply_template',
          label: t('functions:functions.apply_template.name'),
          icon: <AppstoreOutlined />,
          onClick: (info: MenuInfo) => {
            info.domEvent.stopPropagation()
            handleRunFunction(record, 'apply_template')
          },
        })

        const advancedSubmenuItems: MenuProps['items'] = []

        if (!record.mounted) {
          advancedSubmenuItems.push({
            key: 'mount',
            label: t('resources:repos.mount'),
            icon: <DatabaseOutlined />,
            onClick: (info: MenuInfo) => {
              info.domEvent.stopPropagation()
              handleQuickAction(record, 'mount', 4)
            },
          })
        } else {
          advancedSubmenuItems.push({
            key: 'unmount',
            label: t('resources:repos.unmount'),
            icon: <DisconnectOutlined />,
            onClick: (info: MenuInfo) => {
              info.domEvent.stopPropagation()
              handleQuickAction(record, 'unmount', 4)
            },
          })
        }

        if (!record.mounted) {
          advancedSubmenuItems.push({
            key: 'resize',
            label: t('functions:functions.resize.name'),
            icon: <ShrinkOutlined />,
            onClick: (info: MenuInfo) => {
              info.domEvent.stopPropagation()
              handleRunFunction(record, 'resize')
            },
          })
        }

        if (record.mounted) {
          advancedSubmenuItems.push({
            key: 'expand',
            label: t('functions:functions.expand.name'),
            icon: <ExpandOutlined />,
            onClick: (info: MenuInfo) => {
              info.domEvent.stopPropagation()
              handleRunFunction(record, 'expand')
            },
          })
        }

        if (advancedSubmenuItems.length > 0) {
          advancedSubmenuItems.push({ type: 'divider' as const })
        }

        advancedSubmenuItems.push({
          key: 'experimental',
          label: t('machines:experimental'),
          icon: <FunctionOutlined />,
          onClick: (info: MenuInfo) => {
            info.domEvent.stopPropagation()
            handleRunFunction(record)
          },
        })

        if (advancedSubmenuItems.length > 0) {
          menuItems.push({
            key: 'advanced',
            label: t('resources:repos.advanced'),
            icon: <ControlOutlined />,
            children: advancedSubmenuItems,
          })
        }

        if (RepoData && coreIsFork(RepoData)) {
          menuItems.push({
            key: 'promote-to-grand',
            label: t('resources:repos.promoteToGrand'),
            icon: <RiseOutlined />,
            onClick: (info: MenuInfo) => {
              info.domEvent.stopPropagation()
              handlePromoteToGrand(record)
            },
          })
          menuItems.push({
            key: 'delete-fork',
            label: t('resources:repos.deleteFork'),
            icon: <DeleteOutlined />,
            onClick: (info: MenuInfo) => {
              info.domEvent.stopPropagation()
              handleDeleteFork(record)
            },
            danger: true,
          })
        }

        if (menuItems.length > 0) {
          menuItems.push({ type: 'divider' as const })
        }

        menuItems.push({
          key: 'rename',
          label: t('resources:repos.rename'),
          icon: <EditOutlined />,
          onClick: (info: MenuInfo) => {
            info.domEvent.stopPropagation()
            handleRenameRepo(record)
          },
        })

        if (RepoData && coreIsCredential(RepoData)) {
          menuItems.push({
            key: 'delete-grand',
            label: t('resources:repos.deleteGrand'),
            icon: <DeleteOutlined />,
            onClick: (info: MenuInfo) => {
              info.domEvent.stopPropagation()
              handleDeleteGrandRepo(record)
            },
            danger: true,
          })
        }

        const actionRecord: RepoTableRow = {
          ...record,
          actionId: `${record.name}-${record.repoTag || 'latest'}`,
        }

        return (
          <ActionButtonGroup
            buttons={[
              {
                type: 'view',
                icon: <EyeOutlined />,
                tooltip: 'common:viewDetails',
                variant: 'default',
                onClick: (row) => onRepoClick?.(row),
                testId: (row) => `machine-repo-view-details-${row.name}-${row.repoTag || 'latest'}`,
              },
              {
                type: 'remote',
                icon: <FunctionOutlined />,
                tooltip: 'machines:remote',
                variant: 'primary',
                dropdownItems: menuItems,
                loading: isExecuting,
                testId: (row) => `machine-repo-list-repo-actions-${row.name}`,
              },
              {
                type: 'custom',
                visible: (row) => row.mounted,
                render: (row) => (
                  <LocalActionsMenu
                    machine={machine.machineName}
                    repo={row.name}
                    teamName={machine.teamName}
                    userEmail={userEmail}
                    pluginContainers={(containersData[row.name]?.containers || []).map((container) => ({
                      ...container,
                      name: container.name ?? '',
                      image: container.image ?? '',
                      status: container.status ?? container.state ?? '',
                    }))}
                  />
                ),
              },
              {
                type: 'vault',
                icon: <KeyOutlined />,
                tooltip: 'resources:repos.addCredential',
                onClick: (row) => onCreateRepo?.(machine, row.originalGuid || row.name),
                variant: 'default',
                visible: (row) => Boolean(row.isUnmapped && onCreateRepo),
                testId: (row) => `machine-repo-list-add-credential-${row.name}`,
              },
            ]}
            record={actionRecord}
            idField="actionId"
            t={t}
          />
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
          tip={t('resources:repos.fetchingRepos') as string}
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

      {/* Repo Table */}
      <RepoTableComponent
        columns={columns}
        dataSource={getTableDataSource()}
        rowKey={(record: RepoTableRow) => record.key || `${record.name}-${record.repoTag || 'latest'}`}
        size="small"
        pagination={false}
        scroll={{ x: 'max-content' }}
        style={tableStyles.tableContainer}
        data-testid="machine-repo-list-table"
        rowClassName={(record: RepoTableRow) => {
          // Group headers have special styling
          if (record._isGroupHeader) {
            return 'Repo-group-header'
          }

          // Apply subtle background to fork/clone rows
          if (record._isTagRow) {
            const RepoData = teamRepos.find(r =>
              r.repoName === record.name &&
              r.repoTag === record.repoTag
            )
            const isForkRow = RepoData && coreIsFork(RepoData)
            return isForkRow ? 'Repo-fork-row' : 'Repo-grand-row'
          }

          // Regular single Repo rows
          const RepoData = teamRepos.find(r =>
            r.repoName === record.name &&
            r.repoTag === record.repoTag
          )
          const isClone = RepoData && coreIsFork(RepoData)
          return isClone ? 'Repo-clone-row' : ''
        }}
        locale={{
          emptyText: t('resources:repos.noRepos')
        }}
        onRow={(record: RepoTableRow) => {
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
              // Only the eye button should trigger detail panel (via onRepoClick)
              navigate(`/machines/${machine.machineName}/repos/${record.name}/containers`, {
                state: { machine, Repo: record }
              })
            },
            style: {
              cursor: 'pointer',
              backgroundColor: highlightedRepo?.name === record.name ? 'rgba(24, 144, 255, 0.05)' : undefined,
              transition: 'background-color 0.3s ease'
            },
            onMouseEnter: (e: React.MouseEvent<HTMLElement>) => {
              e.currentTarget.style.backgroundColor = highlightedRepo?.name === record.name ? 'rgba(24, 144, 255, 0.08)' : 'rgba(0, 0, 0, 0.02)'
            },
            onMouseLeave: (e: React.MouseEvent<HTMLElement>) => {
              e.currentTarget.style.backgroundColor = highlightedRepo?.name === record.name ? 'rgba(24, 144, 255, 0.05)' : ''
            }
          }
        }}
      />
      
      {/* System Containers Section */}
        {systemContainers.length > 0 && !hideSystemInfo && (
        <S.SystemContainersWrapper data-testid="machine-repo-list-system-containers">
          <S.SystemContainersTitle as={Typography.Title} level={5} data-testid="machine-repo-list-system-containers-title">
            {t('resources:repos.systemContainers')}
          </S.SystemContainersTitle>
          <SystemTableComponent
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
          setSelectedRepo(null)
          setSelectedFunction(null)
        }}
        onSubmit={handleFunctionSubmit}
        title={t('machines:runFunction')}
        data-testid="machine-repo-list-function-modal"
        subtitle={
          selectedRepo && (
            <Space direction="vertical" size="small" style={{ width: '100%' }}>
              <Space>
                <Text>{t('resources:repos.Repo')}:</Text>
                <Tag color="#8FBC8F">{selectedRepo.name}</Tag>
                <Text>â€¢</Text>
                <Text>{t('machines:machine')}:</Text>
                <Tag color="#556b2f">{machine.machineName}</Tag>
              </Space>
              {selectedFunction === 'push' && (() => {
                const currentRepoData = teamRepos.find(r => r.repoName === selectedRepo.name && r.repoTag === selectedRepo.repoTag);
                if (currentRepoData?.parentGuid) {
                  const parentRepo = teamRepos.find(r => r.repoGuid === currentRepoData.parentGuid);
                  if (parentRepo) {
                    return (
                      <Space>
                        <Text type="secondary">Parent Repo:</Text>
                        <Tag color="blue">{parentRepo.repoName}</Tag>
                        <Text type="secondary">â†’</Text>
                        <Text type="secondary">Current:</Text>
                        <Tag color="#8FBC8F">{selectedRepo.name}</Tag>
                      </Space>
                    );
                  }
                }
                return null;
              })()}
            </Space>
          )
        }
        allowedCategories={['Repo', 'backup', 'network']}
        loading={isExecuting}
        showMachineSelection={false}
        teamName={machine.teamName}
        hiddenParams={['repo', 'grand', 'dest', 'state']}
        defaultParams={{
          repo: (() => {
            const repo = teamRepos.find(r => r.repoName === selectedRepo?.name && r.repoTag === selectedRepo?.repoTag);
            return repo?.repoGuid || '';
          })(),
          grand: teamRepos.find(r => r.repoName === selectedRepo?.name && r.repoTag === selectedRepo?.repoTag)?.grandGuid || '',
          // Auto-generate dest and state for backup and push functions
          ...((selectedFunction === 'backup' || selectedFunction === 'push') && selectedRepo ? (() => {
            // Find the current Repo data
            const currentRepoData = teamRepos.find(r => r.repoName === selectedRepo.name && r.repoTag === selectedRepo.repoTag);

            // Find the grand Repo if it exists (for forks)
            let baseRepoName = selectedRepo.name;
            if (currentRepoData?.grandGuid) {
              const grandRepo = teamRepos.find(r => r.repoGuid === currentRepoData.grandGuid);
              if (grandRepo) {
                baseRepoName = grandRepo.repoName;
              }
            }

            // Generate destination filename and state
            const state = selectedRepo.mounted ? 'online' : 'offline';
            const timestamp = new Date().toISOString().slice(0, 19).replace('T', '-').replace(/:/g, '-');
            const dest = `${baseRepoName}-${state}-${timestamp}`;

            return { dest, state };
          })() : {})
        }}
        initialParams={{}}
        preselectedFunction={selectedFunction || undefined}
        currentMachineName={machine.machineName}
        additionalContext={
          selectedFunction === 'push' && selectedRepo ? {
            sourceRepo: selectedRepo.name,
            parentRepo: (() => {
              const currentRepoData = teamRepos.find(r => r.repoName === selectedRepo.name && r.repoTag === selectedRepo.repoTag);
              if (currentRepoData?.parentGuid) {
                const parentRepo = teamRepos.find(r => r.repoGuid === currentRepoData.parentGuid);
                return parentRepo?.repoName || null;
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







