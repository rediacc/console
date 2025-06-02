import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/client'
import toast from 'react-hot-toast'
import { useAppSelector } from '@/store/store'
import { selectCompany } from '@/store/auth/authSelectors'

export interface SubscriptionDetails {
  subscriptionPlan: string
  planDescription: string
  startDate: string
  endDate: string
  status: string
  features: string[]
}

export interface ResourceLimits {
  maxUsers: number
  maxTeams: number
  maxMachines: number
  maxRepositories: number
  maxStorage: number
  maxSchedules: number
  currentUsers: number
  currentTeams: number
  currentMachines: number
  currentRepositories: number
  currentStorage: number
  currentSchedules: number
}

export interface SubscriptionAnalytics {
  usageOverTime: Array<{
    month: string
    users: number
    teams: number
    machines: number
    repositories: number
  }>
  costBreakdown: Array<{
    category: string
    amount: number
  }>
  projectedCost: number
}

// Get subscription details
export const useSubscriptionDetails = () => {
  return useQuery({
    queryKey: ['subscription-details'],
    queryFn: async () => {
      const response = await apiClient.get('/GetSubscriptionDetails')
      const data = response.tables[1]?.data[0] || {}
      
      // Mock some additional data for now
      return {
        ...data,
        features: [
          'Unlimited backup storage',
          'Advanced security features',
          'Priority support',
          '99.9% SLA',
          'Custom integrations'
        ]
      } as SubscriptionDetails
    },
  })
}

// Get resource limits
export const useResourceLimits = () => {
  return useQuery({
    queryKey: ['resource-limits'],
    queryFn: async () => {
      const response = await apiClient.get('/GetCompanyResourceLimits')
      return response.tables[1]?.data[0] || {} as ResourceLimits
    },
  })
}

// Get subscription analytics
export const useSubscriptionAnalytics = () => {
  return useQuery({
    queryKey: ['subscription-analytics'],
    queryFn: async () => {
      // Mock data for analytics since endpoint might not exist
      const analytics: SubscriptionAnalytics = {
        usageOverTime: generateMockUsageData(),
        costBreakdown: [
          { category: 'Base Plan', amount: 499 },
          { category: 'Additional Users', amount: 150 },
          { category: 'Extra Storage', amount: 89 },
          { category: 'Premium Support', amount: 199 },
        ],
        projectedCost: 937
      }
      
      return analytics
    },
  })
}

// Update company vault
export const useUpdateCompanyVault = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (data: { companyVault: string; vaultVersion: number }) => {
      const response = await apiClient.put('/UpdateCompanyVault', data)
      return response
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['company'] })
      toast.success('Company vault updated successfully')
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to update company vault')
    },
  })
}

// Get company vault
export const useCompanyVault = () => {
  const company = useAppSelector(selectCompany)
  
  return useQuery({
    queryKey: ['company-vault'],
    queryFn: async () => {
      // The vault is typically part of the company data
      return {
        vault: company?.companyVault || '{}',
        vaultVersion: company?.vaultVersion || 1
      }
    },
  })
}

// Helper function to generate mock usage data
function generateMockUsageData() {
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun']
  return months.map((month, index) => ({
    month,
    users: 10 + index * 2,
    teams: 3 + Math.floor(index / 2),
    machines: 15 + index * 3,
    repositories: 20 + index * 4,
  }))
}