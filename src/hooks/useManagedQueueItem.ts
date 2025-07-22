import { useState, useEffect } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/client'
import { showMessage } from '@/utils/messages'
import { minifyJSON } from '@/utils/json'
import queueManagerService, { QueuedItem } from '@/services/queueManagerService'

interface CreateQueueItemData {
  teamName: string
  machineName: string
  bridgeName: string
  queueVault: string
  priority?: number
}

/**
 * A managed version of useCreateQueueItem that handles high-priority queue items
 * through a client-side queue to avoid server-side limitations
 */
export const useManagedQueueItem = () => {
  const queryClient = useQueryClient()
  const [localQueue, setLocalQueue] = useState<QueuedItem[]>([])

  // Subscribe to queue changes
  useEffect(() => {
    const unsubscribe = queueManagerService.subscribe((queue) => {
      setLocalQueue(queue)
    })
    
    return () => {
      unsubscribe()
    }
  }, [])

  // The actual API call function
  const submitQueueItem = async (data: CreateQueueItemData) => {
    // Ensure priority is within valid range
    const priority = data.priority && data.priority >= 1 && data.priority <= 5 ? data.priority : 3
    
    // Minify the vault JSON before sending
    const minifiedData = {
      ...data,
      queueVault: minifyJSON(data.queueVault),
      priority
    }
    
    
    const response = await apiClient.post('/CreateQueueItem', minifiedData)
    
    // Extract taskId from response and add it to the response object
    const taskId = response.resultSets[1]?.data[0]?.taskId || response.resultSets[1]?.data[0]?.TaskId
    return { ...response, taskId }
  }

  const mutation = useMutation({
    mutationFn: async (data: CreateQueueItemData) => {
      // Use queue manager for submission
      const queueId = await queueManagerService.addToQueue(data, submitQueueItem)
      
      // For highest priority items (priority 1), return the queue ID instead of task ID
      const isHighestPriority = data.priority === 1
      if (isHighestPriority) {
        return { queueId, isQueued: true }
      }
      
      // For all other priorities, the item was submitted immediately
      return { taskId: queueId, isQueued: false }
    },
    onSuccess: (response, variables) => {
      queryClient.invalidateQueries({ queryKey: ['queue-items'] })
      queryClient.invalidateQueries({ queryKey: ['queue-items-bridge', variables.bridgeName] })
      
      if (response.isQueued) {
        // Don't show success message for queued items, it was already shown by the service
      } else if (response.taskId) {
        // Success message removed - queue item created silently
      }
    },
    onError: (error: any) => {
      showMessage('error', error.message || 'Failed to create queue item')
    },
  })

  return {
    ...mutation,
    localQueue,
    queueStats: queueManagerService.getQueueStats(),
    retryQueueItem: (id: string) => queueManagerService.retryItem(id),
    removeFromQueue: (id: string) => queueManagerService.removeFromQueue(id),
    clearCompleted: () => queueManagerService.clearCompleted(),
    getQueuePosition: (id: string) => queueManagerService.getQueuePosition(id),
    getQueueItem: (queueId: string) => queueManagerService.getQueueItem(queueId),
    subscribeToQueueItem: (queueId: string, callback: (item: any) => void) => 
      queueManagerService.subscribeToQueueItem(queueId, callback)
  }
}