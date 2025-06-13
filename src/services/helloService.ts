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
export async function waitForQueueItemCompletion(
  taskId: string, 
  timeout: number = 30000
): Promise<QueueItemCompletionResult> {
  const startTime = Date.now()
  
  while (Date.now() - startTime < timeout) {
    try {
      const response = await apiClient.get('/GetQueueItemTrace', { taskId })
      
      // Queue details are in the second table (index 1)
      const queueDetails = response.tables?.[1]?.data?.[0]
      
      if (queueDetails) {
        const status = queueDetails.status || queueDetails.Status
        
        if (status === 'COMPLETED') {
          // Check if there was an error in the response vault (usually in table index 3)
          const responseVault = response.tables?.[3]?.data?.[0]
          if (responseVault?.vaultContent) {
            try {
              const vaultData = JSON.parse(responseVault.vaultContent)
              if (vaultData.result && typeof vaultData.result === 'string' && vaultData.result.includes('Error')) {
                return { 
                  success: false, 
                  message: vaultData.result,
                  status: 'COMPLETED',
                  responseData: vaultData
                }
              }
              return { 
                success: true, 
                message: vaultData.result || 'Hello function completed successfully',
                status: 'COMPLETED',
                responseData: vaultData
              }
            } catch (e) {
              // If vault parsing fails, still consider it a success
              return { 
                success: true, 
                message: 'Hello function completed',
                status: 'COMPLETED'
              }
            }
          }
          return { 
            success: true, 
            message: 'Hello function completed successfully',
            status: 'COMPLETED'
          }
        } else if (status === 'FAILED' || status === 'CANCELLED') {
          const failureReason = queueDetails.lastFailureReason || queueDetails.LastFailureReason || 'Operation failed'
          return { 
            success: false, 
            message: failureReason,
            status
          }
        }
      }
    } catch (error) {
      // Continue polling on error
      console.debug('Error polling queue item status:', error)
    }
    
    // Wait 1 second before next poll
    await new Promise(resolve => setTimeout(resolve, 1000))
  }
  
  return { 
    success: false, 
    message: 'Operation timeout - no response received',
    status: 'TIMEOUT'
  }
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
      // Get team vault data if not provided
      let teamVault = params.teamVault
      if (!teamVault || teamVault === '{}') {
        // Find the team vault from the fetched data
        const teamData = teams?.find(team => team.teamName === params.teamName)
        teamVault = teamData?.vaultContent || '{}'
      }
      
      // Build the queue vault for hello function
      const queueVault = await buildQueueVault({
        teamName: params.teamName,
        machineName: params.machineName,
        bridgeName: params.bridgeName,
        functionName: 'hello',
        params: {},
        priority: params.priority || 3,
        description: params.description || 'Hello function call',
        addedVia: params.addedVia || 'hello-service',
        machineVault: params.machineVault || '{}',
        teamVault: teamVault,
        repositoryVault: params.repositoryVault || '{}'
      })

      // Create the queue item
      const response = await createQueueItemMutation.mutateAsync({
        teamName: params.teamName,
        machineName: params.machineName,
        bridgeName: params.bridgeName,
        queueVault,
        priority: params.priority || 3
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
      const queueVault = await buildQueueVault({
        teamName: params.teamName,
        machineName: params.machineName,
        bridgeName: params.bridgeName,
        functionName: 'hello',
        params: {},
        priority: params.priority || 3,
        description: params.description || 'Hello function call',
        addedVia: params.addedVia || 'hello-service',
        machineVault: params.machineVault || '{}',
        teamVault: params.teamVault || '{}',
        repositoryVault: params.repositoryVault || '{}'
      })

      const response = await createQueueItem({
        teamName: params.teamName,
        machineName: params.machineName,
        bridgeName: params.bridgeName,
        queueVault,
        priority: params.priority || 3
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