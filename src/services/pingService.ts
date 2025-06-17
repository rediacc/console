import { useCallback } from 'react'
import { useQueueVaultBuilder } from '@/hooks/useQueueVaultBuilder'
import { useCreateQueueItem } from '@/api/queries/queue'
import type { Machine } from '@/types'
import { useTeams } from '@/api/queries/teams'
import { waitForQueueItemCompletion, type QueueItemCompletionResult } from './helloService'

export interface PingFunctionParams {
  teamName: string
  machineName: string
  bridgeName: string
  priority?: number
  description?: string
  addedVia?: string
  machineVault?: string
  teamVault?: string
  repositoryVault?: string
}

export interface PingFunctionResult {
  taskId?: string
  success: boolean
  error?: string
}

/**
 * Custom hook that provides a standardized way to call the ping function
 * This encapsulates the logic for building the queue vault and creating queue items
 */
export function usePingFunction() {
  const { buildQueueVault } = useQueueVaultBuilder()
  const createQueueItemMutation = useCreateQueueItem()
  const { data: teams } = useTeams()

  const executePing = useCallback(async (params: PingFunctionParams): Promise<PingFunctionResult> => {
    try {
      const teamVault = getTeamVault(params, teams)
      const queueVault = await buildPingQueueVault(params, teamVault, buildQueueVault)
      const response = await createPingQueueItem(params, queueVault, createQueueItemMutation)

      return {
        taskId: response?.taskId,
        success: !!response?.taskId
      }
    } catch (error: any) {
      return {
        success: false,
        error: error.message || 'Failed to execute ping function'
      }
    }
  }, [buildQueueVault, createQueueItemMutation, teams])

  const executePingForMachine = useCallback(async (machine: Machine, options?: {
    priority?: number
    description?: string
    addedVia?: string
  }): Promise<PingFunctionResult> => {
    return executePing({
      teamName: machine.teamName,
      machineName: machine.machineName,
      bridgeName: machine.bridgeName,
      priority: options?.priority,
      description: options?.description,
      addedVia: options?.addedVia,
      machineVault: machine.vaultContent || '{}'
    })
  }, [executePing])

  const executePingAndWait = useCallback(async (
    params: PingFunctionParams,
    timeout?: number
  ): Promise<{ 
    taskId?: string
    success: boolean
    error?: string
    completionResult?: QueueItemCompletionResult
  }> => {
    const result = await executePing(params)
    
    if (!result.success || !result.taskId) {
      return result
    }

    const completionResult = await waitForQueueItemCompletion(result.taskId, timeout)
    
    return {
      ...result,
      completionResult,
      success: completionResult.success,
      error: completionResult.success ? undefined : completionResult.message
    }
  }, [executePing])

  const executePingForMachineAndWait = useCallback(async (
    machine: Machine,
    options?: {
      priority?: number
      description?: string
      addedVia?: string
      timeout?: number
    }
  ): Promise<{
    taskId?: string
    success: boolean
    error?: string
    completionResult?: QueueItemCompletionResult
  }> => {
    return executePingAndWait({
      teamName: machine.teamName,
      machineName: machine.machineName,
      bridgeName: machine.bridgeName,
      priority: options?.priority,
      description: options?.description,
      addedVia: options?.addedVia,
      machineVault: machine.vaultContent || '{}'
    }, options?.timeout)
  }, [executePingAndWait])

  return {
    executePing,
    executePingForMachine,
    executePingAndWait,
    executePingForMachineAndWait,
    waitForQueueItemCompletion,
    isLoading: createQueueItemMutation.isPending
  }
}

// Helper functions
function getTeamVault(params: PingFunctionParams, teams: any[] | undefined): string {
  if (params.teamVault && params.teamVault !== '{}') {
    return params.teamVault
  }
  
  const teamData = teams?.find(team => team.teamName === params.teamName)
  return teamData?.vaultContent || '{}'
}

async function buildPingQueueVault(
  params: PingFunctionParams,
  teamVault: string,
  buildQueueVault: any
): Promise<string> {
  const DEFAULT_PRIORITY = 4
  const DEFAULT_DESCRIPTION = 'Ping connectivity test'
  const DEFAULT_ADDED_VIA = 'ping-service'
  const DEFAULT_VAULT = '{}'
  
  return buildQueueVault({
    teamName: params.teamName,
    machineName: params.machineName,
    bridgeName: params.bridgeName,
    functionName: 'ping',
    params: {},
    priority: params.priority || DEFAULT_PRIORITY,
    description: params.description || DEFAULT_DESCRIPTION,
    addedVia: params.addedVia || DEFAULT_ADDED_VIA,
    machineVault: params.machineVault || DEFAULT_VAULT,
    teamVault: teamVault,
    repositoryVault: params.repositoryVault || DEFAULT_VAULT
  })
}

async function createPingQueueItem(
  params: PingFunctionParams,
  queueVault: string,
  createQueueItemMutation: any
): Promise<any> {
  const DEFAULT_PRIORITY = 4
  
  return createQueueItemMutation.mutateAsync({
    teamName: params.teamName,
    machineName: params.machineName,
    bridgeName: params.bridgeName,
    queueVault,
    priority: params.priority || DEFAULT_PRIORITY
  })
}