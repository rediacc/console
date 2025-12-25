/**
 * Batch processing service
 * Platform-agnostic batch operations with retry logic and progress tracking
 */

/**
 * Configuration for batch processing
 */
export interface BatchConfig {
  /** Number of items per batch (default: 50) */
  batchSize: number;
  /** Maximum concurrent batches (default: 3) */
  maxConcurrent: number;
  /** Retry configuration */
  retryConfig: RetryConfig;
}

/**
 * Configuration for retry behavior
 */
export interface RetryConfig {
  /** Maximum number of retry attempts */
  maxRetries: number;
  /** Initial delay between retries in ms */
  initialDelay: number;
  /** Maximum delay between retries in ms */
  maxDelay: number;
  /** Multiplier for exponential backoff */
  backoffMultiplier: number;
}

/**
 * Progress information for batch operations
 */
export interface BatchProgress {
  /** Total number of items */
  total: number;
  /** Number of completed items */
  completed: number;
  /** Number of failed items */
  failed: number;
  /** Percentage complete (0-100) */
  percentage: number;
  /** Current batch number (1-indexed) */
  currentBatch: number;
  /** Total number of batches */
  totalBatches: number;
}

/**
 * Result of a batch operation
 */
export interface BatchResult<T> {
  /** Successfully processed items */
  successful: T[];
  /** Failed items with error details */
  failed: { item: T; error: string }[];
  /** Total duration in milliseconds */
  duration: number;
}

/**
 * Request configuration for batch operations
 */
export interface BatchRequest<TItem, TResult = unknown> {
  /** Items to process */
  items: TItem[];
  /** Optional batch size override */
  batchSize?: number;
  /** Progress callback */
  onProgress?: (progress: BatchProgress) => void;
  /** Callback after each batch completes */
  onBatchComplete?: (batchIndex: number, results: TResult[]) => void;
}

/**
 * Default retry configuration
 */
export const DEFAULT_RETRY_CONFIG: RetryConfig = {
  maxRetries: 3,
  initialDelay: 1000,
  maxDelay: 10000,
  backoffMultiplier: 2,
};

/**
 * Default batch configuration
 */
export const DEFAULT_BATCH_CONFIG: BatchConfig = {
  batchSize: 50,
  maxConcurrent: 3,
  retryConfig: DEFAULT_RETRY_CONFIG,
};

/**
 * Platform-agnostic batch processor
 */
export class BatchProcessor<T> {
  private config: BatchConfig;

  constructor(config: Partial<BatchConfig> = {}) {
    this.config = {
      ...DEFAULT_BATCH_CONFIG,
      ...config,
      retryConfig: {
        ...DEFAULT_RETRY_CONFIG,
        ...config.retryConfig,
      },
    };
  }

  /**
   * Process items in batches with retry logic
   */
  async processBatch<TResult>(
    request: BatchRequest<T, TResult>,
    processor: (batch: T[]) => Promise<TResult[]>
  ): Promise<BatchResult<T>> {
    const startTime = Date.now();
    const batchSize = request.batchSize ?? this.config.batchSize;
    const batches = this.createBatches(request.items, batchSize);

    const successful: T[] = [];
    const failed: { item: T; error: string }[] = [];

    let completed = 0;
    const total = request.items.length;

    // Process batches with concurrency limit
    for (let i = 0; i < batches.length; i += this.config.maxConcurrent) {
      const concurrentBatches = batches.slice(i, i + this.config.maxConcurrent);

      const batchPromises = concurrentBatches.map(async (batch, batchIndex) => {
        const actualBatchIndex = i + batchIndex;

        try {
          // Execute with retry
          const results = await this.executeWithRetry(
            () => processor(batch),
            this.config.retryConfig
          );

          // Mark all items in batch as successful
          successful.push(...batch);
          completed += batch.length;

          // Report progress
          if (request.onProgress) {
            request.onProgress({
              total,
              completed,
              failed: failed.length,
              percentage: Math.round((completed / total) * 100),
              currentBatch: actualBatchIndex + 1,
              totalBatches: batches.length,
            });
          }

          // Batch complete callback
          if (request.onBatchComplete) {
            request.onBatchComplete(actualBatchIndex, results);
          }
        } catch (error) {
          // Mark all items in batch as failed
          batch.forEach((item) => {
            failed.push({
              item,
              error: error instanceof Error ? error.message : 'Unknown error',
            });
          });
          completed += batch.length;

          // Report progress even for failures
          if (request.onProgress) {
            request.onProgress({
              total,
              completed,
              failed: failed.length,
              percentage: Math.round((completed / total) * 100),
              currentBatch: actualBatchIndex + 1,
              totalBatches: batches.length,
            });
          }
        }
      });

      // Wait for concurrent batches to complete
      await Promise.all(batchPromises);
    }

    return {
      successful,
      failed,
      duration: Date.now() - startTime,
    };
  }

  /**
   * Create batches from an array
   */
  private createBatches(items: T[], batchSize: number): T[][] {
    const batches: T[][] = [];
    for (let i = 0; i < items.length; i += batchSize) {
      batches.push(items.slice(i, i + batchSize));
    }
    return batches;
  }

  /**
   * Execute a function with exponential backoff retry
   */
  private async executeWithRetry<TResult>(
    fn: () => Promise<TResult>,
    config: RetryConfig
  ): Promise<TResult> {
    let lastError: Error | undefined;
    let delay = config.initialDelay;

    for (let attempt = 0; attempt <= config.maxRetries; attempt++) {
      try {
        return await fn();
      } catch (error) {
        lastError = error instanceof Error ? error : new Error('Unknown error');

        if (attempt < config.maxRetries) {
          // Calculate next delay with exponential backoff
          await this.sleep(delay);
          delay = Math.min(delay * config.backoffMultiplier, config.maxDelay);
        }
      }
    }

    throw lastError ?? new Error('Max retries exceeded');
  }

  /**
   * Sleep helper
   */
  private sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }
}

/**
 * Utility function to process items in batches
 * Convenience wrapper around BatchProcessor
 */
export async function processBatch<T, TResult>(
  items: T[],
  processor: (batch: T[]) => Promise<TResult[]>,
  options?: {
    batchSize?: number;
    maxConcurrent?: number;
    retryConfig?: Partial<RetryConfig>;
    onProgress?: (progress: BatchProgress) => void;
  }
): Promise<BatchResult<T>> {
  const batchProcessor = new BatchProcessor<T>({
    batchSize: options?.batchSize,
    maxConcurrent: options?.maxConcurrent,
    retryConfig: options?.retryConfig as RetryConfig,
  });

  return batchProcessor.processBatch(
    {
      items,
      onProgress: options?.onProgress,
    },
    processor
  );
}
