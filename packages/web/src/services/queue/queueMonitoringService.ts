import { isAxiosError } from 'axios';
import { typedApi } from '@/api/client';
import { showTranslatedMessage } from '@/utils/messages';
import { parseGetQueueItemTrace } from '@rediacc/shared/api';
import { isPermanentFailure, STALE_TASK_CONSTANTS } from '@rediacc/shared/queue';
import type { GetTeamQueueItems_ResultSet1, QueueTrace } from '@rediacc/shared/types';

interface MonitoredTask {
  taskId: string;
  teamName: string;
  machineName: string;
  bridgeName?: string; // Add bridge name for priority 1 task tracking
  priority?: number; // Add priority to identify priority 1 tasks
  lastStatus: string;
  startTime: number;
  checkInterval: number; // milliseconds
  lastCheckTime: number;
}

interface ChromeAPI {
  runtime?: {
    id?: string;
  };
}

interface QueueMonitoringDebug {
  getTasks: () => [string, MonitoredTask][];
  checkTask: (taskId: string) => void;
}

class QueueMonitoringService {
  private readonly monitoredTasks: Map<string, MonitoredTask> = new Map();
  private intervalId: NodeJS.Timeout | null = null;
  private statusHandler?: (taskId: string, status: 'completed' | 'failed' | 'cancelled') => void;

  // Time constants from core
  private readonly CHECK_INTERVAL_MS = STALE_TASK_CONSTANTS.CHECK_INTERVAL_MS;
  private readonly STALE_TASK_THRESHOLD_MS = STALE_TASK_CONSTANTS.STALE_TASK_THRESHOLD_MS;
  private readonly STALE_PROCESSING_MINUTES = STALE_TASK_CONSTANTS.STALE_PROCESSING_MINUTES;
  private readonly MAX_RETRY_COUNT = STALE_TASK_CONSTANTS.MAX_RETRY_COUNT;

  private readonly STORAGE_KEY = 'queue_monitored_tasks';

  constructor() {
    this.loadFromStorage();
    // Check if we're in a Chrome extension context to avoid message channel conflicts
    if (this.isExtensionContext()) {
      // Delay startup to avoid conflicts with extension initialization
      setTimeout(() => this.startMonitoring(), 1000);
    } else {
      this.startMonitoring();
    }
  }

  private isExtensionContext(): boolean {
    if (typeof window === 'undefined') {
      return false;
    }

    try {
      const chromeApi = (window as Window & { chrome?: ChromeAPI }).chrome;
      return chromeApi?.runtime?.id !== undefined;
    } catch {
      return false;
    }
  }

  registerStatusHandler(
    handler: (taskId: string, status: 'completed' | 'failed' | 'cancelled') => void
  ) {
    this.statusHandler = handler;
  }

  handleStatusUpdate(taskId: string, status: 'completed' | 'failed' | 'cancelled') {
    this.notifyQueue(taskId, status);
    this.removeTask(taskId);
  }

  private loadFromStorage() {
    try {
      const stored = localStorage.getItem(this.STORAGE_KEY);
      if (stored) {
        const tasks = JSON.parse(stored) as MonitoredTask[];
        tasks.forEach((task) => {
          // Only restore tasks that are less than 24 hours old
          if (Date.now() - task.startTime < this.STALE_TASK_THRESHOLD_MS) {
            this.monitoredTasks.set(task.taskId, task);
          }
        });
      }
    } catch {
      // Failed to load monitored tasks from storage
    }
  }

  private notifyQueue(taskId: string, status: 'completed' | 'failed' | 'cancelled') {
    this.statusHandler?.(taskId, status);
  }

  private saveToStorage() {
    try {
      const tasks = Array.from(this.monitoredTasks.values());
      localStorage.setItem(this.STORAGE_KEY, JSON.stringify(tasks));
    } catch {
      // Failed to save monitored tasks to storage
    }
  }

