import { showMessage } from '@/utils/messages'

interface QueuedItem {
  id: string
  data: {
    teamName: string
    machineName: string
    bridgeName: string
    queueVault: string
    priority?: number
  }
  retryCount: number
  status: 'pending' | 'submitting' | 'submitted' | 'failed' | 'cancelled'
  timestamp: number
  submitFunction: (data: any) => Promise<any>
  taskId?: string // Backend task ID once submitted
}

interface ActiveTask {
  bridgeName: string
  machineName: string
  taskId: string
  priority: number
  status: 'pending' | 'assigned' | 'processing'
  timestamp: number
}

class QueueManagerService {
  private queue: QueuedItem[] = []
  private activeTasks: Map<string, ActiveTask> = new Map() // key: bridgeName-machineName
  private isProcessing = false
  private processingInterval: ReturnType<typeof setInterval> | null = null
  private readonly MAX_RETRIES = 3
  private readonly SUBMISSION_DELAY = 5000 // 5 seconds between submissions
  private readonly HIGHEST_PRIORITY = 1 // Only priority 1 items are queued
  private listeners: ((queue: QueuedItem[]) => void)[] = []

  constructor() {
    // Start processing queue when service is initialized
    this.startProcessing()
    
    // Start periodic sync to ensure active tasks are up to date
    this.startPeriodicSync()
  }

  /**
   * Check if there's an active priority 1 task on a specific bridge
   */
  private hasActivePriority1Task(bridgeName: string, excludeItemId?: string): boolean {
    // Check in active tasks
    for (const [key, task] of this.activeTasks) {
      if (task.bridgeName === bridgeName && 
          task.priority === this.HIGHEST_PRIORITY &&
          ['pending', 'assigned', 'processing'].includes(task.status)) {
        console.log('Found active priority 1 task:', {
          taskId: task.taskId,
          status: task.status,
          bridgeName: task.bridgeName,
          timestamp: new Date(task.timestamp).toISOString(),
          age: Math.floor((Date.now() - task.timestamp) / 1000) + ' seconds'
        })
        return true
      }
    }

    // Check in queue (only pending and submitting items, not submitted)
    const queuedTask = this.queue.find(item => 
      item.id !== excludeItemId && // Exclude the specified item
      item.data.bridgeName === bridgeName &&
      item.data.priority === this.HIGHEST_PRIORITY &&
      ['pending', 'submitting'].includes(item.status)
    )
    
    if (queuedTask) {
      console.log('Found queued priority 1 task:', {
        id: queuedTask.id,
        status: queuedTask.status,
        bridgeName: queuedTask.data.bridgeName
      })
      return true
    }
    
    return false
  }

  /**
   * Cancel existing pending tasks for the same bridge/machine
   */
  private cancelExistingTasks(bridgeName: string, machineName: string) {
    this.queue.forEach(item => {
      if (item.data.bridgeName === bridgeName &&
          item.data.machineName === machineName &&
          item.status === 'pending') {
        item.status = 'cancelled'
        // Message will be shown by the component using this service
      }
    })
  }

  /**
   * Track an active task
   */
  private trackActiveTask(task: ActiveTask) {
    const key = `${task.bridgeName}-${task.machineName}`
    this.activeTasks.set(key, task)
    console.log(`Tracked active task: key=${key}, taskId=${task.taskId}, bridgeName=${task.bridgeName}`)
  }

  /**
   * Remove an active task
   */
  private removeActiveTask(bridgeName: string, machineName: string) {
    const key = `${bridgeName}-${machineName}`
    this.activeTasks.delete(key)
  }

  /**
   * Add a queue item to the local queue
   */
  async addToQueue(
    data: QueuedItem['data'],
    submitFunction: (data: any) => Promise<any>
  ): Promise<string> {
    const id = `queue-${Date.now()}-${Math.random().toString(36).substring(2, 11)}`

    const queuedItem: QueuedItem = {
      id,
      data,
      retryCount: 0,
      status: 'pending',
      timestamp: Date.now(),
      submitFunction
    }

    // Check if this is the highest priority item
    const isHighestPriority = data.priority === this.HIGHEST_PRIORITY

    if (isHighestPriority) {
      // Check if there's already a priority 1 task on this bridge
      if (this.hasActivePriority1Task(data.bridgeName)) {
        showMessage('warning', `You already have a highest priority task running on bridge ${data.bridgeName}. Please wait for it to complete.`)
        throw new Error('Already have a priority 1 task on this bridge')
      }

      // Cancel any existing pending tasks for this bridge/machine
      this.cancelExistingTasks(data.bridgeName, data.machineName)

      // For highest priority items, add to queue for managed submission
      this.queue.push(queuedItem)
      this.notifyListeners()
      showMessage('info', `Highest priority task queued. Position: ${this.queue.length}`)
      
      // Ensure processing is running
      if (!this.isProcessing) {
        this.startProcessing()
      }
    } else {
      // For all other priority items, submit immediately
      try {
        queuedItem.status = 'submitting'
        const response = await submitFunction(data)
        queuedItem.status = 'submitted'
        return response.taskId || id
      } catch (error: any) {
        queuedItem.status = 'failed'
        throw error
      }
    }

    return id
  }

