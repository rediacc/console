import { showTranslatedMessage } from '@/utils/messages'
import { api } from '@/api/client'
import { isPermanentFailure, STALE_TASK_CONSTANTS } from '@rediacc/shared/queue'
import type { QueueItem, QueueTrace } from '@rediacc/shared/types'
import { isAxiosError } from 'axios'

interface MonitoredTask {
  taskId: string
  teamName: string
  machineName: string
  bridgeName?: string // Add bridge name for priority 1 task tracking
  priority?: number // Add priority to identify priority 1 tasks
  lastStatus: string
  startTime: number
  checkInterval: number // milliseconds
  lastCheckTime: number
}

interface ChromeAPI {
  runtime?: {
    id?: string
  }
}

interface QueueMonitoringDebug {
  getTasks: () => Array<[string, MonitoredTask]>
  checkTask: (taskId: string) => void
}

class QueueMonitoringService {
  private static instance: QueueMonitoringService
  private monitoredTasks: Map<string, MonitoredTask> = new Map()
  private intervalId: NodeJS.Timeout | null = null
  private statusHandler?: (taskId: string, status: 'completed' | 'failed' | 'cancelled') => void

  // Time constants from core
  private readonly CHECK_INTERVAL_MS = STALE_TASK_CONSTANTS.CHECK_INTERVAL_MS
  private readonly STALE_TASK_THRESHOLD_MS = STALE_TASK_CONSTANTS.STALE_TASK_THRESHOLD_MS
  private readonly STALE_PROCESSING_MINUTES = STALE_TASK_CONSTANTS.STALE_PROCESSING_MINUTES
  private readonly MAX_RETRY_COUNT = STALE_TASK_CONSTANTS.MAX_RETRY_COUNT

  private readonly STORAGE_KEY = 'queue_monitored_tasks'

  private constructor() {
    this.loadFromStorage()
    // Check if we're in a Chrome extension context to avoid message channel conflicts
    if (this.isExtensionContext()) {
      // Delay startup to avoid conflicts with extension initialization
      setTimeout(() => this.startMonitoring(), 1000)
    } else {
      this.startMonitoring()
    }
  }

  private isExtensionContext(): boolean {
    if (typeof window === 'undefined') {
      return false
    }

    try {
      const chromeApi = (window as Window & { chrome?: ChromeAPI }).chrome
      return chromeApi?.runtime?.id !== undefined
    } catch {
      return false
    }
  }

  static getInstance(): QueueMonitoringService {
    if (!QueueMonitoringService.instance) {
      QueueMonitoringService.instance = new QueueMonitoringService()
    }
    return QueueMonitoringService.instance
  }

  registerStatusHandler(handler: (taskId: string, status: 'completed' | 'failed' | 'cancelled') => void) {
    this.statusHandler = handler
  }

  handleStatusUpdate(taskId: string, status: 'completed' | 'failed' | 'cancelled') {
    this.notifyQueue(taskId, status)
    this.removeTask(taskId)
  }

  private loadFromStorage() {
    try {
      const stored = localStorage.getItem(this.STORAGE_KEY)
      if (stored) {
        const tasks = JSON.parse(stored) as MonitoredTask[]
        tasks.forEach(task => {
          // Only restore tasks that are less than 24 hours old
          if (Date.now() - task.startTime < this.STALE_TASK_THRESHOLD_MS) {
            this.monitoredTasks.set(task.taskId, task)
          }
        })
      }
    } catch {
      // Failed to load monitored tasks from storage
    }
  }

  private notifyQueue(taskId: string, status: 'completed' | 'failed' | 'cancelled') {
    this.statusHandler?.(taskId, status)
  }

  private saveToStorage() {
    try {
      const tasks = Array.from(this.monitoredTasks.values())
      localStorage.setItem(this.STORAGE_KEY, JSON.stringify(tasks))
    } catch {
      // Failed to save monitored tasks to storage
    }
  }

  startMonitoring() {
    if (this.intervalId) {
      clearInterval(this.intervalId)
    }

    // Initial check
    this.checkAllTasks()

    // Set up periodic checking
    this.intervalId = setInterval(() => {
      this.checkAllTasks()
    }, this.CHECK_INTERVAL_MS)
  }

