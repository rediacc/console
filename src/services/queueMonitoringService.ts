import { showMessage } from '@/utils/messages'
import apiClient from '@/api/client'

interface MonitoredTask {
  taskId: string
  teamName: string
  machineName: string
  lastStatus: string
  startTime: number
  checkInterval: number // milliseconds
  lastCheckTime: number
}

class QueueMonitoringService {
  private static instance: QueueMonitoringService
  private monitoredTasks: Map<string, MonitoredTask> = new Map()
  private intervalId: NodeJS.Timeout | null = null
  private readonly CHECK_INTERVAL = 60000 // 1 minute
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
          if (Date.now() - task.startTime < 24 * 60 * 60 * 1000) {
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
    }, this.CHECK_INTERVAL)
  }

  stopMonitoring() {
    if (this.intervalId) {
      clearInterval(this.intervalId)
      this.intervalId = null
    }
  }

  addTask(taskId: string, teamName: string, machineName: string, currentStatus: string, retryCount?: number, lastFailureReason?: string) {
    // Don't monitor completed, cancelled, or permanently failed tasks
    if (currentStatus === 'COMPLETED' || currentStatus === 'CANCELLED' || currentStatus === 'FAILED') {
      return
    }
    
    // Don't monitor PENDING tasks that have reached max retries
    if (currentStatus === 'PENDING' && retryCount && retryCount >= 2 && lastFailureReason) {
      return
    }

    const task: MonitoredTask = {
      taskId,
      teamName,
      machineName,
      lastStatus: currentStatus,
      startTime: Date.now(),
      checkInterval: this.CHECK_INTERVAL,
      lastCheckTime: Date.now()
    }

    this.monitoredTasks.set(taskId, task)
    this.saveToStorage()
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

    for (const task of tasksToCheck) {
      await this.checkTask(task)
    }
  }

  private async checkTask(task: MonitoredTask) {
    try {
      // Update last check time
      task.lastCheckTime = Date.now()

      // Fetch the latest status
      const response = await apiClient.get('/GetQueueItemTrace', { taskId: task.taskId })
      
      // Extract queue details from response
      let queueDetails: any = null
      response.tables?.forEach((table) => {
        if (table.data && table.data.length > 0 && table.resultSetIndex === 1) {
          queueDetails = table.data[0]
        }
      })

      if (!queueDetails) {
        return
      }

      const currentStatus = queueDetails.status || queueDetails.Status

      // Check if status has changed
      if (currentStatus !== task.lastStatus) {
        const oldStatus = task.lastStatus
        task.lastStatus = currentStatus

        // Notify user of status change
        if (currentStatus === 'COMPLETED') {
          showMessage('success', `Queue task ${task.taskId} completed successfully! (${task.teamName} - ${task.machineName})`)
          this.removeTask(task.taskId)
          return // Stop processing this task
        } else if (currentStatus === 'CANCELLED') {
          showMessage('warning', `Queue task ${task.taskId} was cancelled (${task.teamName} - ${task.machineName})`)
          this.removeTask(task.taskId)
          return // Stop processing this task
        } else if (currentStatus === 'FAILED') {
          // Note: In the middleware, FAILED status with retryCount < 2 gets reset to PENDING immediately
          // So we might not see FAILED status for long, but handle it just in case
          const retryCount = queueDetails.retryCount || queueDetails.RetryCount || 0
          if (retryCount >= 2) {
            showMessage('error', `Queue task ${task.taskId} permanently failed after 2 attempts (${task.teamName} - ${task.machineName})`)
            this.removeTask(task.taskId)
            return // Stop processing this task
          } else {
            // This should be rare as middleware immediately resets to PENDING
            showMessage('warning', `Queue task ${task.taskId} failed - waiting for retry (attempt ${retryCount} of 2) (${task.teamName} - ${task.machineName})`)
            // Continue monitoring as it should become PENDING soon
            this.monitoredTasks.set(task.taskId, task)
            this.saveToStorage()
          }
        } else if (currentStatus === 'PROCESSING' && oldStatus !== 'PROCESSING') {
          showMessage('info', `Queue task ${task.taskId} started processing (${task.teamName} - ${task.machineName})`)
          // Update the task with new status
          this.monitoredTasks.set(task.taskId, task)
          this.saveToStorage()
        } else if (currentStatus === 'ASSIGNED' && oldStatus === 'PENDING') {
          showMessage('info', `Queue task ${task.taskId} assigned to machine (${task.teamName} - ${task.machineName})`)
          // Update the task with new status
          this.monitoredTasks.set(task.taskId, task)
          this.saveToStorage()
        } else if (currentStatus === 'PENDING' && oldStatus !== 'PENDING' && (queueDetails.retryCount || queueDetails.RetryCount || 0) > 0) {
          // Task has been reset to PENDING for retry
          const retryCount = queueDetails.retryCount || queueDetails.RetryCount || 0
          const lastFailureReason = queueDetails.lastFailureReason || queueDetails.LastFailureReason
          
          // Check if we've reached max retries
          if (retryCount >= 2 && lastFailureReason) {
            showMessage('error', `Queue task ${task.taskId} permanently failed after 2 attempts (${task.teamName} - ${task.machineName})`)
            this.removeTask(task.taskId)
            return
          }
          
          showMessage('info', `Queue task ${task.taskId} queued for retry (attempt ${retryCount} of 2) (${task.teamName} - ${task.machineName})`)
          // Update the task with new status
          this.monitoredTasks.set(task.taskId, task)
          this.saveToStorage()
        } else if (currentStatus === 'PENDING' && (queueDetails.retryCount || queueDetails.RetryCount || 0) >= 2 && (queueDetails.lastFailureReason || queueDetails.LastFailureReason)) {
          // Task is stuck in PENDING with max retries - treat as permanently failed
          showMessage('error', `Queue task ${task.taskId} permanently failed after 3 attempts (${task.teamName} - ${task.machineName})`)
          this.removeTask(task.taskId)
          return
        }
      }

      // Check for stale tasks (no heartbeat for more than 5 minutes during processing)
      if (currentStatus === 'PROCESSING' && queueDetails.minutesSinceHeartbeat > 5) {
        showMessage('error', `Queue task ${task.taskId} appears to be stale (no heartbeat for ${queueDetails.minutesSinceHeartbeat} minutes)`)
        // Continue monitoring but less frequently
        task.checkInterval = this.CHECK_INTERVAL * 2 // Check every 2 minutes for stale tasks
        this.monitoredTasks.set(task.taskId, task)
        this.saveToStorage()
      }

    } catch (error: any) {
      console.error(`Failed to check queue task ${task.taskId}:`, error)
      
      // If we get a 404, the task might have been deleted
      if (error.response?.status === 404) {
        showMessage('error', `Queue task ${task.taskId} no longer exists`)
        this.removeTask(task.taskId)
      }
    }
  }

  // Get all monitored tasks
  getMonitoredTasks(): MonitoredTask[] {
    return Array.from(this.monitoredTasks.values())
  }

  // Clear old tasks (older than 24 hours)
  clearOldTasks() {
    const now = Date.now()
    const oldTaskIds: string[] = []

    this.monitoredTasks.forEach((task, taskId) => {
      if (now - task.startTime > 24 * 60 * 60 * 1000) {
        oldTaskIds.push(taskId)
      }
    })

    oldTaskIds.forEach(taskId => this.removeTask(taskId))
  }
}

// Export singleton instance
export const queueMonitoringService = QueueMonitoringService.getInstance()

// Export type for use in components
export type { MonitoredTask }