  startMonitoring() {
    if (this.intervalId) {
      clearInterval(this.intervalId);
    }

    // Initial check
    void this.checkAllTasks();

    // Set up periodic checking
    this.intervalId = setInterval(() => {
      void this.checkAllTasks();
    }, this.CHECK_INTERVAL_MS);
  }

  stopMonitoring() {
    if (this.intervalId) {
      clearInterval(this.intervalId);
      this.intervalId = null;
    }
  }

  addTask(
    taskId: string,
    teamName: string,
    machineName: string,
    currentStatus: string,
    retryCount?: number,
    lastFailureReason?: string,
    bridgeName?: string,
    priority?: number
  ) {
    const terminalStatuses = ['COMPLETED', 'CANCELLED', 'FAILED'];
    if (terminalStatuses.includes(currentStatus)) {
      return;
    }

    // Don't monitor PENDING tasks that have reached max retries
    if (
      currentStatus === 'PENDING' &&
      retryCount &&
      retryCount >= this.MAX_RETRY_COUNT &&
      lastFailureReason
    ) {
      return;
    }

    const task: MonitoredTask = {
      taskId,
      teamName,
      machineName,
      bridgeName,
      priority,
      lastStatus: currentStatus,
      startTime: Date.now(),
      checkInterval: this.CHECK_INTERVAL_MS,
      lastCheckTime: Date.now(),
    };

    this.monitoredTasks.set(taskId, task);
    this.saveToStorage();

    // Added task to monitoring with status, bridge, priority

    // Trigger an immediate check for this new task
    setTimeout(() => {
      void this.checkTask(task);
    }, 1000); // Check after 1 second to allow backend to update
  }

  removeTask(taskId: string) {
    this.monitoredTasks.delete(taskId);
    this.saveToStorage();
  }

  isTaskMonitored(taskId: string): boolean {
    return this.monitoredTasks.has(taskId);
  }

  private async checkAllTasks() {
    const now = Date.now();
    const tasksToCheck = Array.from(this.monitoredTasks.values()).filter(
      (task) => now - task.lastCheckTime >= task.checkInterval
    );

    // Checking tasks out of total monitored tasks

    for (const task of tasksToCheck) {
      await this.checkTask(task);
    }
  }

  private async fetchTaskTrace(task: MonitoredTask): Promise<QueueTrace | null> {
    if (!this.isExtensionContext()) {
      const response = await typedApi.GetQueueItemTrace({ taskId: task.taskId });
      return parseGetQueueItemTrace(response as never);
    }

    try {
      const response = (await Promise.race([
        typedApi.GetQueueItemTrace({ taskId: task.taskId }),
        new Promise((_, reject) =>
          setTimeout(() => reject(new Error('Chrome extension timeout')), 8000)
        ),
      ])) as Awaited<ReturnType<typeof typedApi.GetQueueItemTrace>>;
      return parseGetQueueItemTrace(response as never);
    } catch (extensionError: unknown) {
      if (
        extensionError instanceof Error &&
        extensionError.message === 'Chrome extension timeout'
      ) {
        return null;
      }
      throw extensionError;
    }
  }

  private handlePermanentFailure(task: MonitoredTask, lastFailureReason: string | undefined): void {
    this.notifyQueue(task.taskId, 'failed');

    const messageKey = lastFailureReason
      ? 'queue:monitoring.permanentlyFailedWithReason'
      : 'queue:monitoring.permanentlyFailed';

    showTranslatedMessage('error', messageKey, {
      taskId: task.taskId,
      reason: lastFailureReason ?? '',
      attempts: this.MAX_RETRY_COUNT,
      teamName: task.teamName,
      machineName: task.machineName,
    });
    this.removeTask(task.taskId);
  }

