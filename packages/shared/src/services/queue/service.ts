/**
 * Queue service
 * High-level queue service that combines vault building and state management
 */

import { QueueStateManager } from './state-manager';
import {
  type FunctionRequirements,
  type QueueRequestContext,
  QueueVaultBuilder,
  type QueueVaultBuilderConfig,
} from '../../queue-vault';
import type {
  ActiveTask,
  LocalQueueItem,
  LocalQueueItemData,
  QueueItemListener,
  QueueListener,
  QueueServiceConfig,
} from './types';

/**
 * Queue service
 * Provides queue vault building and state management capabilities
 */
export class QueueService {
  private readonly builder: QueueVaultBuilder;
  private readonly manager: QueueStateManager;

  constructor(config: QueueServiceConfig) {
    const builderConfig: QueueVaultBuilderConfig = {
      getApiUrl: config.getApiUrl,
      encodeBase64: config.encodeBase64,
    };

    this.builder = new QueueVaultBuilder(builderConfig);
    this.manager = new QueueStateManager({
      timer: config.timer,
      isExtensionContext: config.isExtensionContext,
      emitNotification: config.emitNotification,
      emitMonitoringEvent: config.emitMonitoringEvent,
    });
  }

  getFunctionRequirements(functionName: string): FunctionRequirements {
    return this.builder.getFunctionRequirements(functionName);
  }

  async buildQueueVault(context: QueueRequestContext): Promise<string> {
    return this.builder.buildQueueVault(context);
  }

  async addToQueue(
    data: LocalQueueItemData,
    submitFunction: LocalQueueItem['submitFunction']
  ): Promise<string> {
    return this.manager.addToQueue(data, submitFunction);
  }

  getQueue(): LocalQueueItem[] {
    return this.manager.getQueue();
  }

  getQueueStats() {
    return this.manager.getQueueStats();
  }

  subscribe(listener: QueueListener): () => void {
    return this.manager.subscribe(listener);
  }

  subscribeToQueueItem(queueId: string, listener: QueueItemListener): () => void {
    return this.manager.subscribeToQueueItem(queueId, listener);
  }

  retryItem(id: string) {
    this.manager.retryItem(id);
  }

  removeFromQueue(id: string) {
    this.manager.removeFromQueue(id);
  }

  clearCompleted() {
    this.manager.clearCompleted();
  }

  getQueuePosition(id: string): number {
    return this.manager.getQueuePosition(id);
  }

  getQueueItem(queueId: string) {
    return this.manager.getQueueItem(queueId);
  }

  updateTaskStatus(taskId: string, status: 'completed' | 'failed' | 'cancelled') {
    this.manager.updateTaskStatus(taskId, status);
  }

  getActiveTasks(): ActiveTask[] {
    return this.manager.getActiveTasks();
  }

  stopProcessing() {
    this.manager.stopProcessing();
  }
}
