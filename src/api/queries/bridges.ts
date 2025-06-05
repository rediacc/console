import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/client'
import toast from 'react-hot-toast'

export interface Bridge {
  bridgeName: string
  regionName: string
  machineCount: number
  vaultVersion: number
}

// Get bridges for a region
export const useBridges = (regionName?: string) => {
  return useQuery<Bridge[]>({
    queryKey: ['bridges', regionName],
    queryFn: async () => {
      if (!regionName) return []
      const response = await apiClient.get<Bridge[]>('/GetRegionBridges', { regionName })
      const data = response.tables?.[1]?.data || response.tables?.[0]?.data || []
      if (!Array.isArray(data)) return []
      // Filter out any empty or invalid bridge objects
      return data.filter(bridge => bridge && bridge.bridgeName)
    },
    enabled: !!regionName,
    staleTime: 30 * 1000, // 30 seconds
  })
}

// Create bridge
export const useCreateBridge = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (data: { regionName: string; bridgeName: string; bridgeVault?: string }) => {
      const response = await apiClient.post('/CreateBridge', {
        regionName: data.regionName,
        bridgeName: data.bridgeName,
        bridgeVault: data.bridgeVault || '{}',
      })
      return response
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['bridges'] })
      queryClient.invalidateQueries({ queryKey: ['regions'] })
      queryClient.invalidateQueries({ queryKey: ['dropdown-data'] })
      toast.success(`Bridge "${variables.bridgeName}" created successfully`)
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to create bridge')
    },
  })
}

// Update bridge name
export const useUpdateBridgeName = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (data: { regionName: string; currentBridgeName: string; newBridgeName: string }) => {
      const response = await apiClient.put('/UpdateBridgeName', data)
      return response
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['bridges'] })
      queryClient.invalidateQueries({ queryKey: ['dropdown-data'] })
      toast.success(`Bridge renamed to "${variables.newBridgeName}"`)
    },
  })
}

// Update bridge vault
export const useUpdateBridgeVault = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (data: { regionName: string; bridgeName: string; bridgeVault: string; vaultVersion: number }) => {
      const response = await apiClient.put('/UpdateBridgeVault', data)
      return response
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['bridges'] })
      toast.success(`Bridge vault updated for "${variables.bridgeName}"`)
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to update bridge vault')
    },
  })
}

// Delete bridge
export const useDeleteBridge = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (data: { regionName: string; bridgeName: string }) => {
      const response = await apiClient.delete('/DeleteBridge', data)
      return response
    },
    onSuccess: (_, data) => {
      queryClient.invalidateQueries({ queryKey: ['bridges'] })
      queryClient.invalidateQueries({ queryKey: ['regions'] })
      queryClient.invalidateQueries({ queryKey: ['dropdown-data'] })
      toast.success(`Bridge "${data.bridgeName}" deleted successfully`)
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to delete bridge')
    },
  })
}