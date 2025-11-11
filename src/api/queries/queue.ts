import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/client'
import { showMessage } from '@/utils/messages'
import { minifyJSON } from '@/utils/json'

export interface QueueItem {
  taskId: string
  teamName: string
  machineName: string
  bridgeName: string
  regionName: string
  vaultContent: string
  vaultVersion: number
  vaultContentResponse?: string
  vaultVersionResponse?: number
  status: 'PENDING' | 'ASSIGNED' | 'PROCESSING' | 'CANCELLING' | 'COMPLETED' | 'CANCELLED' | 'FAILED'
  priority?: number // Only for Business/Enterprise plans, 1-5 where 1 is highest
  priorityLabel?: string // 'Highest', 'High', 'Normal', 'Low', 'Lowest'
  createdTime: string
  ageInMinutes: number
  assignedTime?: string
  lastAssigned?: string
  minutesSinceAssigned?: number
  healthStatus: 'PENDING' | 'ACTIVE' | 'STALE' | 'STALE_PENDING' | 'CANCELLING' | 'COMPLETED' | 'CANCELLED' | 'FAILED' | 'UNKNOWN'
  canBeCancelled: boolean
  hasResponse: boolean
  retryCount?: number
  lastRetryAt?: string
  lastFailureReason?: string
  lastResponseAt?: string
  permanentlyFailed?: boolean
  createdBy?: string
}

export interface QueueStatistics {
  totalCount: number
  pendingCount: number
  assignedCount: number
  processingCount: number
  cancellingCount: number
  completedCount: number
  cancelledCount: number
  failedCount: number
  staleCount: number
}

export interface QueueFunction {
  name: string
  description: string
  category: string
  params: Record<string, {
    type: string
    required?: boolean
    default?: any
    help?: string
    label?: string
    format?: string
    units?: string[]
    options?: string[]
    ui?: string
    checkboxOptions?: Array<{ value: string; label: string }>
  }>
}

// Queue functions will be loaded via the functionsService instead

// Parameters for GetTeamQueueItems
export interface QueueFilters {
  teamName?: string // Comma-separated team names
  machineName?: string
  bridgeName?: string
  regionName?: string
  status?: string // Comma-separated status values
  priority?: number
  minPriority?: number
  maxPriority?: number
  dateFrom?: string
  dateTo?: string
  taskId?: string
  includeCompleted?: boolean
  includeCancelled?: boolean
  onlyStale?: boolean
  staleThresholdMinutes?: number
  maxRecords?: number
  createdByUserEmail?: string
}

// Get queue items with advanced filtering
export const useQueueItems = (filters: QueueFilters = {}) => {
  return useQuery({
    queryKey: ['queue-items', filters],
    queryFn: async () => {
      const response = await apiClient.get<{ items: QueueItem[], statistics: QueueStatistics }>('/GetTeamQueueItems', filters)
      
      // Find the actual data resultSets (skip the nextRequestToken table)
      // The queue items table has multiple fields, statistics table has count fields
      let items: QueueItem[] = []
      let statistics: QueueStatistics | null = null
      
      response.resultSets?.forEach((table) => {
        if (table.data && table.data.length > 0) {
          const firstItem = table.data[0]
          // Check if this is the statistics table
          if ('totalCount' in firstItem || 'pendingCount' in firstItem) {
            statistics = firstItem as unknown as QueueStatistics
          }
          // Check if this is the queue items table (has taskId)
          else if ('taskId' in firstItem || 'TaskId' in firstItem) {
            items = table.data as unknown as QueueItem[]
          }
          // Skip resultSets that only have nextRequestToken
        }
      })
      
      return { items, statistics }
    },
    // refetchInterval: 5000, // Disabled auto-refresh
  })
}

// Get next queue items for machine
export const useNextQueueItems = (machineName: string, itemCount: number = 5) => {
  return useQuery({
    queryKey: ['queue-next', machineName, itemCount],
    queryFn: async () => {
      const response = await apiClient.get<QueueItem[]>('/GetQueueItemsNext', { machineName, itemCount })
      return response.resultSets[1]?.data || []
    },
    enabled: !!machineName,
  })
}

// Get queue items by bridge (using GetTeamQueueItems with bridge filter)
export const useQueueItemsByBridge = (bridgeName: string, teamName?: string) => {
  return useQueueItems({
    teamName: teamName || '',
    bridgeName,
    includeCompleted: true,
    includeCancelled: false  // Don't show cancelled tasks by default
  })
}

