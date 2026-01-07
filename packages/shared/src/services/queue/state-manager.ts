/**
 * Queue state manager
 * Platform-agnostic queue state management with dependency injection for timers
 */

import type {
  ActiveTask,
  LocalQueueItem,
  LocalQueueItemData,
  LocalQueueItemStatus,
  QueueItemListener,
  QueueListener,
  QueueMonitoringEvent,
  QueueNotification,
  QueueNotificationLevel,
  QueueStateManagerConfig,
  TimerProvider,
} from './types';

/**
 * Queue state manager
 * Handles local queue state, submission logic, retry handling, and listener notifications
 */
export class QueueStateManager {
  private queue: LocalQueueItem[] = [];
  private listeners: QueueListener[] = [];
  private readonly MAX_RETRIES = 3;
  private readonly SUBMISSION_DELAY = 100;
  private readonly HIGHEST_PRIORITY = 1;
  private isProcessing = false;
  private processingInterval: ReturnType<TimerProvider['setInterval']> | null = null;
  private activeTasks: Map<string, ActiveTask> = new Map();
  private taskIdToBridge: Map<string, string> = new Map();

  private readonly timer: TimerProvider;
  private readonly isExtensionContext: boolean;
  private readonly emitNotificationFn?: (notification: QueueNotification) => void;
  private readonly emitMonitoringEventFn?: (event: QueueMonitoringEvent) => void;

  constructor(config: QueueStateManagerConfig) {
    this.timer = config.timer;
    this.isExtensionContext = config.isExtensionContext ?? false;
    this.emitNotificationFn = config.emitNotification;
    this.emitMonitoringEventFn = config.emitMonitoringEvent;

    if (this.isExtensionContext) {
      this.timer.setTimeout(() => this.startProcessing(), 1200);
    } else {
      this.startProcessing();
    }
  }

  private notify(level: QueueNotificationLevel, message: string) {
    this.emitNotificationFn?.({ level, message });
  }

  private emitMonitoringEvent(event: QueueMonitoringEvent) {
    this.emitMonitoringEventFn?.(event);
  }

  private hasActivePriorityTask(bridgeName?: string, excludeItemId?: string): boolean {
    if (!bridgeName) {
      return false;
    }
    const activeTask = this.activeTasks.get(bridgeName);
    if (activeTask?.priority === this.HIGHEST_PRIORITY) {
      return true;
    }

    return this.queue.some(
      (item) =>
        item.id !== excludeItemId &&
        item.data.bridgeName === bridgeName &&
        item.data.priority === this.HIGHEST_PRIORITY &&
        ['pending', 'submitting'].includes(item.status)
    );
  }

  private cancelExistingTasks(bridgeName?: string, machineName?: string) {
    if (!bridgeName || !machineName) {
      return;
    }
    this.queue.forEach((item) => {
      if (
        item.data.bridgeName === bridgeName &&
        item.data.machineName === machineName &&
        item.status === 'pending'
      ) {
        item.status = 'cancelled';
      }
    });
  }

  private trackActiveTask(task: ActiveTask) {
    this.activeTasks.set(task.bridgeName, task);
    if (task.priority === this.HIGHEST_PRIORITY) {
      this.taskIdToBridge.set(task.taskId, task.bridgeName);
    }
  }

  private startMonitoringTask(taskId: string, data: LocalQueueItemData) {
    this.emitMonitoringEvent({
      type: 'task-start',
      taskId,
      data,
    });
  }

