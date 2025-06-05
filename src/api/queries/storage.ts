import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/client'
import toast from 'react-hot-toast'

export interface Storage {
  storageName: string
  teamName: string
  vaultVersion: number
  vaultContent?: string
}

// Get storage for a team or multiple teams
export const useStorage = (teamFilter?: string | string[]) => {
  return useQuery<Storage[]>({
    queryKey: ['storage', teamFilter],
    queryFn: async () => {
      if (!teamFilter || (Array.isArray(teamFilter) && teamFilter.length === 0)) return []
      
      // Build params based on teamFilter
      let params = {}
      
      if (Array.isArray(teamFilter)) {
        // Send comma-separated teams in a single request
        params = { teamName: teamFilter.join(',') }
      } else {
        // Single team
        params = { teamName: teamFilter }
      }
      
      const response = await apiClient.get('/GetTeamStorages', params)
      const data = response.tables?.[1]?.data || response.tables?.[0]?.data || []
      if (!Array.isArray(data)) return []
      return data.filter((storage: any) => storage && storage.storageName)
    },
    enabled: !!teamFilter && (!Array.isArray(teamFilter) || teamFilter.length > 0),
    staleTime: 30 * 1000, // 30 seconds
  })
}

// Create storage
export const useCreateStorage = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (data: { teamName: string; storageName: string; storageVault?: string }) => {
      const response = await apiClient.post('/CreateStorage', {
        teamName: data.teamName,
        storageName: data.storageName,
        storageVault: data.storageVault || '{}',
      })
      return response
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['storage'] })
      queryClient.invalidateQueries({ queryKey: ['teams'] })
      toast.success(`Storage "${variables.storageName}" created successfully`)
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to create storage')
    },
  })
}

// Update storage name
export const useUpdateStorageName = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (data: { teamName: string; currentStorageName: string; newStorageName: string }) => {
      const response = await apiClient.put('/UpdateStorageName', data)
      return response
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['storage'] })
      toast.success(`Storage renamed to "${variables.newStorageName}"`)
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to update storage name')
    },
  })
}

// Update storage vault
export const useUpdateStorageVault = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (data: { teamName: string; storageName: string; storageVault: string; vaultVersion: number }) => {
      const response = await apiClient.put('/UpdateStorageVault', data)
      return response
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['storage'] })
      toast.success(`Storage vault updated for "${variables.storageName}"`)
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to update storage vault')
    },
  })
}

// Delete storage
export const useDeleteStorage = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (data: { teamName: string; storageName: string }) => {
      const response = await apiClient.delete('/DeleteStorage', data)
      return response
    },
    onSuccess: (_, data) => {
      queryClient.invalidateQueries({ queryKey: ['storage'] })
      queryClient.invalidateQueries({ queryKey: ['teams'] })
      toast.success(`Storage "${data.storageName}" deleted successfully`)
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to delete storage')
    },
  })
}