  stopMonitoring() {
    if (this.intervalId) {
      clearInterval(this.intervalId)
      this.intervalId = null
    }
  }

  addTask(taskId: string, teamName: string, machineName: string, currentStatus: string, retryCount?: number, lastFailureReason?: string, bridgeName?: string, priority?: number) {
    const terminalStatuses = ['COMPLETED', 'CANCELLED', 'FAILED']
    if (terminalStatuses.includes(currentStatus)) {
      return
    }
    
    // Don't monitor PENDING tasks that have reached max retries
    if (currentStatus === 'PENDING' && retryCount && retryCount >= this.MAX_RETRY_COUNT && lastFailureReason) {
      return
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
      lastCheckTime: Date.now()
    }

    this.monitoredTasks.set(taskId, task)
    this.saveToStorage()
    
    // Added task to monitoring with status, bridge, priority
    
    // Trigger an immediate check for this new task
    setTimeout(() => {
      this.checkTask(task)
    }, 1000) // Check after 1 second to allow backend to update
  }

  removeTask(taskId: string) {
    this.monitoredTasks.delete(taskId)
    this.saveToStorage()
  }

  isTaskMonitored(taskId: string): boolean {
    return this.monitoredTasks.has(taskId)
  }

  private async checkAllTasks() {
    const now = Date.now()
    const tasksToCheck = Array.from(this.monitoredTasks.values()).filter(
      task => now - task.lastCheckTime >= task.checkInterval
    )

    // Checking tasks out of total monitored tasks

    for (const task of tasksToCheck) {
      await this.checkTask(task)
    }
  }

