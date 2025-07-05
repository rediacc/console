import { useCallback } from 'react'
import { queueDataService, QueueRequestContext } from '@/services/queueDataService'
import apiClient from '@/api/client'
import { minifyJSON } from '@/utils/json'

/**
 * Hook to build queue vault data with all required context
 * This combines vault data from various entities based on function requirements
 */
export function useQueueVaultBuilder() {
  const buildQueueVault = useCallback(async (
    context: Omit<QueueRequestContext, 'companyVault'> & {
      // Allow passing vault data directly from components that already have it
      teamVault?: any
      machineVault?: any
      repositoryVault?: any
      bridgeVault?: any
      storageVault?: any
      destinationMachineVault?: any
      destinationStorageVault?: any
      allRepositoryCredentials?: Record<string, string>
    }
  ): Promise<string> => {
    // Fetch company vault directly from API to ensure we have the latest data
    let companyVaultData = null
    try {
      const response = await apiClient.get('/GetCompanyVault')
      // Company vault data is in the second table (index 1)
      const vaultData = response.tables[1]?.data[0]
      
      if (vaultData) {
        companyVaultData = {
          vault: vaultData.vaultContent || '{}',
          vaultVersion: vaultData.vaultVersion || 1
        }
      } else {
        // No company vault data found
        throw new Error('Company vault not found')
      }
    } catch (error) {
      console.error('Failed to fetch company vault:', error)
      throw new Error('Unable to fetch company vault configuration. Please ensure company vault is properly configured.')
    }
    // Parse vault content (it's stored as JSON string in the API response)
    const parseVault = (vaultContent: string | undefined) => {
      if (!vaultContent || vaultContent === '-') return {}
      try {
        return JSON.parse(vaultContent)
      } catch (e) {
        return {}
      }
    }

    // Build vault data object using passed vault data or empty objects
    const vaults: any = {
      teamVault: context.teamVault ? parseVault(context.teamVault) : {},
      machineVault: context.machineVault ? parseVault(context.machineVault) : {},
      repositoryVault: context.repositoryVault ? parseVault(context.repositoryVault) : {},
      bridgeVault: context.bridgeVault ? parseVault(context.bridgeVault) : {},
      storageVault: context.storageVault ? parseVault(context.storageVault) : {},
      companyVault: companyVaultData ? parseVault(companyVaultData.vault) : {},
      destinationMachineVault: context.destinationMachineVault ? parseVault(context.destinationMachineVault) : {},
      destinationStorageVault: context.destinationStorageVault ? parseVault(context.destinationStorageVault) : {}
    }
    
    // Build complete context with vault data
    const fullContext: QueueRequestContext = {
      ...context,
      ...vaults,
      allRepositoryCredentials: context.allRepositoryCredentials
    }

    // Use the service to build the vault
    return queueDataService.buildQueueVault(fullContext)
  }, [])

  return { buildQueueVault }
}

/**
 * Simplified hook for components that just need basic queue vault
 * without all the context data injection
 */
export function useSimpleQueueVault() {
  const buildSimpleVault = useCallback((data: {
    function: string
    params: Record<string, any>
  }) => {
    return minifyJSON(JSON.stringify({
      function: data.function,
      params: data.params
    }))
  }, [])

  return { buildSimpleVault }
}