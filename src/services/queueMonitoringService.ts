import { showTranslatedMessage } from '@/utils/messages'
import apiClient from '@/api/client'
import queueManagerService from '@/services/queueManagerService'

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

class QueueMonitoringService {
  private static instance: QueueMonitoringService
  private monitoredTasks: Map<string, MonitoredTask> = new Map()
  private intervalId: NodeJS.Timeout | null = null
  
  // Time constants
  private readonly CHECK_INTERVAL_MS = 5000 // 5 seconds for more responsive updates
  private readonly STALE_TASK_THRESHOLD_MS = 24 * 60 * 60 * 1000 // 24 hours
  private readonly STALE_PROCESSING_MINUTES = 5 // 5 minutes without progress
  private readonly MAX_RETRY_COUNT = 3 // Maximum retry attempts (aligned with API polling)
  
  private readonly STORAGE_KEY = 'queue_monitored_tasks'

  private constructor() {
    this.loadFromStorage()
    this.startMonitoring()
  }

  static getInstance(): QueueMonitoringService {
    if (!QueueMonitoringService.instance) {
      QueueMonitoringService.instance = new QueueMonitoringService()
    }
    return QueueMonitoringService.instance
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
    } catch (error) {
      console.error('Failed to load monitored tasks from storage:', error)
    }
  }

  private saveToStorage() {
    try {
      const tasks = Array.from(this.monitoredTasks.values())
      localStorage.setItem(this.STORAGE_KEY, JSON.stringify(tasks))
    } catch (error) {
      console.error('Failed to save monitored tasks to storage:', error)
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
    
    console.log(`Added task ${taskId} to monitoring with status ${currentStatus}, bridge: ${bridgeName}, priority: ${priority}`)
    
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

    console.log(`Checking ${tasksToCheck.length} tasks out of ${this.monitoredTasks.size} total monitored tasks`)

    for (const task of tasksToCheck) {
      await this.checkTask(task)
    }
  }

  private async checkTask(task: MonitoredTask) {
    console.log(`Checking task ${task.taskId} - current status: ${task.lastStatus}`)
    try {
      // Update last check time
      task.lastCheckTime = Date.now()

      // Fetch the latest status
      const response = await apiClient.get('/GetQueueItemTrace', { taskId: task.taskId })
      
      // Extract queue details from response
      const queueDetails = this.extractQueueDetails(response)

      if (!queueDetails) {
        return
      }

      const currentStatus = queueDetails.status || queueDetails.Status
      
      // Check for permanent failure flag
      if (queueDetails.permanentlyFailed) {
        // Update the queue manager service
        queueManagerService.updateTaskStatus(task.taskId, 'failed')
        
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
          console.log(`Task ${task.taskId} completed - calling updateTaskStatus`)
          // Update the queue manager service
          queueManagerService.updateTaskStatus(task.taskId, 'completed')
          
          showTranslatedMessage('success', 'queue:monitoring.completed', { 
            taskId: task.taskId, 
            teamName: task.teamName, 
            machineName: task.machineName 
          })
          this.removeTask(task.taskId)
          return // Stop processing this task
        } else if (currentStatus === 'CANCELLED') {
          // Update the queue manager service
          queueManagerService.updateTaskStatus(task.taskId, 'cancelled')
          
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
          if (this.isPermanentFailure(lastFailureReason)) {
            // Update the queue manager service
            queueManagerService.updateTaskStatus(task.taskId, 'failed')
            
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
            // Update the queue manager service
            queueManagerService.updateTaskStatus(task.taskId, 'failed')
            
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
          if (this.isPermanentFailure(lastFailureReason)) {
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
          if (this.isPermanentFailure(lastFailureReason)) {
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

    } catch (error: any) {
      console.error(`Failed to check queue task ${task.taskId}:`, error)
      
      // If we get a 404, the task might have been deleted
      if (error.response?.status === 404) {
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

  private extractQueueDetails(response: any): any {
    let queueDetails: any = null
    response.tables?.forEach((table: any) => {
      if (table.data && table.data.length > 0 && table.resultSetIndex === 1) {
        queueDetails = table.data[0]
      }
    })
    return queueDetails
  }

  private getRetryCount(queueDetails: any): number {
    return queueDetails.retryCount || queueDetails.RetryCount || 0
  }

  private getLastFailureReason(queueDetails: any): string | undefined {
    return queueDetails.lastFailureReason || queueDetails.LastFailureReason
  }

  private isPermanentFailure(failureReason: string | undefined): boolean {
    if (!failureReason) return false
    
    const permanentFailureMessages = [
      'Bridge reported failure',
      'Task permanently failed',
      'Fatal error'
    ]
    
    return permanentFailureMessages.some(msg => failureReason.includes(msg))
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
  (window as any).queueMonitoringDebug = {
    getTasks: () => Array.from(queueMonitoringService['monitoredTasks'].entries()),
    checkTask: (taskId: string) => {
      const task = queueMonitoringService['monitoredTasks'].get(taskId)
      if (task) {
        queueMonitoringService['checkTask'](task)
      } else {
        console.log('Task not found in monitoring')
      }
    }
  }
}

// Export type for use in components
export type { MonitoredTask }