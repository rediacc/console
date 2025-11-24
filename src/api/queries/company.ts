import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/client'
import { showMessage } from '@/utils/messages'
import { createMutation } from '@/hooks/api/mutationFactory'
import { useAppSelector } from '@/store/store'
import { selectCompany } from '@/store/auth/authSelectors'
import { minifyJSON } from '@/utils/json'
import i18n from '@/i18n/config'
import { getFirstRow, getResultSet } from '@/core/api/response'
import { createErrorHandler } from '@/utils/mutationUtils'

interface CompanyVaultRow {
  vaultContent?: string
  VaultContent?: string
  vaultVersion?: number
  VaultVersion?: number
}

interface BlockUserRequestsResponse {
  DeactivatedCount?: number
}

interface UpdateVaultsResponse {
  Result?: {
    TotalUpdated?: number
    FailedCount?: number
  }
}

interface ExportDataRow {
  [key: string]: unknown
}

interface ImportCompanyDataResult {
  ImportedCount?: number
  SkippedCount?: number
  ErrorCount?: number
}

// Get company vault configuration
export const useCompanyVault = () => {
  const company = useAppSelector(selectCompany)
  
  return useQuery({
    queryKey: ['company-vault', company],
    queryFn: async () => {
      const response = await apiClient.get('/GetCompanyVault')
      const vaultData = getFirstRow<CompanyVaultRow>(response, 1)
      
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
  successMessage: () => i18n.t('system:company.success.vaultUpdated'),
  errorMessage: i18n.t('system:company.errors.vaultUpdateFailed'),
  transformData: (data) => ({
    ...data,
    companyVault: minifyJSON(data.companyVault)
  })
})

// Block or unblock user requests - Special case with dynamic success message
export const useUpdateCompanyBlockUserRequests = () => {
  const queryClient = useQueryClient()
  const blockStatusErrorHandler = createErrorHandler(i18n.t('system:company.errors.blockRequestsFailed'))
  
  return useMutation({
    mutationFn: async (blockUserRequests: boolean) => {
      const response = await apiClient.post('/UpdateCompanyBlockUserRequests', {
        blockUserRequests,
      })
      return getFirstRow<BlockUserRequestsResponse>(response, 0)
    },
    onSuccess: (data, variables) => {
      const deactivatedCount = data?.DeactivatedCount ?? 0
      let message: string

      if (variables) {
        message = deactivatedCount > 0
          ? i18n.t('system:company.success.requestsBlockedWithTerminations', { count: deactivatedCount })
          : i18n.t('system:company.success.requestsBlocked')
      } else {
        message = i18n.t('system:company.success.requestsUnblocked')
      }

      showMessage('success', message)
      
      // Invalidate relevant queries
      queryClient.invalidateQueries({ queryKey: ['company'] })
      queryClient.invalidateQueries({ queryKey: ['users'] })
    },
    onError: blockStatusErrorHandler
  })
}

// Get all company vaults for export
export const useCompanyVaults = () => {
  return useQuery({
    queryKey: ['company-all-vaults'],
    queryFn: async () => {
      const response = await apiClient.get('/GetCompanyVaults')
      const allVaults = getResultSet<Record<string, unknown>>(response, 1)
      const bridgesWithRequestToken = getResultSet<Record<string, unknown>>(response, 2)
      
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
        updates: JSON.stringify(vaultUpdates), // Renamed to 'updates' to avoid automatic encryption
      })
      return getFirstRow<UpdateVaultsResponse>(response, 0)
    },
    onSuccess: (data) => {
      const result = data?.Result || {}
      const totalUpdated = result.TotalUpdated ?? 0
      const failedCount = result.FailedCount ?? 0
      
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
      const exportData = getFirstRow<ExportDataRow>(response, 1)
      
      if (!exportData) {
        throw new Error(i18n.t('system:company.errors.noExportData'))
      }
      
      return exportData
    },
    enabled: false // Only fetch when manually triggered
  })
}

// Import company data
export const useImportCompanyData = () => {
  const queryClient = useQueryClient()
  const importErrorHandler = createErrorHandler(i18n.t('system:company.errors.importFailed'))
  
  return useMutation({
    mutationFn: async (params: { companyDataJson: string; importMode?: 'skip' | 'override' }) => {
      const response = await apiClient.post('/ImportCompanyData', {
        companyDataJson: params.companyDataJson,
        importMode: params.importMode || 'skip',
      })
      return getFirstRow<ImportCompanyDataResult>(response, 0)
    },
    onSuccess: (data) => {
      const importedCount = data?.ImportedCount ?? 0
      const skippedCount = data?.SkippedCount ?? 0
      const errorCount = data?.ErrorCount ?? 0

      const parts = [
        i18n.t('system:company.success.importedCount', { count: importedCount }),
        skippedCount > 0 ? i18n.t('system:company.success.skippedCount', { count: skippedCount }) : null,
        errorCount > 0 ? i18n.t('system:company.success.errorCount', { count: errorCount }) : null
      ].filter(Boolean)

      showMessage('success', i18n.t('system:company.success.importComplete', { summary: parts.join(', ') }))
      
      // Invalidate all queries to refresh data
      queryClient.invalidateQueries()
    },
    onError: importErrorHandler
  })
}
