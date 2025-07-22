import { useQuery } from '@tanstack/react-query'
import apiClient from '@/api/client'
import { createResourceMutation, createVaultUpdateMutation, createMutation } from '@/api/utils/mutationFactory'

export interface Bridge {
  bridgeName: string
  regionName: string
  machineCount: number
  vaultVersion: number
  vaultContent?: string
  bridgeCredentialsVersion?: number
  bridgeCredentials?: string
  bridgeUserEmail?: string
  hasAccess?: number // 0 or 1 from SQL
  managementMode?: string
  isGlobalBridge?: boolean
}

// Get bridges for a region
export const useBridges = (regionName?: string) => {
  return useQuery<Bridge[]>({
    queryKey: ['bridges', regionName],
    queryFn: async () => {
      if (!regionName) return []
      const response = await apiClient.get('/GetRegionBridges', { regionName })
      const data = response.resultSets?.[1]?.data || []
      if (!Array.isArray(data)) return []
      // Filter out any empty or invalid bridge objects
      return data.filter(bridge => bridge && bridge.bridgeName)
    },
    enabled: !!regionName,
    staleTime: 30 * 1000, // 30 seconds
  })
}

// Create bridge
export const useCreateBridge = createMutation<{
  regionName: string
  bridgeName: string
  bridgeVault?: string
}>({
  endpoint: '/CreateBridge',
  method: 'post',
  invalidateKeys: ['bridges', 'regions', 'dropdown-data'],
  successMessage: (vars) => `Bridge "${vars.bridgeName}" created successfully`,
  errorMessage: 'Failed to create bridge',
  transformData: (data) => ({
    ...data,
    bridgeVault: data.bridgeVault || '{}'
  })
})

// Update bridge name
export const useUpdateBridgeName = createMutation<{
  regionName: string
  currentBridgeName: string
  newBridgeName: string
}>({
  endpoint: '/UpdateBridgeName',
  method: 'put',
  invalidateKeys: ['bridges', 'dropdown-data'],
  successMessage: (vars) => `Bridge renamed to "${vars.newBridgeName}"`,
  errorMessage: 'Failed to update bridge name'
})

// Update bridge vault
export const useUpdateBridgeVault = createVaultUpdateMutation<{
  regionName: string
  bridgeName: string
  bridgeVault: string
  vaultVersion: number
}>(
  'Bridge',
  '/UpdateBridgeVault',
  'bridgeName',
  'bridgeVault'
)

// Delete bridge
export const useDeleteBridge = createResourceMutation<{
  regionName: string
  bridgeName: string
}>(
  'Bridge',
  'delete',
  '/DeleteBridge',
  'bridgeName',
  ['regions']
)

// Reset bridge authorization
export const useResetBridgeAuthorization = createMutation<{
  bridgeName: string
  isCloudManaged?: boolean
}>({
  endpoint: '/ResetBridgeAuthorization',
  method: 'post',
  invalidateKeys: ['bridges'],
  successMessage: (vars) => `Bridge authorization reset for "${vars.bridgeName}"`,
  errorMessage: 'Failed to reset bridge authorization'
})