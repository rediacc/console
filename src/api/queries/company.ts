import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/client'
import toast from 'react-hot-toast'
import { useAppSelector } from '@/store/store'
import { selectCompany } from '@/store/auth/authSelectors'

// Get company vault configuration
export const useCompanyVault = () => {
  const company = useAppSelector(selectCompany)
  
  return useQuery({
    queryKey: ['company-vault', company?.companyId],
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
    enabled: !!company?.companyId
  })
}

// Update company vault configuration
export const useUpdateCompanyVault = () => {
  const queryClient = useQueryClient()
  const company = useAppSelector(selectCompany)
  
  return useMutation({
    mutationFn: async (data: { companyVault: string; vaultVersion: number }) => {
      const response = await apiClient.post('/UpdateCompanyVault', data)
      return response.tables[0]?.data[0]
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['company-vault'] })
      toast.success('Vault configuration updated successfully')
    },
    onError: (error: any) => {
      console.error('Failed to update vault:', error)
      toast.error('Failed to update vault configuration')
    }
  })
}