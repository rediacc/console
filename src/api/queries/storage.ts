import { useQuery } from '@tanstack/react-query'
import apiClient from '@/api/client'
import { createResourceMutation, createVaultUpdateMutation, createMutation } from '@/api/utils/mutationFactory'

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
      const storages = Array.isArray(data) ? data : []
      return storages
        .filter((storage: any) => storage && storage.storageName)
        .map((storage: any) => ({
          storageName: storage.storageName,
          teamName: storage.teamName,
          vaultVersion: storage.vaultVersion || 1,
          vaultContent: storage.vaultContent || '{}',
        }))
    },
    enabled: !!teamFilter && (!Array.isArray(teamFilter) || teamFilter.length > 0),
    staleTime: 30 * 1000, // 30 seconds
  })
}

// Create storage
export const useCreateStorage = createMutation<{
  teamName: string
  storageName: string
  storageVault?: string
}>({
  endpoint: '/CreateStorage',
  method: 'post',
  invalidateKeys: ['storage', 'teams'],
  successMessage: (vars) => `Storage "${vars.storageName}" created successfully`,
  errorMessage: 'Failed to create storage',
  transformData: (data) => ({
    ...data,
    storageVault: data.storageVault || '{}'
  })
})

// Update storage name
export const useUpdateStorageName = createMutation<{
  teamName: string
  currentStorageName: string
  newStorageName: string
}>({
  endpoint: '/UpdateStorageName',
  method: 'put',
  invalidateKeys: ['storage'],
  successMessage: (vars) => `Storage renamed to "${vars.newStorageName}"`,
  errorMessage: 'Failed to update storage name'
})

// Update storage vault
export const useUpdateStorageVault = createVaultUpdateMutation<{
  teamName: string
  storageName: string
  storageVault: string
  vaultVersion: number
}>(
  'Storage',
  '/UpdateStorageVault',
  'storageName',
  'storageVault'
)

// Delete storage
export const useDeleteStorage = createResourceMutation<{
  teamName: string
  storageName: string
}>(
  'Storage',
  'delete',
  '/DeleteStorage',
  'storageName',
  ['teams']
)