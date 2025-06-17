import { useCallback } from 'react'
import { useQueueVaultBuilder } from '@/hooks/useQueueVaultBuilder'
import { useCreateQueueItem } from '@/api/queries/queue'
import type { Machine } from '@/types'
import apiClient from '@/api/client'
import { useTeams } from '@/api/queries/teams'

export interface HelloFunctionParams {
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

export interface HelloFunctionResult {
  taskId?: string
  success: boolean
  error?: string
}

export interface QueueItemCompletionResult {
  success: boolean
  message: string
  status?: string
  responseData?: any
}

/**
 * Wait for a queue item to complete by polling its status
 * @param taskId The task ID to monitor
 * @param timeout Maximum time to wait in milliseconds (default: 30 seconds)
 * @returns Completion result with success status and message
 */
const DEFAULT_TIMEOUT = 30000
const POLLING_INTERVAL = 1000
const QUEUE_DETAILS_TABLE_INDEX = 1
const RESPONSE_VAULT_TABLE_INDEX = 3

export async function waitForQueueItemCompletion(
  taskId: string, 
  timeout: number = DEFAULT_TIMEOUT
): Promise<QueueItemCompletionResult> {
  const startTime = Date.now()
  
  while (Date.now() - startTime < timeout) {
    const pollResult = await pollQueueItemStatus(taskId)
    
    if (pollResult) {
      return pollResult
    }
    
    // Wait before next poll
    await new Promise(resolve => setTimeout(resolve, POLLING_INTERVAL))
  }
  
  return createTimeoutResult()
}

async function pollQueueItemStatus(taskId: string): Promise<QueueItemCompletionResult | null> {
  try {
    const response = await apiClient.get('/GetQueueItemTrace', { taskId })
    const queueDetails = response.tables?.[QUEUE_DETAILS_TABLE_INDEX]?.data?.[0]
    
    if (!queueDetails) {
      return null
    }
    
    const status = queueDetails.status || queueDetails.Status
    
    switch (status) {
      case 'COMPLETED':
        return handleCompletedStatus(response)
      case 'FAILED':
      case 'CANCELLED':
        return handleFailedStatus(queueDetails, status)
      default:
        return null
    }
  } catch (error) {
    // Continue polling on error
    console.debug('Error polling queue item status:', error)
    return null
  }
}

function handleCompletedStatus(response: any): QueueItemCompletionResult {
  const responseVault = response.tables?.[RESPONSE_VAULT_TABLE_INDEX]?.data?.[0]
  
  if (!responseVault?.vaultContent) {
    return createSuccessResult('Hello function completed successfully', 'COMPLETED')
  }
  
  try {
    const vaultData = JSON.parse(responseVault.vaultContent)
    const isError = vaultData.result && typeof vaultData.result === 'string' && vaultData.result.includes('Error')
    
    return isError
      ? createErrorResult(vaultData.result, 'COMPLETED', vaultData)
      : createSuccessResult(
          vaultData.result || 'Hello function completed successfully',
          'COMPLETED',
          vaultData
        )
  } catch {
    return createSuccessResult('Hello function completed', 'COMPLETED')
  }
}

function handleFailedStatus(queueDetails: any, status: string): QueueItemCompletionResult {
  const failureReason = queueDetails.lastFailureReason || 
                       queueDetails.LastFailureReason || 
                       'Operation failed'
  
  return createErrorResult(failureReason, status)
}

function createSuccessResult(
  message: string, 
  status: string, 
  responseData?: any
): QueueItemCompletionResult {
  return { success: true, message, status, responseData }
}

function createErrorResult(
  message: string, 
  status: string, 
  responseData?: any
): QueueItemCompletionResult {
  return { success: false, message, status, responseData }
}

function createTimeoutResult(): QueueItemCompletionResult {
  return createErrorResult('Operation timeout - no response received', 'TIMEOUT')
}

/**
 * Custom hook that provides a standardized way to call the hello function
 * This encapsulates the logic for building the queue vault and creating queue items
 */
export function useHelloFunction() {
  const { buildQueueVault } = useQueueVaultBuilder()
  const createQueueItemMutation = useCreateQueueItem()
  const { data: teams } = useTeams()

  const executeHello = useCallback(async (params: HelloFunctionParams): Promise<HelloFunctionResult> => {
    try {
      const teamVault = getTeamVault(params, teams)
      const queueVault = await buildHelloQueueVault(params, teamVault, buildQueueVault)
      const response = await createHelloQueueItem(params, queueVault, createQueueItemMutation)

      return {
        taskId: response?.taskId,
        success: !!response?.taskId
      }
    } catch (error: any) {
      return {
        success: false,
        error: error.message || 'Failed to execute hello function'
      }
    }
  }, [buildQueueVault, createQueueItemMutation, teams])

  const executeHelloForMachine = useCallback(async (machine: Machine, options?: {
    priority?: number
    description?: string
    addedVia?: string
  }): Promise<HelloFunctionResult> => {
    return executeHello({
      teamName: machine.teamName,
      machineName: machine.machineName,
      bridgeName: machine.bridgeName,
      priority: options?.priority,
      description: options?.description,
      addedVia: options?.addedVia,
      machineVault: machine.vaultContent || '{}'
    })
  }, [executeHello])

  const executeHelloAndWait = useCallback(async (
    params: HelloFunctionParams,
    timeout?: number
  ): Promise<{ 
    taskId?: string
    success: boolean
    error?: string
    completionResult?: QueueItemCompletionResult
  }> => {
    const result = await executeHello(params)
    
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
  }, [executeHello])

  const executeHelloForMachineAndWait = useCallback(async (
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
    return executeHelloAndWait({
      teamName: machine.teamName,
      machineName: machine.machineName,
      bridgeName: machine.bridgeName,
      priority: options?.priority,
      description: options?.description,
      addedVia: options?.addedVia,
      machineVault: machine.vaultContent || '{}'
    }, options?.timeout)
  }, [executeHelloAndWait])

  return {
    executeHello,
    executeHelloForMachine,
    executeHelloAndWait,
    executeHelloForMachineAndWait,
    waitForQueueItemCompletion,
    isLoading: createQueueItemMutation.isPending
  }
}

// Helper functions
function getTeamVault(params: HelloFunctionParams, teams: any[] | undefined): string {
  if (params.teamVault && params.teamVault !== '{}') {
    return params.teamVault
  }
  
  const teamData = teams?.find(team => team.teamName === params.teamName)
  return teamData?.vaultContent || '{}'
}

async function buildHelloQueueVault(
  params: HelloFunctionParams,
  teamVault: string,
  buildQueueVault: any
): Promise<string> {
  const DEFAULT_PRIORITY = 4
  const DEFAULT_DESCRIPTION = 'Hello function call'
  const DEFAULT_ADDED_VIA = 'hello-service'
  const DEFAULT_VAULT = '{}'
  
  return buildQueueVault({
    teamName: params.teamName,
    machineName: params.machineName,
    bridgeName: params.bridgeName,
    functionName: 'hello',
    params: {},
    priority: params.priority || DEFAULT_PRIORITY,
    description: params.description || DEFAULT_DESCRIPTION,
    addedVia: params.addedVia || DEFAULT_ADDED_VIA,
    machineVault: params.machineVault || DEFAULT_VAULT,
    teamVault: teamVault,
    repositoryVault: params.repositoryVault || DEFAULT_VAULT
  })
}

async function createHelloQueueItem(
  params: HelloFunctionParams,
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

/**
 * Service class for hello function operations (if class-based approach is preferred)
 */
export class HelloService {
  static async executeHello(
    params: HelloFunctionParams,
    buildQueueVault: any,
    createQueueItem: any
  ): Promise<HelloFunctionResult> {
    try {
      const teamVault = params.teamVault || '{}'
      const queueVault = await buildHelloQueueVault(params, teamVault, buildQueueVault)
      
      const response = await createQueueItem({
        teamName: params.teamName,
        machineName: params.machineName,
        bridgeName: params.bridgeName,
        queueVault,
        priority: params.priority || 4
      })

      return {
        taskId: response?.taskId,
        success: !!response?.taskId
      }
    } catch (error: any) {
      return {
        success: false,
        error: error.message || 'Failed to execute hello function'
      }
    }
  }

  static waitForQueueItemCompletion = waitForQueueItemCompletion
}