  private checkForPermanentFailure(
    task: MonitoredTask,
    queueDetails: GetTeamQueueItems_ResultSet1
  ): boolean {
    const lastFailureReason = this.getLastFailureReason(queueDetails);
    const retryCount = this.getRetryCount(queueDetails);

    if (isPermanentFailure(lastFailureReason)) {
      this.handlePermanentFailure(task, lastFailureReason);
      return true;
    }

    if (retryCount >= this.MAX_RETRY_COUNT && lastFailureReason) {
      this.handlePermanentFailure(task, undefined);
      return true;
    }

    return false;
  }

  private handleTerminalStatus(task: MonitoredTask, status: string): boolean {
    if (status === 'COMPLETED') {
      this.notifyQueue(task.taskId, 'completed');
      showTranslatedMessage('success', 'queue:monitoring.completed', {
        taskId: task.taskId,
        teamName: task.teamName,
        machineName: task.machineName,
      });
      this.removeTask(task.taskId);
      return true;
    }

    if (status === 'CANCELLED') {
      this.notifyQueue(task.taskId, 'cancelled');
      showTranslatedMessage('warning', 'queue:monitoring.cancelled', {
        taskId: task.taskId,
        teamName: task.teamName,
        machineName: task.machineName,
      });
      this.removeTask(task.taskId);
      return true;
    }

    return false;
  }

  private notifyStatusTransition(
    task: MonitoredTask,
    messageKey: string,
    extraParams?: Record<string, unknown>
  ): void {
    showTranslatedMessage('info', messageKey, {
      taskId: task.taskId,
      teamName: task.teamName,
      machineName: task.machineName,
      ...extraParams,
    });
  }

  private handleFailedStatus(
    task: MonitoredTask,
    queueDetails: GetTeamQueueItems_ResultSet1
  ): boolean {
    if (this.checkForPermanentFailure(task, queueDetails)) return true;

    showTranslatedMessage('warning', 'queue:monitoring.failedWaitingRetry', {
      taskId: task.taskId,
      attempt: this.getRetryCount(queueDetails),
      maxAttempts: this.MAX_RETRY_COUNT,
      teamName: task.teamName,
      machineName: task.machineName,
    });
    return false;
  }

  private processStatusChange(
    task: MonitoredTask,
    oldStatus: string,
    currentStatus: string,
    queueDetails: GetTeamQueueItems_ResultSet1
  ): boolean {
    if (currentStatus === 'CANCELLING' && oldStatus !== 'CANCELLING') {
      this.notifyStatusTransition(task, 'queue:monitoring.cancelling');
      return false;
    }
    if (currentStatus === 'FAILED') {
      return this.handleFailedStatus(task, queueDetails);
    }
    if (currentStatus === 'PROCESSING' && oldStatus !== 'PROCESSING') {
      this.notifyStatusTransition(task, 'queue:monitoring.startedProcessing');
      return false;
    }
    if (currentStatus === 'ASSIGNED' && oldStatus === 'PENDING') {
      this.notifyStatusTransition(task, 'queue:monitoring.assigned');
      return false;
    }
    if (currentStatus === 'PENDING' && oldStatus !== 'PENDING') {
      this.handlePendingRetry(task, queueDetails);
      return true;
    }
    if (currentStatus === 'PENDING') {
      return this.checkForPermanentFailure(task, queueDetails);
    }
    return false;
  }

  private handleStatusTransition(
    task: MonitoredTask,
    oldStatus: string,
    currentStatus: string,
    queueDetails: GetTeamQueueItems_ResultSet1
  ): void {
    if (this.processStatusChange(task, oldStatus, currentStatus, queueDetails)) {
      return;
    }
    this.monitoredTasks.set(task.taskId, task);
    this.saveToStorage();
  }

  private handlePendingRetry(
    task: MonitoredTask,
    queueDetails: GetTeamQueueItems_ResultSet1
  ): void {
    const retryCount = this.getRetryCount(queueDetails);
    if (retryCount === 0) return;

    if (this.checkForPermanentFailure(task, queueDetails)) return;

    showTranslatedMessage('info', 'queue:monitoring.queuedForRetry', {
      taskId: task.taskId,
      attempt: retryCount,
      maxAttempts: this.MAX_RETRY_COUNT,
      teamName: task.teamName,
      machineName: task.machineName,
    });
    this.monitoredTasks.set(task.taskId, task);
    this.saveToStorage();
  }

