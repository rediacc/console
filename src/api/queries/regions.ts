import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/client'
import toast from 'react-hot-toast'

export interface Region {
  regionName: string
  bridgeCount: number
  vaultVersion: number
  vaultContent?: string
}

// Get all regions
export const useRegions = (enabled: boolean = true) => {
  return useQuery<Region[]>({
    queryKey: ['regions'],
    queryFn: async () => {
      const response = await apiClient.get('/GetCompanyRegions')
      const data = response.tables?.[1]?.data || response.tables?.[0]?.data || []
      if (!Array.isArray(data)) return []
      // Filter out any empty or invalid region objects
      return data.filter(region => region && region.regionName)
    },
    enabled,
    staleTime: 30 * 1000, // 30 seconds
  })
}

// Get bridges for a region
export const useRegionBridges = (regionName: string) => {
  return useQuery({
    queryKey: ['region-bridges', regionName],
    queryFn: async () => {
      const response = await apiClient.get('/GetRegionBridges', { regionName })
      const data = response.tables?.[1]?.data || response.tables?.[0]?.data || []
      return Array.isArray(data) ? data : []
    },
    enabled: !!regionName,
  })
}

// Create region
export const useCreateRegion = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (data: { regionName: string; regionVault?: string }) => {
      const response = await apiClient.post('/CreateRegion', {
        regionName: data.regionName,
        regionVault: data.regionVault || '{}',
      })
      return response
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['regions'] })
      queryClient.invalidateQueries({ queryKey: ['dropdown-data'] })
      toast.success(`Region "${variables.regionName}" created successfully`)
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to create region')
    },
  })
}

// Update region name
export const useUpdateRegionName = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (data: { currentRegionName: string; newRegionName: string }) => {
      const response = await apiClient.put('/UpdateRegionName', data)
      return response
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['regions'] })
      queryClient.invalidateQueries({ queryKey: ['dropdown-data'] })
      toast.success(`Region renamed to "${variables.newRegionName}"`)
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to update region name')
    },
  })
}

// Update region vault
export const useUpdateRegionVault = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (data: { regionName: string; regionVault: string; vaultVersion: number }) => {
      const response = await apiClient.put('/UpdateRegionVault', data)
      return response
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['regions'] })
      toast.success(`Region vault updated for "${variables.regionName}"`)
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to update region vault')
    },
  })
}

// Delete region
export const useDeleteRegion = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (regionName: string) => {
      const response = await apiClient.delete('/DeleteRegion', { regionName })
      return response
    },
    onSuccess: (_, regionName) => {
      queryClient.invalidateQueries({ queryKey: ['regions'] })
      queryClient.invalidateQueries({ queryKey: ['dropdown-data'] })
      toast.success(`Region "${regionName}" deleted successfully`)
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to delete region')
    },
  })
}