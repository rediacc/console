import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/client'
import { showMessage } from '@/utils/messages'
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
      const vaultData = response.tables[0]?.data[0]
      
      if (!vaultData) {
        return { vault: '{}', vaultVersion: 1 }
      }
      
      return {
        vault: vaultData.VaultContent || vaultData.vault || '{}',
        vaultVersion: vaultData.VaultVersion || vaultData.vaultVersion || 1
      }
    },
    enabled: !!company
  })
}

// Update company vault configuration
export const useUpdateCompanyVault = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (data: { companyVault: string; vaultVersion: number }) => {
      // Minify the vault JSON before sending
      const minifiedData = {
        ...data,
        companyVault: minifyJSON(data.companyVault)
      }
      const response = await apiClient.post('/UpdateCompanyVault', minifiedData)
      return response.tables[0]?.data[0]
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['company-vault'] })
      showMessage('success', 'Vault configuration updated successfully')
    },
    onError: (error: any) => {
      console.error('Failed to update vault:', error)
      showMessage('error', 'Failed to update vault configuration')
    }
  })
}

// Block or unblock user requests
export const useUpdateCompanyBlockUserRequests = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (blockUserRequests: boolean) => {
      const response = await apiClient.post('/UpdateCompanyBlockUserRequests', {
        blockUserRequests
      })
      return response.tables[0]?.data[0]
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
    onError: (error: any) => {
      console.error('Failed to update block user requests:', error)
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
      const allVaults = response.tables[1]?.data || []
      
      // The bridges with RequestCredential info is in table[2]
      const bridgesWithRequestCredential = response.tables[2]?.data || []
      
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
      
      // Return dynamic structure with bridgesWithRequestCredential as a special case
      return {
        ...vaultsByType,
        bridgesWithRequestCredential,
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
      return response.tables[0]?.data[0]
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
      console.error('Failed to update vaults:', error)
      // Show the actual error message from the API response
      const errorMessage = error?.message || i18n.t('system:dangerZone.updateMasterPassword.error.updateFailed')
      showMessage('error', errorMessage)
    }
  })
}