// Create queue item (direct API call - use useManagedQueueItem for high-priority items)
export const useCreateQueueItem = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (data: {
      teamName: string
      machineName?: string // Made optional for bridge-only queue items
      bridgeName: string
      queueVault: string
      priority?: number // Optional priority (1-5), defaults to 3
    }) => {
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
    },
    onSuccess: (response, variables) => {
      queryClient.invalidateQueries({ queryKey: ['queue-items'] })
      queryClient.invalidateQueries({ queryKey: ['queue-items-bridge', variables.bridgeName] })
      showMessage('success', `Queue item created${response.taskId ? ` with ID: ${response.taskId}` : ''}`)
    },
    onError: (error: any) => {
      showMessage('error', error.message || 'Failed to create queue item')
    },
  })
}

// Update queue item response
export const useUpdateQueueItemResponse = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (data: { taskId: string; responseVault: string }) => {
      // Minify the vault JSON before sending
      const minifiedData = {
        ...data,
        responseVault: minifyJSON(data.responseVault)
      }
      const response = await apiClient.put('/UpdateQueueItemResponse', minifiedData)
      return response
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['queue-items'] })
      showMessage('success', `Queue item ${variables.taskId} response updated`)
    },
    onError: (error: any) => {
      showMessage('error', error.message || 'Failed to update queue item')
    },
  })
}

// Complete or fail queue item
export const useCompleteQueueItem = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (data: { taskId: string; finalVault: string; finalStatus?: 'COMPLETED' | 'FAILED' }) => {
      // Minify the vault JSON before sending
      const minifiedData = {
        ...data,
        finalVault: minifyJSON(data.finalVault),
        finalStatus: data.finalStatus || 'COMPLETED' // Default to COMPLETED for backward compatibility
      }
      const response = await apiClient.put('/UpdateQueueItemToCompleted', minifiedData)
      return response
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['queue-items'] })
      const status = variables.finalStatus || 'COMPLETED'
      const message = status === 'FAILED' ? 
        `Queue item ${variables.taskId} marked as failed` : 
        `Queue item ${variables.taskId} completed`
      showMessage('success', message)
    },
    onError: (error: any) => {
      showMessage('error', error.message || 'Failed to update queue item')
    },
  })
}

// Update queue item priority
export const useUpdateQueueItemPriority = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (data: { taskId: string; priority: number }) => {
      // Ensure priority is within valid range
      const priority = data.priority >= 1 && data.priority <= 5 ? data.priority : 3
      const response = await apiClient.put('/UpdateQueueItemPriority', { ...data, priority })
      return response
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['queue-items'] })
      queryClient.invalidateQueries({ queryKey: ['queue-items-bridge'] })
      showMessage('success', `Queue item ${variables.taskId} priority updated to ${variables.priority}`)
    },
    onError: (error: any) => {
      showMessage('error', error.message || 'Failed to update queue item priority')
    },
  })
}

// Update queue item protection status
export const useUpdateQueueItemProtection = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (data: { taskId: string; protection: boolean }) => {
      const response = await apiClient.put('/UpdateQueueItemProtection', data)
      return response
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['queue-items'] })
      queryClient.invalidateQueries({ queryKey: ['queue-items-bridge'] })
      showMessage('success', `Queue item ${variables.taskId} protection ${variables.protection ? 'enabled' : 'disabled'}`)
    },
    onError: (error: any) => {
      showMessage('error', error.message || 'Failed to update queue item protection')
    },
  })
}

// Cancel queue item
export const useCancelQueueItem = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (taskId: string) => {
      const response = await apiClient.post('/CancelQueueItem', { taskId })
      return response
    },
    onSuccess: (_, taskId) => {
      queryClient.invalidateQueries({ queryKey: ['queue-items'] })
      queryClient.invalidateQueries({ queryKey: ['queue-items-bridge'] })
      showMessage('success', `Queue item ${taskId} cancellation initiated`)
    },
    onError: (error: any) => {
      showMessage('error', error.message || 'Failed to cancel queue item')
    },
  })
}

// Delete queue item
export const useDeleteQueueItem = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (taskId: string) => {
      const response = await apiClient.delete('/DeleteQueueItem', { taskId })
      return response
    },
    onSuccess: (_, taskId) => {
      queryClient.invalidateQueries({ queryKey: ['queue-items'] })
      queryClient.invalidateQueries({ queryKey: ['queue-items-bridge'] })
      showMessage('success', `Queue item ${taskId} deleted`)
    },
    onError: (error: any) => {
      showMessage('error', error.message || 'Failed to delete queue item')
    },
  })
}

