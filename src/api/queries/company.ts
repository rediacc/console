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
  maxRegions: number
  maxBridges: number
  currentUsers: number
  currentTeams: number
  currentMachines: number
  currentRepositories: number
  currentStorage: number
  currentSchedules: number
  currentRegions: number
  currentBridges: number
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
      
      // Log the raw response for debugging
      console.log('GetCompanyResourceLimits raw response:', response)
      
      // Transform the first result set (resource limits by type) into our expected format
      const resourceData = response.tables[0]?.data || []
      
      // If no data, return mock data for development
      if (resourceData.length === 0) {
        console.warn('No resource limits data returned, using defaults')
        return {
          maxUsers: 10,
          maxTeams: 10,
          maxMachines: 50,
          maxRepositories: 25,
          maxStorage: 25,
          maxSchedules: 5,
          maxRegions: 5,
          maxBridges: 15,
          currentUsers: 2,
          currentTeams: 3,
          currentMachines: 12,
          currentRepositories: 8,
          currentStorage: 5,
          currentSchedules: 2,
          currentRegions: 1,
          currentBridges: 3,
        } as ResourceLimits
      }
      
      const limits: ResourceLimits = {
        maxUsers: 0,
        maxTeams: 0,
        maxMachines: 0,
        maxRepositories: 0,
        maxStorage: 0,
        maxSchedules: 0,
        maxRegions: 0,
        maxBridges: 0,
        currentUsers: 0,
        currentTeams: 0,
        currentMachines: 0,
        currentRepositories: 0,
        currentStorage: 0,
        currentSchedules: 0,
        currentRegions: 0,
        currentBridges: 0,
      }
      
      // Map each resource type to the appropriate property
      resourceData.forEach((resource: any) => {
        const type = resource.ResourceType
        const current = resource.CurrentUsage || 0
        const max = resource.ResourceLimit || 0
        
        switch (type) {
          case 'User':
            limits.currentUsers = current
            limits.maxUsers = max
            break
          case 'Team':
            limits.currentTeams = current
            limits.maxTeams = max
            break
          case 'Machine':
            limits.currentMachines = current
            limits.maxMachines = max
            break
          case 'Repo':
            limits.currentRepositories = current
            limits.maxRepositories = max
            break
          case 'Storage':
            limits.currentStorage = current
            limits.maxStorage = max
            break
          case 'Schedule':
            limits.currentSchedules = current
            limits.maxSchedules = max
            break
          case 'Region':
            limits.currentRegions = current
            limits.maxRegions = max
            break
          case 'Bridge':
            limits.currentBridges = current
            limits.maxBridges = max
            break
        }
      })
      
      return limits
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

// Generate mock usage data for the last 6 months
function generateMockUsageData() {
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun']
  return months.map((month, index) => ({
    month,
    users: Math.floor(Math.random() * 5) + index + 1,
    teams: Math.floor(Math.random() * 3) + index,
    machines: Math.floor(Math.random() * 10) + index * 2,
    repositories: Math.floor(Math.random() * 5) + index,
  }))
}

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