  private async checkTask(task: MonitoredTask) {
    // Checking task - current status
    try {
      // Update last check time
      task.lastCheckTime = Date.now()

      // Add Chrome extension protection to API calls
      let trace: QueueTrace
      if (this.isExtensionContext()) {
        // In Chrome extension context, wrap API call with additional error handling
        try {
          trace = (await Promise.race([
            api.queue.getTrace(task.taskId),
            new Promise((_, reject) => 
              setTimeout(() => reject(new Error('Chrome extension timeout')), 8000)
            )
          ])) as QueueTrace
        } catch (extensionError: unknown) {
          if (extensionError instanceof Error && extensionError.message === 'Chrome extension timeout') {
            return // Skip this check to avoid blocking
          }
          throw extensionError
        }
      } else {
        // Fetch the latest status normally
        trace = await api.queue.getTrace(task.taskId)
      }
      
      // Extract queue details from response
      const queueDetails = this.extractQueueDetails(trace)

      if (!queueDetails) {
        return
      }

    const currentStatus = queueDetails.status
      
      // Check for permanent failure flag
      if (queueDetails.permanentlyFailed) {
        this.notifyQueue(task.taskId, 'failed')
        
        const lastFailureReason = this.getLastFailureReason(queueDetails)
        if (lastFailureReason) {
          showTranslatedMessage('error', 'queue:monitoring.permanentlyFailedWithReason', { 
            taskId: task.taskId,
            reason: lastFailureReason,
            teamName: task.teamName, 
            machineName: task.machineName 
          })
        } else {
          showTranslatedMessage('error', 'queue:monitoring.permanentlyFailed', { 
            taskId: task.taskId,
            attempts: this.MAX_RETRY_COUNT,
            teamName: task.teamName, 
            machineName: task.machineName 
          })
        }
        this.removeTask(task.taskId)
        return // Stop processing this task
      }

      // Check if status has changed
      if (currentStatus !== task.lastStatus) {
        const oldStatus = task.lastStatus
        task.lastStatus = currentStatus

        // Notify user of status change
        if (currentStatus === 'COMPLETED') {
          this.notifyQueue(task.taskId, 'completed')
          
          showTranslatedMessage('success', 'queue:monitoring.completed', { 
            taskId: task.taskId, 
            teamName: task.teamName, 
            machineName: task.machineName 
          })
          this.removeTask(task.taskId)
          return // Stop processing this task
        } else if (currentStatus === 'CANCELLED') {
          this.notifyQueue(task.taskId, 'cancelled')
          
          showTranslatedMessage('warning', 'queue:monitoring.cancelled', { 
            taskId: task.taskId, 
            teamName: task.teamName, 
            machineName: task.machineName 
          })
          this.removeTask(task.taskId)
          return // Stop processing this task
        } else if (currentStatus === 'CANCELLING' && oldStatus !== 'CANCELLING') {
          showTranslatedMessage('info', 'queue:monitoring.cancelling', { 
            taskId: task.taskId, 
            teamName: task.teamName, 
            machineName: task.machineName 
          })
          // Continue monitoring until it transitions to CANCELLED
          this.monitoredTasks.set(task.taskId, task)
          this.saveToStorage()
        } else if (currentStatus === 'FAILED') {
          // Note: In the middleware, FAILED status with retryCount < 2 gets reset to PENDING immediately
          // So we might not see FAILED status for long, but handle it just in case
          const retryCount = this.getRetryCount(queueDetails)
          const lastFailureReason = this.getLastFailureReason(queueDetails)
          
          // Check for permanent failure messages
          if (isPermanentFailure(lastFailureReason)) {
          this.notifyQueue(task.taskId, 'failed')
            
            showTranslatedMessage('error', 'queue:monitoring.permanentlyFailedWithReason', { 
              taskId: task.taskId,
              reason: lastFailureReason || '',
              teamName: task.teamName, 
              machineName: task.machineName 
            })
            this.removeTask(task.taskId)
            return // Stop processing this task
          }
          
          if (retryCount >= this.MAX_RETRY_COUNT) {
            this.notifyQueue(task.taskId, 'failed')
            
            showTranslatedMessage('error', 'queue:monitoring.permanentlyFailed', { 
              taskId: task.taskId,
              attempts: this.MAX_RETRY_COUNT,
              teamName: task.teamName, 
              machineName: task.machineName 
            })
            this.removeTask(task.taskId)
            return // Stop processing this task
          } else {
            // This should be rare as middleware immediately resets to PENDING
            showTranslatedMessage('warning', 'queue:monitoring.failedWaitingRetry', { 
              taskId: task.taskId,
              attempt: retryCount,
              maxAttempts: this.MAX_RETRY_COUNT,
              teamName: task.teamName, 
              machineName: task.machineName 
            })
            // Continue monitoring as it should become PENDING soon
            this.monitoredTasks.set(task.taskId, task)
            this.saveToStorage()
          }
        } else if (currentStatus === 'PROCESSING' && oldStatus !== 'PROCESSING') {
          showTranslatedMessage('info', 'queue:monitoring.startedProcessing', { 
            taskId: task.taskId, 
            teamName: task.teamName, 
            machineName: task.machineName 
          })
          // Update the task with new status
          this.monitoredTasks.set(task.taskId, task)
          this.saveToStorage()
        } else if (currentStatus === 'ASSIGNED' && oldStatus === 'PENDING') {
          showTranslatedMessage('info', 'queue:monitoring.assigned', { 
            taskId: task.taskId, 
            teamName: task.teamName, 
            machineName: task.machineName 
          })
          // Update the task with new status
          this.monitoredTasks.set(task.taskId, task)
          this.saveToStorage()
        } else if (currentStatus === 'PENDING' && oldStatus !== 'PENDING' && this.getRetryCount(queueDetails) > 0) {
          // Task has been reset to PENDING for retry
          const retryCount = this.getRetryCount(queueDetails)
          const lastFailureReason = this.getLastFailureReason(queueDetails)
          
          // Check for permanent failure messages
          if (isPermanentFailure(lastFailureReason)) {
            showTranslatedMessage('error', 'queue:monitoring.permanentlyFailedWithReason', { 
              taskId: task.taskId,
              reason: lastFailureReason || '',
              teamName: task.teamName, 
              machineName: task.machineName 
            })
            this.removeTask(task.taskId)
            return
          }
          
          // Check if we've reached max retries
          if (retryCount >= this.MAX_RETRY_COUNT && lastFailureReason) {
            showTranslatedMessage('error', 'queue:monitoring.permanentlyFailed', { 
              taskId: task.taskId,
              attempts: this.MAX_RETRY_COUNT,
              teamName: task.teamName, 
              machineName: task.machineName 
            })
            this.removeTask(task.taskId)
            return
          }
          
          showTranslatedMessage('info', 'queue:monitoring.queuedForRetry', { 
            taskId: task.taskId,
            attempt: retryCount,
            maxAttempts: this.MAX_RETRY_COUNT,
            teamName: task.teamName, 
            machineName: task.machineName 
          })
          // Update the task with new status
          this.monitoredTasks.set(task.taskId, task)
          this.saveToStorage()
        } else if (currentStatus === 'PENDING') {
          const retryCount = this.getRetryCount(queueDetails)
          const lastFailureReason = this.getLastFailureReason(queueDetails)
          
          // Check for permanent failure messages
          if (isPermanentFailure(lastFailureReason)) {
            showTranslatedMessage('error', 'queue:monitoring.permanentlyFailedWithReason', { 
              taskId: task.taskId,
              reason: lastFailureReason || '',
              teamName: task.teamName, 
              machineName: task.machineName 
            })
            this.removeTask(task.taskId)
            return
          }
          
          // Task is stuck in PENDING with max retries - treat as permanently failed
          if (retryCount >= this.MAX_RETRY_COUNT && lastFailureReason) {
            showTranslatedMessage('error', 'queue:monitoring.permanentlyFailed', { 
              taskId: task.taskId,
              attempts: this.MAX_RETRY_COUNT,
              teamName: task.teamName, 
              machineName: task.machineName 
            })
            this.removeTask(task.taskId)
            return
          }
        }
      }

      // Check for stale tasks (no assignment update for more than 5 minutes during processing)
      if (currentStatus === 'PROCESSING' && queueDetails.minutesSinceAssigned && queueDetails.minutesSinceAssigned > this.STALE_PROCESSING_MINUTES) {
        showTranslatedMessage('error', 'queue:monitoring.staleTask', { 
          taskId: task.taskId,
          minutes: queueDetails.minutesSinceAssigned
        })
        // Continue monitoring but less frequently
        task.checkInterval = this.CHECK_INTERVAL_MS * 2 // Double the check interval for stale tasks
        this.monitoredTasks.set(task.taskId, task)
        this.saveToStorage()
      }

    } catch (error: unknown) {
      // Failed to check queue task
      
      // If we get a 404, the task might have been deleted
      if (isAxiosError(error) && error.response?.status === 404) {
        showTranslatedMessage('error', 'queue:monitoring.taskNotFound', { 
          taskId: task.taskId
        })
        this.removeTask(task.taskId)
      }
    }
  }