  /**
   * Get the current queue status
   */
  getQueue(): QueuedItem[] {
    return [...this.queue]
  }

  /**
   * Get queue statistics
   */
  getQueueStats() {
    const stats = {
      total: this.queue.length,
      pending: this.queue.filter(item => item.status === 'pending').length,
      submitting: this.queue.filter(item => item.status === 'submitting').length,
      submitted: this.queue.filter(item => item.status === 'submitted').length,
      failed: this.queue.filter(item => item.status === 'failed').length,
      highestPriority: this.queue.filter(item => 
        item.data.priority === this.HIGHEST_PRIORITY
      ).length
    }
    return stats
  }

  /**
   * Subscribe to queue changes
   */
  subscribe(listener: (queue: QueuedItem[]) => void): () => void {
    this.listeners.push(listener)
    
    // Return unsubscribe function
    return () => {
      this.listeners = this.listeners.filter(l => l !== listener)
    }
  }

  /**
   * Notify all listeners of queue changes
   */
  private notifyListeners() {
    const queue = this.getQueue()
    this.listeners.forEach(listener => listener(queue))
  }

  /**
   * Start processing the queue
   */
  private startProcessing() {
    if (this.isProcessing) return

    this.isProcessing = true
    this.processingInterval = setInterval(() => {
      this.processQueue()
    }, this.SUBMISSION_DELAY)
  }

  /**
   * Stop processing the queue
   */
  stopProcessing() {
    this.isProcessing = false
    if (this.processingInterval) {
      clearInterval(this.processingInterval)
      this.processingInterval = null
    }
  }

  /**
   * Process the next item in the queue
   */
  private async processQueue() {
    // Find the next pending item (skip cancelled)
    const pendingItem = this.queue.find(item => item.status === 'pending')
    
    if (!pendingItem) {
      // Clean up old submitted/failed/cancelled items after 5 minutes
      const fiveMinutesAgo = Date.now() - 5 * 60 * 1000
      this.queue = this.queue.filter(item => 
        item.status === 'pending' || 
        item.status === 'submitting' || 
        item.timestamp > fiveMinutesAgo
      )
      
      // Also clean up old active tasks
      const twoMinutesAgo = Date.now() - 2 * 60 * 1000
      for (const [key, task] of this.activeTasks) {
        if (task.priority === 1 && task.timestamp < twoMinutesAgo) {
          this.activeTasks.delete(key)
        } else if (task.priority !== 1 && task.timestamp < fiveMinutesAgo) {
          this.activeTasks.delete(key)
        }
      }
      
      // Stop processing if queue is empty
      if (this.queue.length === 0) {
        this.stopProcessing()
      }
      
      this.notifyListeners()
      return
    }

    // Check again if there's still no priority 1 task on this bridge (exclude current item)
    if (pendingItem.data.priority === this.HIGHEST_PRIORITY && 
        this.hasActivePriority1Task(pendingItem.data.bridgeName, pendingItem.id)) {
      pendingItem.status = 'cancelled'
      this.notifyListeners()
      showMessage('info', 'Task cancelled: Already have a priority 1 task on this bridge')
      return
    }

    // Mark as submitting
    pendingItem.status = 'submitting'
    this.notifyListeners()

    try {
      // Submit the item
      const response = await pendingItem.submitFunction(pendingItem.data)
      
      // Store the task ID
      pendingItem.taskId = response.taskId || response.id
      
      // Track as active task if it's priority 1
      if (pendingItem.data.priority === this.HIGHEST_PRIORITY && 
          pendingItem.taskId) {
        const activeTask = {
          bridgeName: pendingItem.data.bridgeName,
          machineName: pendingItem.data.machineName,
          taskId: pendingItem.taskId,
          priority: pendingItem.data.priority,
          status: 'pending' as const,
          timestamp: Date.now()
        }
        this.trackActiveTask(activeTask)
        
        // Trigger a sync after a short delay to ensure monitoring catches up
        setTimeout(() => {
          this.syncActiveTasksStatus()
        }, 5000)
      }
      
      // Mark as submitted
      pendingItem.status = 'submitted'
      this.notifyListeners()
      
      showMessage('success', `Queue item submitted successfully${pendingItem.taskId ? ` (ID: ${pendingItem.taskId})` : ''}`)
    } catch (error: any) {
      pendingItem.retryCount++
      
      if (pendingItem.retryCount < this.MAX_RETRIES) {
        // Retry later
        pendingItem.status = 'pending'
        showMessage('warning', `Queue submission failed, will retry (${pendingItem.retryCount}/${this.MAX_RETRIES})`)
      } else {
        // Max retries reached
        pendingItem.status = 'failed'
        showMessage('error', `Queue submission failed after ${this.MAX_RETRIES} attempts: ${error.message}`)
      }
      
      this.notifyListeners()
    }
  }

