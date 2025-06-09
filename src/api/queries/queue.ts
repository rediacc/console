import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/client'
import toast from 'react-hot-toast'

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
  status: 'PENDING' | 'ASSIGNED' | 'PROCESSING' | 'COMPLETED' | 'CANCELLED'
  priority?: number // Only for Premium/Elite plans, 1-5 where 1 is highest
  priorityLabel?: string // 'Highest', 'High', 'Normal', 'Low', 'Lowest'
  createdTime: string
  ageInMinutes: number
  assignedTime?: string
  lastHeartbeat?: string
  minutesSinceHeartbeat?: number
  healthStatus: 'PENDING' | 'ACTIVE' | 'STALE' | 'COMPLETED' | 'CANCELLED' | 'UNKNOWN'
  canBeCancelled: boolean
  hasResponse: boolean
}

export interface QueueStatistics {
  totalCount: number
  pendingCount: number
  assignedCount: number
  processingCount: number
  completedCount: number
  cancelledCount: number
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
  }>
}

// Import queue functions from JSON
import functionsData from '@/data/functions.json'

// Queue functions definition (from JSON file)
export const QUEUE_FUNCTIONS: Record<string, QueueFunction> = functionsData.functions

// Parameters for GetTeamQueueItems
export interface QueueFilters {
  teamName?: string // Comma-separated team names
  machineName?: string
  bridgeName?: string
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
}

// Get queue items with advanced filtering
export const useQueueItems = (filters: QueueFilters = {}) => {
  return useQuery({
    queryKey: ['queue-items', filters],
    queryFn: async () => {
      const response = await apiClient.get<{ items: QueueItem[], statistics: QueueStatistics }>('/GetTeamQueueItems', filters)
      
      // Find the actual data tables (skip the nextRequestCredential table)
      // The queue items table has multiple fields, statistics table has count fields
      let items: QueueItem[] = []
      let statistics: QueueStatistics | null = null
      
      response.tables?.forEach((table) => {
        if (table.data && table.data.length > 0) {
          const firstItem = table.data[0]
          // Check if this is the statistics table
          if ('totalCount' in firstItem || 'pendingCount' in firstItem) {
            statistics = firstItem as QueueStatistics
          }
          // Check if this is the queue items table (has taskId)
          else if ('taskId' in firstItem || 'TaskId' in firstItem) {
            items = table.data as QueueItem[]
          }
          // Skip tables that only have nextRequestCredential
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
      return response.tables[1]?.data || []
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
    includeCancelled: true
  })
}

// Create queue item
export const useCreateQueueItem = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (data: {
      teamName: string
      machineName: string
      bridgeName: string
      queueVault: string
      priority?: number // Optional priority (1-5), defaults to 3
    }) => {
      // Ensure priority is within valid range
      const priority = data.priority && data.priority >= 1 && data.priority <= 5 ? data.priority : 3
      const response = await apiClient.post('/CreateQueueItem', { ...data, priority })
      return response
    },
    onSuccess: (response, variables) => {
      queryClient.invalidateQueries({ queryKey: ['queue-items'] })
      queryClient.invalidateQueries({ queryKey: ['queue-items-bridge', variables.bridgeName] })
      const taskId = response.tables[1]?.data[0]?.taskId || response.tables[1]?.data[0]?.TaskId
      toast.success(`Queue item created${taskId ? ` with ID: ${taskId}` : ''}`)
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to create queue item')
    },
  })
}

// Update queue item response
export const useUpdateQueueItemResponse = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (data: { taskId: string; responseVault: string }) => {
      const response = await apiClient.put('/UpdateQueueItemResponse', data)
      return response
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['queue-items'] })
      toast.success(`Queue item ${variables.taskId} response updated`)
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to update queue item')
    },
  })
}

// Complete queue item
export const useCompleteQueueItem = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (data: { taskId: string; finalVault: string }) => {
      const response = await apiClient.put('/UpdateQueueItemToCompleted', data)
      return response
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['queue-items'] })
      toast.success(`Queue item ${variables.taskId} completed`)
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to complete queue item')
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
      toast.success(`Queue item ${variables.taskId} priority updated to ${variables.priority}`)
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to update queue item priority')
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
      toast.success(`Queue item ${variables.taskId} protection ${variables.protection ? 'enabled' : 'disabled'}`)
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to update queue item protection')
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
      toast.success(`Queue item ${taskId} cancelled`)
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to cancel queue item')
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
      toast.success(`Queue item ${taskId} deleted`)
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to delete queue item')
    },
  })
}