  // Get all monitored tasks
  getMonitoredTasks(): MonitoredTask[] {
    return Array.from(this.monitoredTasks.values())
  }

  private extractQueueDetails(response: QueueTrace): QueueItem | null {
    return response.queueDetails
  }

  private getRetryCount(queueDetails: QueueItem): number {
    return queueDetails.retryCount ?? 0
  }

  private getLastFailureReason(queueDetails: QueueItem): string | undefined {
    return queueDetails.lastFailureReason
  }

  // Clear old tasks (older than 24 hours)
  clearOldTasks() {
    const now = Date.now()
    const oldTaskIds: string[] = []

    this.monitoredTasks.forEach((task, taskId) => {
      if (now - task.startTime > this.STALE_TASK_THRESHOLD_MS) {
        oldTaskIds.push(taskId)
      }
    })

    oldTaskIds.forEach(taskId => this.removeTask(taskId))
  }
}

// Export singleton instance
export const queueMonitoringService = QueueMonitoringService.getInstance()

// Expose debug methods on window for debugging
if (typeof window !== 'undefined') {
  const debugWindow = window as Window & { queueMonitoringDebug?: QueueMonitoringDebug }
  debugWindow.queueMonitoringDebug = {
    getTasks: () => Array.from(queueMonitoringService['monitoredTasks'].entries()),
    checkTask: (taskId: string) => {
      const task = queueMonitoringService['monitoredTasks'].get(taskId)
      if (task) {
        queueMonitoringService['checkTask'](task)
      } else {
        // Task not found in monitoring
      }
    }
  }
}

// Export type for use in components
export type { MonitoredTask }
