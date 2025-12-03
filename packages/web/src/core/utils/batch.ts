/**
 * Core utilities for batch operations
 * These utilities are framework-agnostic and can be used in both React and CLI
 */

/**
 * Create batches from an array of items
 * @param items - Array of items to batch
 * @param batchSize - Maximum size of each batch
 * @returns Array of batches
 */
export function createBatches<T>(items: T[], batchSize: number): T[][] {
  if (batchSize <= 0) {
    throw new Error('Batch size must be positive')
  }

  const batches: T[][] = []

  for (let i = 0; i < items.length; i += batchSize) {
    batches.push(items.slice(i, i + batchSize))
  }

  return batches
}

/**
 * Validation error for bulk operations
 */
export interface BulkValidationError {
  index: number
  item: unknown
  errors: string[]
}

/**
 * Result of bulk validation
 */
export interface BulkValidationResult<T> {
  valid: T[]
  invalid: BulkValidationError[]
  hasErrors: boolean
}

/**
 * Perform bulk validation on items
 * @param items - Array of items to validate
 * @param validator - Validation function that returns errors array
 * @returns Validation result with valid and invalid items
 */
export function performBulkValidation<T>(
  items: T[],
  validator: (item: T) => string[]
): BulkValidationResult<T> {
  const valid: T[] = []
  const invalid: BulkValidationError[] = []

  items.forEach((item, index) => {
    const errors = validator(item)
    if (errors.length > 0) {
      invalid.push({ index, item, errors })
    } else {
      valid.push(item)
    }
  })

  return {
    valid,
    invalid,
    hasErrors: invalid.length > 0
  }
}

/**
 * Batch operation result
 */
export interface BatchOperationResult<T, R> {
  successful: Array<{ item: T; result: R }>
  failed: Array<{ item: T; error: Error | string }>
  totalProcessed: number
  successCount: number
  failCount: number
}

/**
 * Execute operation on batches with concurrency control
 * @param items - Array of items to process
 * @param operation - Async operation to perform on each item
 * @param options - Options for batch processing
 * @returns Result with successful and failed items
 */
export async function executeBatchOperation<T, R>(
  items: T[],
  operation: (item: T) => Promise<R>,
  options: {
    batchSize?: number
    concurrency?: number
    onProgress?: (processed: number, total: number) => void
    stopOnError?: boolean
  } = {}
): Promise<BatchOperationResult<T, R>> {
  const {
    batchSize = 10,
    concurrency = 3,
    onProgress,
    stopOnError = false
  } = options

  const successful: Array<{ item: T; result: R }> = []
  const failed: Array<{ item: T; error: Error | string }> = []
  let processed = 0

  const batches = createBatches(items, batchSize)

  for (const batch of batches) {
    // Process batch with concurrency limit
    const chunkSize = Math.ceil(batch.length / concurrency)
    const chunks = createBatches(batch, chunkSize)

    const chunkPromises = chunks.map(async (chunk) => {
      for (const item of chunk) {
        try {
          const result = await operation(item)
          successful.push({ item, result })
        } catch (error) {
          const errorMessage = error instanceof Error ? error : String(error)
          failed.push({ item, error: errorMessage })

          if (stopOnError) {
            throw error
          }
        }

        processed++
        onProgress?.(processed, items.length)
      }
    })

    await Promise.all(chunkPromises)
  }

  return {
    successful,
    failed,
    totalProcessed: processed,
    successCount: successful.length,
    failCount: failed.length
  }
}

/**
 * Retry failed items from a batch operation
 * @param failedItems - Array of failed items from previous batch operation
 * @param operation - Operation to retry
 * @param maxRetries - Maximum number of retries per item
 * @returns Result with successful and failed items after retries
 */
export async function retryFailedItems<T, R>(
  failedItems: Array<{ item: T; error: Error | string }>,
  operation: (item: T) => Promise<R>,
  maxRetries: number = 3
): Promise<BatchOperationResult<T, R>> {
  const successful: Array<{ item: T; result: R }> = []
  const failed: Array<{ item: T; error: Error | string }> = []

  for (const { item } of failedItems) {
    let lastError: Error | string = ''
    let succeeded = false

    for (let attempt = 0; attempt < maxRetries; attempt++) {
      try {
        const result = await operation(item)
        successful.push({ item, result })
        succeeded = true
        break
      } catch (error) {
        lastError = error instanceof Error ? error : String(error)
        // Wait before retry (exponential backoff)
        await new Promise(resolve => setTimeout(resolve, Math.pow(2, attempt) * 100))
      }
    }

    if (!succeeded) {
      failed.push({ item, error: lastError })
    }
  }

  return {
    successful,
    failed,
    totalProcessed: failedItems.length,
    successCount: successful.length,
    failCount: failed.length
  }
}

/**
 * Chunk array into smaller arrays
 * @param array - Array to chunk
 * @param size - Size of each chunk
 * @returns Array of chunks
 */
export function chunk<T>(array: T[], size: number): T[][] {
  return createBatches(array, size)
}

/**
 * Flatten array of arrays
 * @param arrays - Array of arrays to flatten
 * @returns Flattened array
 */
export function flatten<T>(arrays: T[][]): T[] {
  return arrays.reduce((acc, arr) => acc.concat(arr), [])
}
