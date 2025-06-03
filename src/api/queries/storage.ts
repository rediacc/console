import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/client'
import toast from 'react-hot-toast'

export interface Storage {
  storageName: string
  teamName: string
  vaultVersion: number
}

// Get storage for a team
export const useStorage = (teamName?: string) => {
  return useQuery<Storage[]>({
    queryKey: ['storage', teamName],
    queryFn: async () => {
      if (!teamName) return []
      const response = await apiClient.get<Storage[]>('/GetTeamStorages', { teamName })
      return response.tables[1]?.data || []
    },
    enabled: !!teamName,
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