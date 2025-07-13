import { useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/client'
import { showMessage } from '@/utils/messages'
import { useAppSelector, useAppDispatch } from '@/store/store'
import { selectCompany } from '@/store/auth/authSelectors'
import { setVaultCompany } from '@/store/auth/authSlice'
import { createVaultCompanySentinel } from '@/utils/vaultProtocol'

/**
 * Enable vault encryption for a company by setting VaultCompany
 * This should be called when the company admin first sets up encryption
 */
export const useEnableCompanyEncryption = () => {
  const queryClient = useQueryClient()
  const dispatch = useAppDispatch()
  const company = useAppSelector(selectCompany)
  
  return useMutation({
    mutationFn: async (masterPassword: string) => {
      if (!company) {
        throw new Error('No company selected')
      }
      
      // Create the encrypted sentinel value
      const encryptedSentinel = await createVaultCompanySentinel(company, masterPassword)
      
      // Update VaultCompany in the database
      const response = await apiClient.post('/UpdateCompanyVaultProtocol', {
        vaultCompany: encryptedSentinel
      })
      
      if (response.failure !== 0) {
        throw new Error(response.errors?.join('; ') || 'Failed to enable encryption')
      }
      
      return { encryptedSentinel, company }
    },
    onSuccess: (data) => {
      // Update Redux store
      dispatch(setVaultCompany({
        vaultCompany: data.encryptedSentinel,
        companyEncryptionEnabled: true
      }))
      
      // Invalidate relevant queries
      queryClient.invalidateQueries({ queryKey: ['company-vault'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      
      showMessage('success', 'Vault encryption enabled successfully. All users must now use this master password.')
    },
    onError: (error: any) => {
      showMessage('error', error.message || 'Failed to enable vault encryption')
    }
  })
}

/**
 * Disable vault encryption for a company by clearing VaultCompany
 * This should only be allowed by company admins
 */
export const useDisableCompanyEncryption = () => {
  const queryClient = useQueryClient()
  const dispatch = useAppDispatch()
  
  return useMutation({
    mutationFn: async () => {
      // Clear VaultCompany in the database
      const response = await apiClient.post('/UpdateCompanyVaultProtocol', {
        vaultCompany: null
      })
      
      if (response.failure !== 0) {
        throw new Error(response.errors?.join('; ') || 'Failed to disable encryption')
      }
      
      return true
    },
    onSuccess: () => {
      // Update Redux store
      dispatch(setVaultCompany({
        vaultCompany: null,
        companyEncryptionEnabled: false
      }))
      
      // Invalidate relevant queries
      queryClient.invalidateQueries({ queryKey: ['company-vault'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      
      showMessage('success', 'Vault encryption disabled. Master passwords are no longer required.')
    },
    onError: (error: any) => {
      showMessage('error', error.message || 'Failed to disable vault encryption')
    }
  })
}

/**
 * Check if the current user can manage encryption settings
 * (typically only company admins)
 */
export const useCanManageEncryption = () => {
  // This would check user permissions
  // For now, we'll assume it's based on user role
  const user = useAppSelector(state => state.auth.user)
  return user?.role === 'admin' || user?.role === 'owner'
}