  async addToQueue(
    data: LocalQueueItemData,
    submitFunction: LocalQueueItem['submitFunction']
  ): Promise<string> {
    const id = this.generateQueueId();
    const queuedItem: LocalQueueItem = {
      id,
      data,
      retryCount: 0,
      status: 'pending',
      timestamp: Date.now(),
      submitFunction,
    };

    const isHighestPriority = data.priority === this.HIGHEST_PRIORITY;
    if (isHighestPriority) {
      if (this.hasActivePriorityTask(data.bridgeName)) {
        this.notify(
          'warning',
          `You already have a highest priority task running on bridge ${data.bridgeName}. Please wait for it to complete.`
        );
        throw new Error('Already have a priority 1 task on this bridge');
      }

      this.cancelExistingTasks(data.bridgeName, data.machineName);
      this.queue.push(queuedItem);
      this.notifyListeners();
      this.notify('info', `Highest priority task queued. Position: ${this.queue.length}`);
      if (!this.isProcessing) {
        this.startProcessing();
      }
      return id;
    }

    try {
      queuedItem.status = 'submitting';
      const response = await submitFunction(data);
      queuedItem.status = 'submitted';
      return (response as { taskId?: string }).taskId ?? id;
    } catch (error) {
      queuedItem.status = 'failed';
      throw error instanceof Error ? error : new Error('Failed to submit queue item');
    }
  }

  getQueue(): LocalQueueItem[] {
    return [...this.queue];
  }

  getQueueStats() {
    return {
      total: this.queue.length,
      pending: this.queue.filter((item) => item.status === 'pending').length,
      submitting: this.queue.filter((item) => item.status === 'submitting').length,
      submitted: this.queue.filter((item) => item.status === 'submitted').length,
      failed: this.queue.filter((item) => item.status === 'failed').length,
      highestPriority: this.queue.filter((item) => item.data.priority === this.HIGHEST_PRIORITY)
        .length,
    };
  }

  subscribe(listener: QueueListener): () => void {
    this.listeners.push(listener);
    listener(this.getQueue());
    return () => {
      this.listeners = this.listeners.filter((l) => l !== listener);
    };
  }

  subscribeToQueueItem(queueId: string, callback: QueueItemListener): () => void {
    const listener = (queue: LocalQueueItem[]) => {
      const item = queue.find((q) => q.id === queueId);
      callback(item);
    };
    this.listeners.push(listener);
    listener(this.queue);
    return () => {
      this.listeners = this.listeners.filter((l) => l !== listener);
    };
  }

  private notifyListeners() {
    const queue = this.getQueue();
    this.listeners.forEach((listener) => listener(queue));
  }

  private startProcessing() {
    if (this.isProcessing) return;
    this.isProcessing = true;
    this.processingInterval = this.timer.setInterval(() => {
      void this.processQueue();
    }, this.SUBMISSION_DELAY);
  }

  stopProcessing() {
    this.isProcessing = false;
    if (this.processingInterval) {
      this.timer.clearInterval(this.processingInterval);
      this.processingInterval = null;
    }
  }

  private async processQueue() {
    const pendingItem = this.queue.find((item) => item.status === 'pending');

    if (!pendingItem) {
      this.queue = this.queue.filter(
        (item) => item.status === 'pending' || item.status === 'submitting'
      );
      if (this.queue.length === 0) {
        this.stopProcessing();
      }
      this.notifyListeners();
      return;
    }

    if (
      pendingItem.data.priority === this.HIGHEST_PRIORITY &&
      this.hasActivePriorityTask(pendingItem.data.bridgeName, pendingItem.id)
    ) {
      pendingItem.status = 'cancelled';
      this.notifyListeners();
      this.notify('info', 'Task cancelled: Already have a priority 1 task on this bridge');
      return;
    }

    pendingItem.status = 'submitting';
    this.notifyListeners();

    try {
      const response = await pendingItem.submitFunction(pendingItem.data);
      const taskId = (response as { taskId?: string }).taskId;

      if (
        taskId &&
        pendingItem.data.priority === this.HIGHEST_PRIORITY &&
        pendingItem.data.bridgeName
      ) {
        pendingItem.taskId = taskId;
        const activeTask: ActiveTask = {
          bridgeName: pendingItem.data.bridgeName,
          machineName: pendingItem.data.machineName ?? '',
          taskId,
          priority: pendingItem.data.priority ?? this.HIGHEST_PRIORITY,
          status: 'pending',
          timestamp: Date.now(),
        };
        this.trackActiveTask(activeTask);
        this.startMonitoringTask(taskId, pendingItem.data);
      }

      pendingItem.status = 'submitted';
      this.notifyListeners();
      if (taskId) {
        this.notify('success', `Queue item submitted successfully (ID: ${taskId})`);
      } else {
        this.notify('success', 'Queue item submitted successfully');
      }
    } catch (error) {
      pendingItem.retryCount += 1;
      if (pendingItem.retryCount < this.MAX_RETRIES) {
        pendingItem.status = 'pending';
        this.notify(
          'warning',
          `Queue submission failed, will retry (${pendingItem.retryCount}/${this.MAX_RETRIES})`
        );
      } else {
        pendingItem.status = 'failed';
        const message = error instanceof Error ? error.message : 'Unknown error';
        this.notify(
          'error',
          `Queue submission failed after ${this.MAX_RETRIES} attempts: ${message}`
        );
      }
      this.notifyListeners();
    }
  }