  /**
   * Remove an item from the queue
   */
  removeFromQueue(id: string) {
    this.queue = this.queue.filter(item => item.id !== id)
    this.notifyListeners()
  }

  /**
   * Retry a failed item
   */
  retryItem(id: string) {
    const item = this.queue.find(item => item.id === id)
    if (item && item.status === 'failed') {
      item.status = 'pending'
      item.retryCount = 0
      this.notifyListeners()
      
      // Restart processing if needed
      if (!this.isProcessing) {
        this.startProcessing()
      }
    }
  }

  /**
   * Clear all completed items
   */
  clearCompleted() {
    this.queue = this.queue.filter(item => 
      item.status === 'pending' || item.status === 'submitting'
    )
    this.notifyListeners()
  }

  /**
   * Get position of an item in the queue
   */
  getQueuePosition(id: string): number {
    const pendingItems = this.queue.filter(item => item.status === 'pending')
    const index = pendingItems.findIndex(item => item.id === id)
    return index === -1 ? -1 : index + 1
  }

  /**
   * Get a queued item by its queue ID
   */
  getQueueItem(queueId: string): QueuedItem | undefined {
    return this.queue.find(item => item.id === queueId)
  }

  /**
   * Subscribe to a specific queue item's status changes
   */
  subscribeToQueueItem(queueId: string, callback: (item: QueuedItem | undefined) => void): () => void {
    const listener = (queue: QueuedItem[]) => {
      const item = queue.find(q => q.id === queueId)
      callback(item)
    }
    
    this.listeners.push(listener)
    
    // Immediately call with current state
    listener(this.queue)
    
    // Return unsubscribe function
    return () => {
      this.listeners = this.listeners.filter(l => l !== listener)
    }
  }

  /**
   * Update task status from backend
   */
  updateTaskStatus(taskId: string, status: 'completed' | 'failed' | 'cancelled') {
    console.log(`updateTaskStatus called: taskId=${taskId}, status=${status}`)
    
    // Update in queue
    const queueItem = this.queue.find(item => item.taskId === taskId)
    if (queueItem) {
      console.log('Found queue item to update:', queueItem.id)
      if (status === 'completed' || status === 'failed' || status === 'cancelled') {
        // Remove from active tasks
        this.removeActiveTask(
          queueItem.data.bridgeName,
          queueItem.data.machineName
        )
      }
    }

    // Update in active tasks
    let found = false
    for (const [key, task] of this.activeTasks) {
      if (task.taskId === taskId) {
        found = true
        console.log(`Found active task to remove: key=${key}, taskId=${taskId}`)
        if (status === 'completed' || status === 'failed' || status === 'cancelled') {
          this.activeTasks.delete(key)
          console.log(`Removed active task: ${key}`)
        } else {
          task.status = status as any
        }
        break
      }
    }
    
    if (!found) {
      console.log(`Task ${taskId} not found in active tasks`)
      // Log current active tasks
      console.log('Current active tasks:', Array.from(this.activeTasks.entries()).map(([k, v]) => ({
        key: k,
        taskId: v.taskId,
        status: v.status
      })))
    }

    this.notifyListeners()
  }

  /**
   * Get all active tasks
   */
  getActiveTasks(): ActiveTask[] {
    return Array.from(this.activeTasks.values())
  }

  /**
   * Check if a specific task can be submitted
   */
  canSubmitTask(bridgeName: string, priority: number): boolean {
    if (priority !== this.HIGHEST_PRIORITY) {
      return true // Non-priority 1 tasks can always be submitted
    }
    return !this.hasActivePriority1Task(bridgeName)
  }

  /**
   * Clear cancelled tasks
   */
  clearCancelled() {
    this.queue = this.queue.filter(item => item.status !== 'cancelled')
    this.notifyListeners()
  }

