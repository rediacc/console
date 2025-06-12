import { useCallback } from 'react'
import { queueDataService, QueueRequestContext } from '@/services/queueDataService'
import { useCompanyVault } from '@/api/queries/company'
import apiClient from '@/api/client'
import { minifyJSON } from '@/utils/json'

/**
 * Hook to build queue vault data with all required context
 * This combines vault data from various entities based on function requirements
 */
export function useQueueVaultBuilder() {
  const { data: companyVaultData } = useCompanyVault()

  const buildQueueVault = useCallback(async (
    context: Omit<QueueRequestContext, 'companyVault'> & {
      // Allow passing vault data directly from components that already have it
      teamVault?: any
      machineVault?: any
      repositoryVault?: any
      bridgeVault?: any
      storageVault?: any
    }
  ): Promise<string> => {
    // Parse vault content (it's stored as JSON string in the API response)
    const parseVault = (vaultContent: string | undefined) => {
      if (!vaultContent || vaultContent === '-') return {}
      try {
        return JSON.parse(vaultContent)
      } catch (e) {
        console.warn('Failed to parse vault content:', vaultContent, e)
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
      companyVault: companyVaultData ? parseVault(companyVaultData.vault) : {}
    }
    
    // Build complete context with vault data
    const fullContext: QueueRequestContext = {
      ...context,
      ...vaults
    }

    // Use the service to build the vault
    return queueDataService.buildQueueVault(fullContext)
  }, [companyVaultData])


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
    priority: number
    description: string
    addedVia: string
  }) => {
    return minifyJSON(JSON.stringify({
      function: data.function,
      params: data.params,
      priority: data.priority,
      description: data.description,
      addedVia: data.addedVia
    }))
  }, [])

  return { buildSimpleVault }
}