  removeFromQueue(id: string) {
    this.queue = this.queue.filter((item) => item.id !== id);
    this.notifyListeners();
  }

  retryItem(id: string) {
    const item = this.queue.find((queueItem) => queueItem.id === id);
    if (item?.status === 'failed') {
      item.status = 'pending';
      item.retryCount = 0;
      this.notifyListeners();
      if (!this.isProcessing) {
        this.startProcessing();
      }
    }
  }

  clearCompleted() {
    this.queue = this.queue.filter(
      (item) => item.status === 'pending' || item.status === 'submitting'
    );
    this.notifyListeners();
  }

  getQueuePosition(id: string): number {
    const pendingItems = this.queue.filter((item) => item.status === 'pending');
    const index = pendingItems.findIndex((item) => item.id === id);
    return index === -1 ? -1 : index + 1;
  }

  getQueueItem(queueId: string): LocalQueueItem | undefined {
    return this.queue.find((item) => item.id === queueId);
  }

  updateTaskStatus(taskId: string, status: 'completed' | 'failed' | 'cancelled') {
    let bridgeCleared: string | null = null;
    const mappedBridge = this.taskIdToBridge.get(taskId);
    if (mappedBridge) {
      const activeTask = this.activeTasks.get(mappedBridge);
      if (activeTask?.taskId === taskId) {
        if (this.isTerminalStatus(status)) {
          this.activeTasks.delete(mappedBridge);
          this.taskIdToBridge.delete(taskId);
          bridgeCleared = mappedBridge;
        }
      }
    }

    if (!bridgeCleared) {
      for (const [bridgeName, task] of this.activeTasks) {
        if (task.taskId === taskId && task.priority === this.HIGHEST_PRIORITY) {
          if (this.isTerminalStatus(status)) {
            this.activeTasks.delete(bridgeName);
            this.taskIdToBridge.delete(taskId);
            bridgeCleared = bridgeName;
            break;
          }
        }
      }
    }

    if (!bridgeCleared) {
      const queueItem = this.queue.find((item) => item.taskId === taskId);
      if (queueItem?.data.priority === this.HIGHEST_PRIORITY) {
        const bridgeName = queueItem.data.bridgeName;
        if (bridgeName && this.activeTasks.has(bridgeName)) {
          const activeTask = this.activeTasks.get(bridgeName);
          if (activeTask?.taskId === taskId) {
            this.activeTasks.delete(bridgeName);
            this.taskIdToBridge.delete(taskId);
            bridgeCleared = bridgeName;
          }
        }

        if (this.isTerminalStatus(status)) {
          queueItem.status = 'submitted';
        }
      }
    }

    this.emitMonitoringEvent({
      type: 'task-status',
      taskId,
      status,
    });

    this.notifyListeners();
  }

  getActiveTasks(): ActiveTask[] {
    return Array.from(this.activeTasks.values());
  }

  private generateQueueId(): string {
    return `queue-${Date.now()}-${Math.random().toString(36).substring(2, 11)}`;
  }

  private isTerminalStatus(status: LocalQueueItemStatus): boolean {
    return status === 'completed' || status === 'failed' || status === 'cancelled';
  }
}