  /**
   * Clear all active tasks for a specific bridge
   */
  clearActiveTasks(bridgeName?: string) {
    if (bridgeName) {
      // Clear tasks for specific bridge
      const keysToRemove: string[] = []
      for (const [key, task] of this.activeTasks) {
        if (task.bridgeName === bridgeName) {
          keysToRemove.push(key)
        }
      }
      keysToRemove.forEach(key => this.activeTasks.delete(key))
      console.log(`Cleared ${keysToRemove.length} active tasks for bridge ${bridgeName}`)
    } else {
      // Clear all active tasks
      const count = this.activeTasks.size
      this.activeTasks.clear()
      console.log(`Cleared all ${count} active tasks`)
    }
    this.notifyListeners()
  }

  /**
   * Get debug info about active tasks
   */
  getDebugInfo() {
    return {
      activeTasks: Array.from(this.activeTasks.entries()).map(([k, v]) => ({
        key: k,
        ...v,
        age: Math.floor((Date.now() - v.timestamp) / 1000) + ' seconds'
      })),
      queuedTasks: this.queue.filter(item => 
        item.data.priority === this.HIGHEST_PRIORITY &&
        ['pending', 'submitting'].includes(item.status)
      ).map(item => ({
        id: item.id,
        status: item.status,
        bridgeName: item.data.bridgeName,
        machineName: item.data.machineName
      }))
    }
  }

  /**
   * Force sync active tasks (public method for debugging)
   */
  async forceSync() {
    console.log('Force syncing active tasks...')
    await this.syncActiveTasksStatus()
  }

  /**
   * Get active priority 1 tasks count per bridge
   */
  getActivePriority1CountByBridge(): Map<string, number> {
    const counts = new Map<string, number>()
    
    // Count from active tasks
    for (const task of this.activeTasks.values()) {
      if (task.priority === this.HIGHEST_PRIORITY) {
        const current = counts.get(task.bridgeName) || 0
        counts.set(task.bridgeName, current + 1)
      }
    }

    // Count from queue
    this.queue.forEach(item => {
      if (item.data.priority === this.HIGHEST_PRIORITY &&
          ['pending', 'submitting', 'submitted'].includes(item.status)) {
        const current = counts.get(item.data.bridgeName) || 0
        counts.set(item.data.bridgeName, current + 1)
      }
    })

    return counts
  }

  /**
   * Start periodic sync to check task status
   */
  private startPeriodicSync() {
    // Run sync immediately
    this.syncActiveTasksStatus()
    
    // Check every 10 seconds for stale active tasks
    setInterval(() => {
      this.syncActiveTasksStatus()
    }, 10000)
  }

  /**
   * Sync active tasks status with actual completion
   */
  private async syncActiveTasksStatus() {
    const now = Date.now()
    const tasksToRemove: string[] = []

    for (const [key, task] of this.activeTasks) {
      // For priority 1 tasks older than 30 seconds, check if they're still active
      if (task.priority === this.HIGHEST_PRIORITY && 
          now - task.timestamp > 30 * 1000) {
        
        try {
          // Import apiClient dynamically to avoid circular dependency
          const { default: apiClient } = await import('@/api/client')
          const response = await apiClient.get('/GetQueueItemTrace', { taskId: task.taskId })
          
          // Check the status from the first table
          const queueDetails = response.tables?.[1]?.data?.[0]
          if (queueDetails) {
            const status = queueDetails.status || queueDetails.Status
            
            // If task is completed, failed, or cancelled, remove it
            if (['COMPLETED', 'FAILED', 'CANCELLED'].includes(status) || queueDetails.permanentlyFailed) {
              tasksToRemove.push(key)
              console.log(`Removing stale active task ${task.taskId} with status ${status}`)
            }
          } else {
            // If we can't find the task, it's probably old - remove it
            tasksToRemove.push(key)
            console.log(`Removing stale active task ${task.taskId} - not found in backend`)
          }
        } catch (error) {
          console.error(`Error checking task ${task.taskId}:`, error)
          // If there's an error checking, keep the task for now
        }
      }
    }

    // Remove stale tasks
    tasksToRemove.forEach(key => {
      this.activeTasks.delete(key)
    })

    if (tasksToRemove.length > 0) {
      this.notifyListeners()
    }
  }
}

// Create singleton instance
const queueManagerService = new QueueManagerService()

// Expose debug methods on window for debugging
if (typeof window !== 'undefined') {
  (window as any).queueManagerDebug = {
    getInfo: () => queueManagerService.getDebugInfo(),
    clearActiveTasks: (bridgeName?: string) => queueManagerService.clearActiveTasks(bridgeName),
    updateTaskStatus: (taskId: string, status: 'completed' | 'failed' | 'cancelled') => 
      queueManagerService.updateTaskStatus(taskId, status),
    forceSync: () => queueManagerService.forceSync()
  }
}

export default queueManagerService
export type { QueuedItem, ActiveTask }