  private handleStaleTask(
    task: MonitoredTask,
    queueDetails: GetTeamQueueItems_ResultSet1,
    currentStatus: string
  ): void {
    if (currentStatus !== 'PROCESSING') return;
    if (!queueDetails.minutesSinceAssigned) return;
    if (queueDetails.minutesSinceAssigned <= this.STALE_PROCESSING_MINUTES) return;

    showTranslatedMessage('error', 'queue:monitoring.staleTask', {
      taskId: task.taskId,
      minutes: queueDetails.minutesSinceAssigned,
    });
    task.checkInterval = this.CHECK_INTERVAL_MS * 2;
    this.monitoredTasks.set(task.taskId, task);
    this.saveToStorage();
  }

  private processTaskCheck(task: MonitoredTask, queueDetails: GetTeamQueueItems_ResultSet1): void {
    const currentStatus = queueDetails.status;
    if (!currentStatus) return;

    if (queueDetails.permanentlyFailed) {
      this.handlePermanentFailure(task, this.getLastFailureReason(queueDetails));
      return;
    }

    if (currentStatus !== task.lastStatus) {
      const oldStatus = task.lastStatus;
      task.lastStatus = currentStatus;
      if (this.handleTerminalStatus(task, currentStatus)) return;
      this.handleStatusTransition(task, oldStatus, currentStatus, queueDetails);
    }

    this.handleStaleTask(task, queueDetails, currentStatus);
  }

  private async checkTask(task: MonitoredTask) {
    try {
      task.lastCheckTime = Date.now();
      const trace = await this.fetchTaskTrace(task);
      if (!trace) return;

      const queueDetails = this.extractQueueDetails(trace);
      if (!queueDetails) return;

      this.processTaskCheck(task, queueDetails);
    } catch (error: unknown) {
      if (isAxiosError(error) && error.response?.status === 404) {
        showTranslatedMessage('error', 'queue:monitoring.taskNotFound', {
          taskId: task.taskId,
        });
        this.removeTask(task.taskId);
      }
    }
  }

  // Get all monitored tasks
  getMonitoredTasks(): MonitoredTask[] {
    return Array.from(this.monitoredTasks.values());
  }

  private extractQueueDetails(response: QueueTrace): GetTeamQueueItems_ResultSet1 | null {
    return response.queueDetails;
  }

  private getRetryCount(queueDetails: GetTeamQueueItems_ResultSet1): number {
    return queueDetails.retryCount ?? 0;
  }

  private getLastFailureReason(queueDetails: GetTeamQueueItems_ResultSet1): string | undefined {
    return queueDetails.lastFailureReason ?? undefined;
  }

  // Clear old tasks (older than 24 hours)
  clearOldTasks() {
    const now = Date.now();
    const oldTaskIds: string[] = [];

    this.monitoredTasks.forEach((task, taskId) => {
      if (now - task.startTime > this.STALE_TASK_THRESHOLD_MS) {
        oldTaskIds.push(taskId);
      }
    });

    oldTaskIds.forEach((taskId) => this.removeTask(taskId));
  }
}

// Export singleton instance
export const queueMonitoringService = new QueueMonitoringService();

// Expose debug methods on window for debugging
if (typeof window !== 'undefined') {
  const debugWindow = window as Window & { queueMonitoringDebug?: QueueMonitoringDebug };
  debugWindow.queueMonitoringDebug = {
    getTasks: () => Array.from(queueMonitoringService['monitoredTasks'].entries()),
    checkTask: (taskId: string) => {
      const task = queueMonitoringService['monitoredTasks'].get(taskId);
      if (task) {
        void queueMonitoringService['checkTask'](task);
      } else {
        // Task not found in monitoring
      }
    },
  };
}