// Retry failed queue item
export const useRetryFailedQueueItem = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (taskId: string) => {
      const response = await apiClient.post('/RetryFailedQueueItem', { taskId })
      return response
    },
    onSuccess: (_, taskId) => {
      queryClient.invalidateQueries({ queryKey: ['queue-items'] })
      queryClient.invalidateQueries({ queryKey: ['queue-item-trace', taskId] })
      showMessage('success', `Queue item ${taskId} queued for retry`)
    },
    onError: (error: any) => {
      showMessage('error', error.message || 'Failed to retry queue item')
    },
  })
}

// Get queue item trace
export const useQueueItemTrace = (taskId: string | null, enabled: boolean = true) => {
  return useQuery({
    queryKey: ['queue-item-trace', taskId],
    queryFn: async () => {
      if (!taskId) return null
      const response = await apiClient.get('/GetQueueItemTrace', { taskId })
      
      let queueDetails: any = null
      let traceLogs: any[] = []
      let vaultContent: any = null
      let responseVaultContent: any = null
      let queuePosition: any[] = []
      let machineStats: any = null
      let planInfo: any = null
      
      // Parse the response resultSets by index
      response.resultSets?.forEach((table) => {
        if (table.data && table.data.length > 0) {
          const resultSetIndex = table.resultSetIndex
          
          switch (resultSetIndex) {
            case 1: // Queue details
              queueDetails = table.data[0]
              break
            case 2: // Vault content
              vaultContent = table.data[0]
              break
            case 3: // Response vault content
              responseVaultContent = table.data[0]
              break
            case 4: // Audit/trace logs
              traceLogs = table.data
              break
            case 5: // Queue position
              queuePosition = table.data
              break
            case 6: // Machine statistics
              machineStats = table.data[0]
              break
            case 7: // Plan information
              planInfo = table.data[0]
              break
          }
        }
      })
      
      return { 
        queueDetails, 
        traceLogs, 
        vaultContent, 
        responseVaultContent,
        queuePosition, 
        machineStats, 
        planInfo 
      }
    },
    enabled: enabled && !!taskId,
    refetchInterval: (query) => {
      // The query parameter contains the full query state, with data in query.state.data
      const data = query.state.data
      // Stop refreshing if the task is completed, cancelled, or permanently failed
      const status = data?.queueDetails?.status || data?.queueDetails?.Status
      const retryCount = data?.queueDetails?.retryCount || data?.queueDetails?.RetryCount || 0
      const permanentlyFailed = data?.queueDetails?.permanentlyFailed || data?.queueDetails?.PermanentlyFailed
      const lastFailureReason = data?.queueDetails?.lastFailureReason || data?.queueDetails?.LastFailureReason
      
      // Stop polling for completed or cancelled tasks
      if (status === 'COMPLETED' || status === 'CANCELLED') {
        return false
      }
      
      // Continue polling for CANCELLING status (it will transition to CANCELLED)
      if (status === 'CANCELLING') {
        return enabled && taskId ? 1000 : false
      }
      
      // Stop polling for permanently failed tasks (retry count >= 3)
      if (status === 'FAILED' && (permanentlyFailed || retryCount >= 3)) {
        return false
      }
      
      // Stop polling for tasks with specific permanent failure messages
      if ((status === 'FAILED' || status === 'PENDING') && lastFailureReason) {
        // Check for bridge reported failure or other permanent failures
        const permanentFailureMessages = [
          'Bridge reported failure',
          'Task permanently failed',
          'Fatal error'
        ]
        if (permanentFailureMessages.some(msg => lastFailureReason.includes(msg))) {
          return false
        }
      }
      
      // Stop polling for PENDING tasks that have reached max retries (3)
      // These are tasks that failed 3 times and are stuck in PENDING status
      if (status === 'PENDING' && retryCount >= 3 && lastFailureReason) {
        return false
      }
      
      // Continue polling for all other states, including FAILED tasks that can be retried
      // Refresh every 1 second when enabled
      return enabled && taskId ? 1000 : false
    },
    // Ensure that refetch waits for the previous request to complete
    refetchIntervalInBackground: false,
    // This ensures new requests wait for the previous one to complete
    networkMode: 'online',
  })
}
