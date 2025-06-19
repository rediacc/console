import { showMessage } from '@/utils/messages'
import { queueMonitoringService } from '@/services/queueMonitoringService'

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
  private activeTasks: Map<string, ActiveTask> = new Map() // key: bridgeName
  private taskIdToBridge: Map<string, string> = new Map() // taskId -> bridgeName mapping for priority 1 tasks
  private isProcessing = false
  private processingInterval: ReturnType<typeof setInterval> | null = null
  private readonly MAX_RETRIES = 3
  private readonly SUBMISSION_DELAY = 100 // 100ms between queue checks
  private readonly HIGHEST_PRIORITY = 1 // Only priority 1 items are queued
  private listeners: ((queue: QueuedItem[]) => void)[] = []

  constructor() {
    // Start processing queue when service is initialized
    this.startProcessing()
  }

  /**
   * Check if there's an active priority 1 task on a specific bridge
   */
  private hasActivePriority1Task(bridgeName: string, excludeItemId?: string): boolean {
    // Check in active tasks
    const activeTask = this.activeTasks.get(bridgeName)
    if (activeTask && activeTask.priority === this.HIGHEST_PRIORITY) {
      console.log('Found active priority 1 task:', {
        bridgeName: bridgeName,
        taskId: activeTask.taskId,
        status: activeTask.status,
        machineName: activeTask.machineName,
        timestamp: new Date(activeTask.timestamp).toISOString(),
        age: Math.floor((Date.now() - activeTask.timestamp) / 1000) + ' seconds'
      })
      return true
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
    // Track by bridge only, since the restriction is per user per bridge
    const key = task.bridgeName
    this.activeTasks.set(key, task)
    
    // Also track taskId -> bridge mapping for priority 1 tasks
    if (task.priority === this.HIGHEST_PRIORITY) {
      this.taskIdToBridge.set(task.taskId, task.bridgeName)
    }
    
    console.log(`Tracked active task: key=${key}, taskId=${task.taskId}, bridgeName=${task.bridgeName}, machineName=${task.machineName}`)
  }

  /**
   * Remove an active task by bridge name
   */
  private removeActiveTaskByBridge(bridgeName: string) {
    console.log(`Removing active task for bridge: ${bridgeName}`)
    const deleted = this.activeTasks.delete(bridgeName)
    if (!deleted) {
      console.log(`No active task found for bridge: ${bridgeName}`)
    }
    return deleted
  }

  /**
   * Start monitoring a task
   */
  private async startMonitoringTask(taskId: string, data: QueuedItem['data']) {
    try {
      console.log(`Starting monitoring for priority ${data.priority} task ${taskId}`)
      queueMonitoringService.addTask(
        taskId,
        data.teamName,
        data.machineName,
        'PENDING',
        undefined, // retryCount
        undefined, // lastFailureReason
        data.bridgeName,
        data.priority
      )
    } catch (error) {
      console.error('Failed to start monitoring for task:', error)
    }
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
      
      console.log('Added task to queue:', {
        id: queuedItem.id,
        bridgeName: data.bridgeName,
        machineName: data.machineName,
        queueLength: this.queue.length,
        activeTasks: Array.from(this.activeTasks.keys())
      })
      
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
    
    console.log(`Processing queue - found pending item: ${pendingItem?.id || 'none'}`)
    
    if (!pendingItem) {
      // Clean up completed items from queue
      this.queue = this.queue.filter(item => 
        item.status === 'pending' || 
        item.status === 'submitting'
      )
      
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
      console.log('Cancelling pending task:', {
        taskId: pendingItem.id,
        bridgeName: pendingItem.data.bridgeName,
        machineName: pendingItem.data.machineName
      })
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
        
        // Start monitoring this task
        this.startMonitoringTask(pendingItem.taskId, pendingItem.data)
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
   * Update task status from backend - THIS IS THE CRITICAL METHOD
   */
  updateTaskStatus(taskId: string, status: 'completed' | 'failed' | 'cancelled') {
    console.log(`\n=== updateTaskStatus called ===`)
    console.log(`TaskId: ${taskId}, Status: ${status}`)
    
    let bridgeCleared: string | null = null
    
    // First check if we have a taskId -> bridge mapping
    const mappedBridge = this.taskIdToBridge.get(taskId)
    if (mappedBridge) {
      console.log(`Found bridge mapping for taskId ${taskId}: ${mappedBridge}`)
      
      // Verify this task is still active
      const activeTask = this.activeTasks.get(mappedBridge)
      if (activeTask && activeTask.taskId === taskId) {
        if (status === 'completed' || status === 'failed' || status === 'cancelled') {
          this.activeTasks.delete(mappedBridge)
          this.taskIdToBridge.delete(taskId)
          bridgeCleared = mappedBridge
          console.log(`✓ Removed active priority 1 task for bridge: ${mappedBridge} (via taskId mapping)`)
        }
      }
    }
    
    // If not found via mapping, search all active tasks
    if (!bridgeCleared) {
      for (const [bridgeName, task] of this.activeTasks) {
        if (task.taskId === taskId && task.priority === this.HIGHEST_PRIORITY) {
          if (status === 'completed' || status === 'failed' || status === 'cancelled') {
            this.activeTasks.delete(bridgeName)
            this.taskIdToBridge.delete(taskId)
            bridgeCleared = bridgeName
            console.log(`✓ Removed active priority 1 task for bridge: ${bridgeName} (via search)`)
            break
          }
        }
      }
    }
    
    // Also check queue items
    if (!bridgeCleared) {
      const queueItem = this.queue.find(item => item.taskId === taskId)
      if (queueItem && queueItem.data.priority === this.HIGHEST_PRIORITY) {
        const bridgeName = queueItem.data.bridgeName
        
        // Remove from active tasks if it exists there
        if (this.activeTasks.has(bridgeName)) {
          const activeTask = this.activeTasks.get(bridgeName)
          if (activeTask && activeTask.taskId === taskId) {
            this.activeTasks.delete(bridgeName)
            this.taskIdToBridge.delete(taskId)
            bridgeCleared = bridgeName
            console.log(`✓ Removed active priority 1 task for bridge via queue: ${bridgeName}`)
          }
        }
        
        // Update queue item status
        if (status === 'completed' || status === 'failed' || status === 'cancelled') {
          queueItem.status = 'submitted'
        }
      }
    }
    
    console.log(`Task update complete. Bridge cleared: ${bridgeCleared || 'none'}`)
    console.log(`Current active tasks: ${this.activeTasks.size}, TaskId mappings: ${this.taskIdToBridge.size}`)
    console.log(`=== End updateTaskStatus ===\n`)
    
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
   * Clear active task for a specific bridge (recovery mechanism)
   */
  clearBridgeTask(bridgeName: string): boolean {
    const task = this.activeTasks.get(bridgeName)
    if (task) {
      console.log(`Manually clearing active task for bridge ${bridgeName}, taskId: ${task.taskId}`)
      this.activeTasks.delete(bridgeName)
      
      // Also remove from taskId mapping
      if (task.priority === this.HIGHEST_PRIORITY) {
        this.taskIdToBridge.delete(task.taskId)
      }
      
      this.notifyListeners()
      return true
    }
    return false
  }

  /**
   * Clear all stuck priority 1 tasks (recovery mechanism)
   */
  clearAllStuckTasks(): number {
    let clearedCount = 0
    const stuckTasks: string[] = []
    
    // Find all priority 1 tasks
    for (const [bridgeName, task] of this.activeTasks) {
      if (task.priority === this.HIGHEST_PRIORITY) {
        stuckTasks.push(bridgeName)
      }
    }
    
    // Clear them
    for (const bridgeName of stuckTasks) {
      const task = this.activeTasks.get(bridgeName)
      if (task) {
        console.log(`Clearing stuck task: bridge=${bridgeName}, taskId=${task.taskId}, age=${Math.floor((Date.now() - task.timestamp) / 1000)}s`)
        this.activeTasks.delete(bridgeName)
        this.taskIdToBridge.delete(task.taskId)
        clearedCount++
      }
    }
    
    if (clearedCount > 0) {
      this.notifyListeners()
      console.log(`Cleared ${clearedCount} stuck priority 1 tasks`)
    }
    
    return clearedCount
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
      taskIdMappings: Array.from(this.taskIdToBridge.entries()).map(([taskId, bridge]) => ({
        taskId,
        bridge
      })),
      queuedTasks: this.queue.filter(item => 
        item.data.priority === this.HIGHEST_PRIORITY &&
        ['pending', 'submitting'].includes(item.status)
      ).map(item => ({
        id: item.id,
        status: item.status,
        bridgeName: item.data.bridgeName,
        machineName: item.data.machineName,
        taskId: item.taskId
      }))
    }
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

}

// Create singleton instance
const queueManagerService = new QueueManagerService()

// Expose simple debug info on window
if (typeof window !== 'undefined') {
  (window as any).queueInfo = () => {
    const info = queueManagerService.getDebugInfo()
    console.log('=== Queue Manager Status ===')
    console.log('Active Priority 1 Tasks:', info.activeTasks)
    console.log('TaskId Mappings:', info.taskIdMappings)
    console.log('Queued Tasks:', info.queuedTasks)
    return info
  }
  
  ;(window as any).clearStuckTasks = () => {
    const count = queueManagerService.clearAllStuckTasks()
    console.log(`Cleared ${count} stuck priority 1 tasks`)
    return count
  }
}

export default queueManagerService
export type { QueuedItem, ActiveTask }