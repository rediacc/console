import { useQuery } from '@tanstack/react-query'
import apiClient from '@/api/client'
import { createResourceMutation, createVaultUpdateMutation, createMutation } from '@/api/utils/mutationFactory'
import { extractResourceData, extractTableData } from '@/api/utils/responseHelpers'

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
      return extractResourceData<Region>(response, 'regionName')
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
      return extractTableData(response, 1, [])
    },
    enabled: !!regionName,
  })
}

// Create region
export const useCreateRegion = createResourceMutation<{ regionName: string; regionVault?: string }>(
  'Region', 'create', '/CreateRegion', 'regionName'
)

// Update region name
export const useUpdateRegionName = createMutation<{ currentRegionName: string; newRegionName: string }>({
  endpoint: '/UpdateRegionName',
  method: 'put',
  invalidateKeys: ['regions', 'dropdown-data'],
  successMessage: (variables) => `Region renamed to "${variables.newRegionName}"`,
  errorMessage: 'Failed to update region name'
})

// Update region vault
export const useUpdateRegionVault = createVaultUpdateMutation<{ regionName: string; regionVault: string; vaultVersion: number }>(
  'Region', '/UpdateRegionVault', 'regionName', 'regionVault'
)

// Delete region
export const useDeleteRegion = createMutation<string>({
  endpoint: '/DeleteRegion',
  method: 'delete',
  invalidateKeys: ['regions', 'dropdown-data'],
  successMessage: (regionName) => `Region "${regionName}" deleted successfully`,
  errorMessage: 'Failed to delete region',
  transformData: (regionName) => ({ regionName })
})