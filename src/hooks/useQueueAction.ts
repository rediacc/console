import { useTeams } from '@/api/queries/teams'
import { useManagedQueueItem } from '@/hooks/useManagedQueueItem'
import { useQueueVaultBuilder } from '@/hooks/useQueueVaultBuilder'

/**
 * Parameters for executing a queue action
 */
export interface QueueActionParams {
  // Required: Basic action parameters
  teamName: string
  machineName: string
  bridgeName: string
  functionName: string
  params: Record<string, any>

  // Required: Metadata
  priority: number
  description: string
  addedVia: string

  // Required: Machine vault
  machineVault: string

  // Optional: Repository-specific parameters
  repositoryGuid?: string
  repositoryVault?: string
  repositoryLoopbackIp?: string
  repositoryNetworkMode?: string
  repositoryTag?: string

  // Optional: Storage-specific parameters
  storageName?: string
  storageVault?: string

  // Optional: Override team vault (if already fetched)
  teamVault?: string
}

export interface QueueActionResult {
  success: boolean
  taskId?: string
  error?: string
  isQueued?: boolean
}

/**
 * Generic hook for executing queue actions
 * Handles vault assembly and queue item creation for any function
 */
export function useQueueAction() {
  const { data: teams = [] } = useTeams()
  const { buildQueueVault } = useQueueVaultBuilder()
  const createQueueItemMutation = useManagedQueueItem()

  const executeAction = async (
    params: QueueActionParams
  ): Promise<QueueActionResult> => {
    try {
      // Get team vault if not provided
      const team = teams.find(t => t.teamName === params.teamName)
      const teamVault = params.teamVault || team?.vaultContent || '{}'

      // Build queue vault with all provided parameters
      const queueVault = await buildQueueVault({
        teamName: params.teamName,
        machineName: params.machineName,
        bridgeName: params.bridgeName,
        functionName: params.functionName,
        params: params.params,
        priority: params.priority,
        description: params.description,
        addedVia: params.addedVia,
        teamVault,
        machineVault: params.machineVault,
        // Repository parameters (if provided)
        ...(params.repositoryGuid && {
          repositoryGuid: params.repositoryGuid,
          repositoryVault: params.repositoryVault,
          repositoryLoopbackIp: params.repositoryLoopbackIp,
          repositoryNetworkMode: params.repositoryNetworkMode,
          repositoryTag: params.repositoryTag
        }),
        // Storage parameters (if provided)
        ...(params.storageName && {
          storageName: params.storageName,
          storageVault: params.storageVault
        })
      })

      // Create queue item
      const response = await createQueueItemMutation.mutateAsync({
        teamName: params.teamName,
        machineName: params.machineName,
        bridgeName: params.bridgeName,
        queueVault,
        priority: params.priority
      })

      return {
        success: true,
        taskId: response?.taskId,
        isQueued: response?.isQueued
      }
    } catch (error) {
      console.error('Failed to execute queue action:', error)
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error'
      }
    }
  }

  return {
    executeAction,
    isExecuting: createQueueItemMutation.isPending
  }
}
