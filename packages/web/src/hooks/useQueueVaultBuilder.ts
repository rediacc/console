import { useCallback } from 'react'
import { queueService, type QueueRequestContext } from '@/services/queueService'
import { api } from '@/api/client'
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
      repoVault?: any
      bridgeVault?: any
      storageVault?: any
      destinationMachineVault?: any
      destinationStorageVault?: any
      sourceMachineVault?: any
      sourceStorageVault?: any
      allRepoCredentials?: Record<string, string>
      additionalStorageData?: Record<string, any>
      additionalMachineData?: Record<string, any>
    }
  ): Promise<string> => {
    // Fetch company vault directly from API to ensure we have the latest data
    const companyVaultData = await api.company.getVault()

    if (!companyVaultData) {
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
      repoVault: context.repoVault ? parseVault(context.repoVault) : {},
      bridgeVault: context.bridgeVault ? parseVault(context.bridgeVault) : {},
      storageVault: context.storageVault ? parseVault(context.storageVault) : {},
      companyVault: parseVault(companyVaultData.vault),
      destinationMachineVault: context.destinationMachineVault ? parseVault(context.destinationMachineVault) : {},
      destinationStorageVault: context.destinationStorageVault ? parseVault(context.destinationStorageVault) : {},
      sourceMachineVault: context.sourceMachineVault ? parseVault(context.sourceMachineVault) : {},
      sourceStorageVault: context.sourceStorageVault ? parseVault(context.sourceStorageVault) : {}
    }
    
    // Build complete context with vault data
    const fullContext: QueueRequestContext = {
      ...context,
      ...vaults,
      companyCredential: companyVaultData.companyCredential ?? undefined,
      allRepoCredentials: context.allRepoCredentials,
      additionalStorageData: context.additionalStorageData,
      additionalMachineData: context.additionalMachineData
    }

    // Use the service to build the vault
    return queueService.buildQueueVault(fullContext)
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
