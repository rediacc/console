import { api } from '@/api/client'
import type { Machine } from '@/types'

export interface BatchRequest<TItem, TResult = unknown> {
  items: TItem[]
  batchSize?: number
  onProgress?: (progress: BatchProgress) => void
  onBatchComplete?: (batchIndex: number, results: TResult[]) => void
}

export interface BatchProgress {
  total: number
  completed: number
  failed: number
  percentage: number
  currentBatch: number
  totalBatches: number
}

export interface BatchResult<T> {
  successful: T[]
  failed: Array<{ item: T; error: string }>
  duration: number
}

interface RetryConfig {
  maxRetries: number
  initialDelay: number
  maxDelay: number
  backoffMultiplier: number
}

const DEFAULT_RETRY_CONFIG: RetryConfig = {
  maxRetries: 3,
  initialDelay: 1000,
  maxDelay: 10000,
  backoffMultiplier: 2
}

export class BatchApiService {
  private static readonly DEFAULT_BATCH_SIZE = 50
  private static readonly MAX_CONCURRENT_REQUESTS = 3

  /**
   * Execute API requests in batches with retry logic
   */
  static async executeBatch<TInput, TOutput>(
    request: BatchRequest<TInput, TOutput>,
    apiCall: (batch: TInput[]) => Promise<TOutput[]>,
    retryConfig: RetryConfig = DEFAULT_RETRY_CONFIG
  ): Promise<BatchResult<TInput>> {
    const startTime = Date.now()
    const batchSize = request.batchSize || this.DEFAULT_BATCH_SIZE
    const batches = this.createBatches(request.items, batchSize)
    
    const successful: TInput[] = []
    const failed: Array<{ item: TInput; error: string }> = []
    
    let completed = 0
    const total = request.items.length

    // Process batches with concurrency limit
    for (let i = 0; i < batches.length; i += this.MAX_CONCURRENT_REQUESTS) {
      const concurrentBatches = batches.slice(i, i + this.MAX_CONCURRENT_REQUESTS)
      
      const batchPromises = concurrentBatches.map(async (batch, batchIndex) => {
        const actualBatchIndex = i + batchIndex
        
        try {
          // Execute with retry
          const results = await this.executeWithRetry(
            () => apiCall(batch),
            retryConfig
          )
          
          // Mark all items in batch as successful
          successful.push(...batch)
          completed += batch.length
          
          // Report progress
          if (request.onProgress) {
            request.onProgress({
              total,
              completed,
              failed: failed.length,
              percentage: Math.round((completed / total) * 100),
              currentBatch: actualBatchIndex + 1,
              totalBatches: batches.length
            })
          }
          
          // Batch complete callback
          if (request.onBatchComplete) {
            request.onBatchComplete(actualBatchIndex, results)
          }
        } catch (error) {
          // Mark all items in batch as failed
          batch.forEach(item => {
            failed.push({
              item,
              error: error instanceof Error ? error.message : 'Unknown error'
            })
          })
          completed += batch.length
          
          // Report progress even for failures
          if (request.onProgress) {
            request.onProgress({
              total,
              completed,
              failed: failed.length,
              percentage: Math.round((completed / total) * 100),
              currentBatch: actualBatchIndex + 1,
              totalBatches: batches.length
            })
          }
        }
      })
      
      // Wait for concurrent batches to complete
      await Promise.all(batchPromises)
    }

    return {
      successful,
      failed,
      duration: Date.now() - startTime
    }
  }

  /**
   * Specialized method for batch machine operations
   */
  static async batchMachineOperation(
    operation: 'assign' | 'remove' | 'update',
    machines: string[],
    params: {
      teamName: string
      targetType?: 'cluster' | 'image' | 'clone'
      targetResource?: string
    },
    onProgress?: (progress: BatchProgress) => void
  ): Promise<BatchResult<string>> {
    const apiCall = async (batch: string[]) => {
      switch (operation) {
        case 'assign':
          if (!params.targetType || !params.targetResource) {
            throw new Error('Target type and resource required for assignment')
          }
          
          // Map to appropriate API based on target type
          if (params.targetType === 'cluster') {
            return Promise.all(
              batch.map(machineName =>
                api.machines.updateClusterAssignment(params.teamName, machineName, params.targetResource || null)
              )
            )
          } else if (params.targetType === 'clone') {
            return Promise.all(
              batch.map(machineName =>
                api.machines.updateCloneAssignment(params.teamName, machineName, params.targetResource as string)
              )
            )
          }
          throw new Error(`Unsupported target type: ${params.targetType}`)
          
        case 'remove':
          return Promise.all(
            batch.map(machineName =>
              api.machines.updateClusterAssignment(params.teamName, machineName, null)
            )
          )
          
        default:
          throw new Error(`Unsupported operation: ${operation}`)
      }
    }

    return this.executeBatch(
      {
        items: machines,
        batchSize: 25, // Smaller batches for machine operations
        onProgress
      },
      apiCall
    )
  }

  /**
   * Create batches from array
   */
  private static createBatches<T>(items: T[], batchSize: number): T[][] {
    const batches: T[][] = []
    for (let i = 0; i < items.length; i += batchSize) {
      batches.push(items.slice(i, i + batchSize))
    }
    return batches
  }

  /**
   * Execute function with exponential backoff retry
   */
  private static async executeWithRetry<T>(
    fn: () => Promise<T>,
    config: RetryConfig
  ): Promise<T> {
    let lastError: Error | undefined
    let delay = config.initialDelay

    for (let attempt = 0; attempt <= config.maxRetries; attempt++) {
      try {
        return await fn()
      } catch (error) {
        lastError = error instanceof Error ? error : new Error('Unknown error')
        
        if (attempt < config.maxRetries) {
          // Calculate next delay with exponential backoff
          await this.sleep(delay)
          delay = Math.min(delay * config.backoffMultiplier, config.maxDelay)
        }
      }
    }

    throw lastError || new Error('Max retries exceeded')
  }

  /**
   * Sleep helper
   */
  private static sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms))
  }

  /**
   * Batch validation for machines
   */
  static async batchValidateMachines(
    machines: Machine[],
    _targetType: 'cluster' | 'image' | 'clone',
    onProgress?: (progress: BatchProgress) => void
  ): Promise<BatchResult<Machine>> {
    // For validation, we can process in larger batches since it's read-only
    const apiCall = async (batch: Machine[]) => {
      // In real implementation, this would call a batch validation endpoint
      // For now, simulate validation
      await this.sleep(100) // Simulate API delay
      return batch.map(machine => ({
        machineName: machine.machineName,
        isValid: !machine.distributedStorageClusterName // Simple validation
      }))
    }

    return this.executeBatch(
      {
        items: machines,
        batchSize: 100,
        onProgress
      },
      apiCall
    )
  }
}
