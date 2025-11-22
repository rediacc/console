import { useQuery } from '@tanstack/react-query'
import apiClient from '@/api/client'
import { extractTableData } from '@/core/api/response'
import { createResourceMutation, createVaultUpdateMutation, createMutation } from '@/hooks/api/mutationFactory'

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
      const storages = extractTableData<Record<string, unknown>[]>(response, 1, [])
      return storages
        .filter((storage) => storage && storage.storageName)
        .map((storage) => ({
          storageName: storage.storageName as string,
          teamName: storage.teamName as string,
          vaultVersion: (storage.vaultVersion as number) || 1,
          vaultContent: (storage.vaultContent as string) || '{}',
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
