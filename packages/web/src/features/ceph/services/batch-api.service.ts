/**
 * Web-specific batch API service
 * Uses shared BatchProcessor for core logic with web-specific API calls
 */

import { api } from '@/api/client';
import type { Machine } from '@/types';
import {
  BatchProcessor,
  type BatchProgress,
  type BatchResult,
  type BatchRequest,
  type RetryConfig,
  DEFAULT_RETRY_CONFIG,
} from '@rediacc/shared/services/batch';

// Re-export shared types
export type { BatchProgress, BatchResult, BatchRequest, RetryConfig };

export class BatchApiService {
  private static readonly DEFAULT_BATCH_SIZE = 50;

  /**
   * Execute API requests in batches with retry logic
   */
  static async executeBatch<TInput, TOutput>(
    request: BatchRequest<TInput, TOutput>,
    apiCall: (batch: TInput[]) => Promise<TOutput[]>,
    retryConfig: RetryConfig = DEFAULT_RETRY_CONFIG
  ): Promise<BatchResult<TInput>> {
    const processor = new BatchProcessor<TInput>({
      batchSize: request.batchSize || this.DEFAULT_BATCH_SIZE,
      maxConcurrent: 3,
      retryConfig,
    });

    return processor.processBatch(
      {
        items: request.items,
        batchSize: request.batchSize,
        onProgress: request.onProgress,
        onBatchComplete: request.onBatchComplete,
      },
      apiCall
    );
  }

  /**
   * Specialized method for batch machine operations
   * Uses web-specific API calls
   */
  static async batchMachineOperation(
    operation: 'assign' | 'remove' | 'update',
    machines: string[],
    params: {
      teamName: string;
      targetType?: 'cluster' | 'image' | 'clone';
      targetResource?: string;
    },
    onProgress?: (progress: BatchProgress) => void
  ): Promise<BatchResult<string>> {
    const apiCall = async (batch: string[]) => {
      switch (operation) {
        case 'assign':
          if (!params.targetType || !params.targetResource) {
            throw new Error('Target type and resource required for assignment');
          }

          // Map to appropriate API based on target type
          if (params.targetType === 'cluster') {
            return Promise.all(
              batch.map((machineName) =>
                api.machines.updateClusterAssignment({
                  teamName: params.teamName,
                  machineName,
                  clusterName: params.targetResource || '',
                })
              )
            );
          } else if (params.targetType === 'clone') {
            return Promise.all(
              batch.map((machineName) =>
                api.machines.updateCloneAssignment(
                  params.teamName,
                  machineName,
                  params.targetResource as string
                )
              )
            );
          }
          throw new Error(`Unsupported target type: ${params.targetType}`);

        case 'remove':
          return Promise.all(
            batch.map((machineName) =>
              api.machines.updateClusterAssignment({
                teamName: params.teamName,
                machineName,
                clusterName: '',
              })
            )
          );

        default:
          throw new Error(`Unsupported operation: ${operation}`);
      }
    };

    return this.executeBatch(
      {
        items: machines,
        batchSize: 25, // Smaller batches for machine operations
        onProgress,
      },
      apiCall
    );
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
      await new Promise((resolve) => setTimeout(resolve, 100));
      return batch.map((machine) => ({
        machineName: machine.machineName,
        isValid: !machine.cephClusterName, // Simple validation
      }));
    };

    return this.executeBatch(
      {
        items: machines,
        batchSize: 100,
        onProgress,
      },
      apiCall
    );
  }
}
