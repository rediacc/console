import { useQuery } from '@tanstack/react-query'
import apiClient from '@/api/client'

export interface DropdownData {
  teams: Array<{ value: string; label: string }>
  allTeams: Array<{ value: string; label: string; memberCount: number }>
  regions: Array<{ value: string; label: string; bridgeCount: number }>
  bridgesByRegion: Array<{
    regionName: string
    bridges: Array<{ value: string; label: string; machineCount: number }>
  }>
  machinesByTeam: Array<{
    teamName: string
    machines: Array<{
      value: string
      label: string
      bridgeName: string
      regionName: string
    }>
  }>
  users: Array<{ value: string; label: string; status: string }>
  permissionGroups: Array<{
    value: string
    label: string
    userCount: number
    permissionCount: number
  }>
  queueFunctions: Array<{
    category: string
    functions: Array<{
      value: string
      label: string
      description: string
    }>
  }>
  subscriptionPlans: Array<{
    value: string
    label: string
    description: string
  }>
  requestContext?: string
  currentUser?: string
  userRole?: string
}

export const useDropdownData = (context?: string) => {
  return useQuery({
    queryKey: ['dropdown-data', context],
    queryFn: async () => {
      const response = await apiClient.get<DropdownData>('/GetLookupData', 
        context ? { context } : {}
      )
      return response.tables[1]?.data[0] || {}
    },
    staleTime: 30 * 60 * 1000, // 30 minutes
    gcTime: 60 * 60 * 1000, // 1 hour
  })
}