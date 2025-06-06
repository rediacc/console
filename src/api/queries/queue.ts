import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/client'
import toast from 'react-hot-toast'

export interface QueueItem {
  taskId: string
  teamName: string
  machineName: string
  bridgeName: string
  queueVault: string
  status: 'pending' | 'processing' | 'completed' | 'failed'
  priority: number // 1-5, where 1 is highest priority
  protection?: boolean // Whether the item is protected from deletion
  createdAt: string
  updatedAt?: string
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

// Queue functions definition (from CLI)
export const QUEUE_FUNCTIONS: Record<string, QueueFunction> = {
  // System setup functions
  'os_setup': {
    name: 'os_setup',
    category: 'System Functions',
    description: 'Setup operating system with required tools and configurations',
    params: {
      datastore_size: { type: 'string', default: '95%', help: 'Datastore size (e.g., 95%, 100G)' },
      source: { type: 'string', default: 'apt-repo', help: 'Package source' }
    }
  },
  'hello': {
    name: 'hello',
    category: 'System Functions',
    description: 'Simple test function that prints hello from hostname',
    params: {}
  },
  'uninstall': {
    name: 'uninstall',
    category: 'System Functions',
    description: 'Cleanup and uninstall system components',
    params: {}
  },
  
  // Repository management functions
  'repo_new': {
    name: 'repo_new',
    category: 'Repository Functions',
    description: 'Create a new repository',
    params: {
      repo: { type: 'string', required: true, help: 'Repository name (no numbers)' },
      size: { type: 'string', required: true, help: 'Repository size (e.g., 10G)' }
    }
  },
  'repo_mount': {
    name: 'repo_mount',
    category: 'Repository Functions',
    description: 'Mount repository filesystems',
    params: {
      repo: { type: 'string', required: true, help: 'Repository name(s), comma-separated' },
      from: { type: 'string', help: 'Remote machine to mount from' }
    }
  },
  'repo_unmount': {
    name: 'repo_unmount',
    category: 'Repository Functions',
    description: 'Unmount repository filesystems',
    params: {
      repo: { type: 'string', required: true, help: 'Repository name(s), comma-separated' },
      from: { type: 'string', help: 'Remote machine to unmount from' }
    }
  },
  'repo_up': {
    name: 'repo_up',
    category: 'Repository Functions',
    description: 'Start repository services using Rediaccfile',
    params: {
      repo: { type: 'string', required: true, help: 'Repository name(s), comma-separated' },
      option: { type: 'string', help: 'Options (e.g., prep-only)' }
    }
  },
  'repo_down': {
    name: 'repo_down',
    category: 'Repository Functions',
    description: 'Stop repository services',
    params: {
      repo: { type: 'string', required: true, help: 'Repository name(s), comma-separated' }
    }
  },
  'repo_resize': {
    name: 'repo_resize',
    category: 'Repository Functions',
    description: 'Resize repository storage',
    params: {
      repo: { type: 'string', required: true, help: 'Repository name' },
      size: { type: 'string', required: true, help: 'New size (e.g., 20G)' }
    }
  },
  'repo_rm': {
    name: 'repo_rm',
    category: 'Repository Functions',
    description: 'Delete repository',
    params: {
      repo: { type: 'string', required: true, help: 'Repository name' }
    }
  },
  'repo_plugin': {
    name: 'repo_plugin',
    category: 'Repository Functions',
    description: 'Activate repository plugins',
    params: {
      repo: { type: 'string', required: true, help: 'Repository name(s), comma-separated' },
      plugin: { type: 'string', required: true, help: 'Plugin name(s), comma-separated' }
    }
  },
  'repo_plugout': {
    name: 'repo_plugout',
    category: 'Repository Functions',
    description: 'Deactivate repository plugins',
    params: {
      repo: { type: 'string', required: true, help: 'Repository name(s), comma-separated' },
      plugin: { type: 'string', required: true, help: 'Plugin name(s), comma-separated' }
    }
  },
  'repo_ownership': {
    name: 'repo_ownership',
    category: 'Repository Functions',
    description: 'Change repository ownership',
    params: {
      repo: { type: 'string', required: true, help: 'Repository name' },
      from: { type: 'string', required: true, help: 'Current owner' },
      to: { type: 'string', help: 'New owner (default: universal user)' }
    }
  },
  'repo_list': {
    name: 'repo_list',
    category: 'Repository Functions',
    description: 'List repositories',
    params: {
      kind: { type: 'string', default: 'repo', help: 'Type to list' },
      format: { type: 'string', help: 'Output format (json)' }
    }
  },
  
  // Backup functions
  'repo_push': {
    name: 'repo_push',
    category: 'Backup Functions',
    description: 'Push repository to remote storage',
    params: {
      repo: { type: 'string', required: true, help: 'Repository name(s), comma-separated' },
      to: { type: 'string', help: 'Destination machine/storage' },
      option: { type: 'string', help: 'Options (e.g., no-suffix, override)' }
    }
  },
  'repo_pull': {
    name: 'repo_pull',
    category: 'Backup Functions',
    description: 'Pull repository from remote storage',
    params: {
      from: { type: 'string', required: true, help: 'Source machine/storage' },
      repo: { type: 'string', required: true, help: 'Repository name(s), comma-separated' }
    }
  },
  
  // Socket mapping
  'map_socket': {
    name: 'map_socket',
    category: 'Network Functions',
    description: 'Map socket from remote machine',
    params: {
      machine: { type: 'string', required: true, help: 'Machine name' },
      repo: { type: 'string', required: true, help: 'Repository name' },
      plugin: { type: 'string', required: true, help: 'Plugin name' }
    }
  }
}

// Get queue items
export const useQueueItems = (teamName?: string) => {
  return useQuery({
    queryKey: ['queue-items', teamName],
    queryFn: async () => {
      // Queue items are always retrieved per team
      if (!teamName) {
        return [] // Return empty array if no team is selected
      }
      const response = await apiClient.get<QueueItem[]>('/GetTeamQueueItems', { teamName })
      return response.tables[1]?.data || []
    },
    refetchInterval: 5000, // Refetch every 5 seconds for real-time updates
    enabled: !!teamName, // Only run query if teamName is provided
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

// Get queue items by bridge
export const useQueueItemsByBridge = (bridgeName: string) => {
  return useQuery({
    queryKey: ['queue-items-bridge', bridgeName],
    queryFn: async () => {
      const response = await apiClient.get<QueueItem[]>('/GetBridgeQueueItems', { bridgeName })
      return response.tables[1]?.data || []
    },
    refetchInterval: 5000, // Refetch every 5 seconds for real-time updates
    enabled: !!bridgeName,
  })
}

// Get queue items with advanced filtering
export const useFilteredQueueItems = (filters: {
  teamName?: string
  bridgeName?: string
  machineName?: string
  priority?: number
  status?: QueueItem['status']
  protected?: boolean
}) => {
  return useQuery({
    queryKey: ['queue-items-filtered', filters],
    queryFn: async () => {
      const response = await apiClient.get<QueueItem[]>('/GetFilteredQueueItems', filters)
      return response.tables[1]?.data || []
    },
    refetchInterval: 5000, // Refetch every 5 seconds for real-time updates
    enabled: !!(filters.teamName || filters.bridgeName || filters.machineName),
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