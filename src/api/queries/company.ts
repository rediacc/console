import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/client'
import { showMessage } from '@/utils/messages'
import { createMutation } from '@/api/utils/mutationFactory'
import { useAppSelector } from '@/store/store'
import { selectCompany } from '@/store/auth/authSelectors'
import { minifyJSON } from '@/utils/json'
import i18n from '@/i18n/config'

// Get company vault configuration
export const useCompanyVault = () => {
  const company = useAppSelector(selectCompany)
  
  return useQuery({
    queryKey: ['company-vault', company],
    queryFn: async () => {
      const response = await apiClient.get('/GetCompanyVault')
      // Company vault data is in the second table (index 1)
      const vaultData = response.resultSets[1]?.data[0]
      
      if (!vaultData) {
        return { vault: '{}', vaultVersion: 1 }
      }
      
      return {
        vault: vaultData.vaultContent || vaultData.VaultContent || '{}',
        vaultVersion: vaultData.vaultVersion || vaultData.VaultVersion || 1
      }
    },
    enabled: !!company
  })
}

// Update company vault configuration
export const useUpdateCompanyVault = createMutation<{ companyVault: string; vaultVersion: number }>({
  endpoint: '/UpdateCompanyVault',
  method: 'post',
  invalidateKeys: ['company-vault'],
  successMessage: () => 'Vault configuration updated successfully',
  errorMessage: 'Failed to update vault configuration',
  transformData: (data) => ({
    ...data,
    companyVault: minifyJSON(data.companyVault)
  })
})

// Block or unblock user requests - Special case with dynamic success message
export const useUpdateCompanyBlockUserRequests = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (blockUserRequests: boolean) => {
      const response = await apiClient.post('/UpdateCompanyBlockUserRequests', {
        blockUserRequests
      })
      return response.resultSets[0]?.data[0]
    },
    onSuccess: (data, variables) => {
      const action = variables ? 'blocked' : 'unblocked'
      const deactivatedCount = data?.DeactivatedCount || 0
      
      if (variables && deactivatedCount > 0) {
        showMessage('success', `User requests ${action}. ${deactivatedCount} active sessions were terminated.`)
      } else {
        showMessage('success', `User requests ${action} successfully`)
      }
      
      // Invalidate relevant queries
      queryClient.invalidateQueries({ queryKey: ['company'] })
      queryClient.invalidateQueries({ queryKey: ['users'] })
    },
    onError: () => {
      showMessage('error', 'Failed to update user request blocking status')
    }
  })
}

// Get all company vaults for export
export const useGetCompanyVaults = () => {
  return useQuery({
    queryKey: ['company-all-vaults'],
    queryFn: async () => {
      const response = await apiClient.get('/GetCompanyVaults')
      
      // The main vault data is in table[1]
      const allVaults = response.resultSets[1]?.data || []
      
      // The bridges with RequestToken info is in table[2]
      const bridgesWithRequestToken = response.resultSets[2]?.data || []
      
      // Dynamically organize vaults by entity type
      const vaultsByType: Record<string, any[]> = {}
      
      allVaults.forEach((vault: any) => {
        const entityType = vault.entityType
        if (entityType) {
          // Create a key based on entity type (e.g., "User" -> "users", "Company" -> "company")
          const key = entityType.charAt(0).toLowerCase() + entityType.slice(1) + (entityType === 'Company' ? '' : 's')
          
          if (!vaultsByType[key]) {
            vaultsByType[key] = []
          }
          vaultsByType[key].push(vault)
        }
      })
      
      // Return dynamic structure with bridgesWithRequestToken as a special case
      return {
        ...vaultsByType,
        bridgesWithRequestToken,
        allVaults // Include raw data for maximum flexibility
      }
    },
    enabled: false // Only fetch when manually triggered
  })
}

// Update all company vaults with new master password
export const useUpdateCompanyVaults = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (vaultUpdates: any[]) => {
      const response = await apiClient.post('/UpdateCompanyVaults', {
        updates: JSON.stringify(vaultUpdates)  // Renamed to 'updates' to avoid automatic encryption
      })
      return response.resultSets[0]?.data[0]
    },
    onSuccess: (data) => {
      const result = data?.Result || {}
      const totalUpdated = result.TotalUpdated || 0
      const failedCount = result.FailedCount || 0
      
      if (failedCount > 0) {
        const message = i18n.t('system:dangerZone.updateMasterPassword.error.partialSuccess', {
          updated: totalUpdated,
          failed: failedCount
        })
        showMessage('error', message)
      }
      // Success toast removed - handled by modal in SystemPage
      
      // Invalidate all queries to refresh data
      queryClient.invalidateQueries()
    },
    onError: (error: any) => {
      // Show the actual error message from the API response
      const errorMessage = error?.message || i18n.t('system:dangerZone.updateMasterPassword.error.updateFailed')
      showMessage('error', errorMessage)
    }
  })
}

// Export company data
export const useExportCompanyData = () => {
  return useQuery({
    queryKey: ['company-export-data'],
    queryFn: async () => {
      const response = await apiClient.get('/ExportCompanyData')
      // The export data is in table[1]
      const exportData = response.resultSets[1]?.data[0]
      
      if (!exportData) {
        throw new Error('No export data returned')
      }
      
      return exportData
    },
    enabled: false // Only fetch when manually triggered
  })
}

// Import company data
export const useImportCompanyData = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (params: { companyDataJson: string; importMode?: 'skip' | 'override' }) => {
      const response = await apiClient.post('/ImportCompanyData', {
        companyDataJson: params.companyDataJson,
        importMode: params.importMode || 'skip'
      })
      return response.resultSets[0]?.data[0]
    },
    onSuccess: (data) => {
      const importedCount = data?.ImportedCount || 0
      const skippedCount = data?.SkippedCount || 0
      const errorCount = data?.ErrorCount || 0
      
      let message = `Import completed: ${importedCount} items imported`
      if (skippedCount > 0) {
        message += `, ${skippedCount} items skipped`
      }
      if (errorCount > 0) {
        message += `, ${errorCount} errors`
      }
      
      showMessage('success', message)
      
      // Invalidate all queries to refresh data
      queryClient.invalidateQueries()
    },
    onError: (error: any) => {
      const errorMessage = error?.message || 'Failed to import company data'
      showMessage('error', errorMessage)
    }
  })
}