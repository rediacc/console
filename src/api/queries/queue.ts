import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/client'
import { extractTableData, getFirstRow, getResultSetByIndex } from '@/core/api/response'
import { showMessage } from '@/utils/messages'
import { minifyJSON } from '@/utils/json'
import { createErrorHandler } from '@/utils/mutationUtils'
import i18n from '@/i18n/config'

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
      return extractTableData<QueueItem[]>(response, 1, [])
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
      const taskRow = getFirstRow<Record<string, unknown>>(response, 1)
      const taskId = (taskRow?.taskId as string) || (taskRow?.TaskId as string)
      return { ...response, taskId }
    },
    onSuccess: (response, variables) => {
      queryClient.invalidateQueries({ queryKey: ['queue-items'] })
      queryClient.invalidateQueries({ queryKey: ['queue-items-bridge', variables.bridgeName] })
      const message = response.taskId
        ? i18n.t('queue:success.createdWithId', { taskId: response.taskId })
        : i18n.t('queue:success.created')
      showMessage('success', message)
    },
    onError: createErrorHandler(i18n.t('queue:errors.createFailed')),
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
      showMessage('success', i18n.t('queue:success.responseUpdated', { taskId: variables.taskId }))
    },
    onError: createErrorHandler(i18n.t('queue:errors.updateFailed')),
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
      const message = status === 'FAILED'
        ? i18n.t('queue:success.markedFailed', { taskId: variables.taskId })
        : i18n.t('queue:success.completed', { taskId: variables.taskId })
      showMessage('success', message)
    },
    onError: createErrorHandler(i18n.t('queue:errors.updateFailed')),
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
      showMessage('success', i18n.t('queue:success.priorityUpdated', { taskId: variables.taskId, priority: variables.priority }))
    },
    onError: createErrorHandler(i18n.t('queue:errors.updatePriorityFailed')),
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
      const message = variables.protection
        ? i18n.t('queue:success.protectionEnabled', { taskId: variables.taskId })
        : i18n.t('queue:success.protectionDisabled', { taskId: variables.taskId })
      showMessage('success', message)
    },
    onError: createErrorHandler(i18n.t('queue:errors.updateProtectionFailed')),
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
      showMessage('success', i18n.t('queue:success.cancellationInitiated', { taskId }))
    },
    onError: createErrorHandler(i18n.t('queue:errors.cancelFailed')),
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
      showMessage('success', i18n.t('queue:success.deleted', { taskId }))
    },
    onError: createErrorHandler(i18n.t('queue:errors.deleteFailed')),
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
      showMessage('success', i18n.t('queue:success.queuedForRetry', { taskId }))
    },
    onError: createErrorHandler(i18n.t('queue:errors.retryFailed')),
  })
}

// Get queue item trace
export const useQueueItemTrace = (taskId: string | null, enabled: boolean = true) => {
  return useQuery({
    queryKey: ['queue-item-trace', taskId],
    queryFn: async () => {
      if (!taskId) return null
      const response = await apiClient.get('/GetQueueItemTrace', { taskId })
      
      // Using 'as any' here because QueueItemTraceModal expects flexible types
      // for these API response fields. Proper typing would require defining
      // specific interfaces for each response structure.
      const queueDetails = getFirstRow<Record<string, unknown>>(response, 1) as any
      const vaultContent = getFirstRow<Record<string, unknown>>(response, 2) as any
      const responseVaultContent = getFirstRow<Record<string, unknown>>(response, 3) as any
      const traceLogs = getResultSetByIndex<Record<string, unknown>>(response, 4) as any[]
      const queuePosition = getResultSetByIndex<Record<string, unknown>>(response, 5) as any[]
      const machineStats = getFirstRow<Record<string, unknown>>(response, 6) as any
      const planInfo = getFirstRow<Record<string, unknown>>(response, 7) as any

      return {
        queueDetails,
        traceLogs,
        vaultContent,
        responseVaultContent,
        queuePosition,
        machineStats,
        planInfo,
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
