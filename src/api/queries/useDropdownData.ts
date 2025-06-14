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
  permissions: Array<{
    name: string
    value: string
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

const DROPDOWN_FIELDS = [
  'teams', 'allTeams', 'regions', 'bridgesByRegion', 
  'machinesByTeam', 'users', 'permissionGroups', 'permissions', 'subscriptionPlans'
] as const

const EMPTY_DROPDOWN_DATA: DropdownData = DROPDOWN_FIELDS.reduce((acc, field) => ({ ...acc, [field]: [] }), {} as DropdownData)

const parseJsonField = (data: any, field: string): any => {
  if (!data[field] || typeof data[field] !== 'string') return data[field]
  try {
    return JSON.parse(data[field])
  } catch (e) {
    console.error(`Failed to parse ${field}:`, e)
    return data[field]
  }
}

const parseDropdownData = (rawData: any): DropdownData => {
  const dropdownData = typeof rawData.dropdownValues === 'string' 
    ? JSON.parse(rawData.dropdownValues) 
    : rawData.dropdownValues

  // Parse all nested JSON strings
  DROPDOWN_FIELDS.forEach(field => {
    dropdownData[field] = parseJsonField(dropdownData, field)
  })
  
  // Special handling for bridgesByRegion
  if (Array.isArray(dropdownData.bridgesByRegion)) {
    dropdownData.bridgesByRegion = dropdownData.bridgesByRegion.map((region: any) => ({
      ...region,
      bridges: parseJsonField(region, 'bridges')
    }))
  }
  
  return dropdownData as DropdownData
}

export const useDropdownData = (context?: string) => {
  return useQuery({
    queryKey: ['dropdown-data', context],
    queryFn: async () => {
      const response = await apiClient.get<any>('/GetLookupData', context ? { context } : {})
      const rawData = response.tables[1]?.data[0] ?? response.tables[0]?.data[0]
      
      if (rawData?.dropdownValues) {
        try {
          return parseDropdownData(rawData)
        } catch (e) {
          console.error('Failed to parse dropdown data:', e)
          return EMPTY_DROPDOWN_DATA
        }
      }
      
      return { ...EMPTY_DROPDOWN_DATA, ...rawData } as DropdownData
    },
    staleTime: 30 * 60 * 1000, // 30 minutes
    gcTime: 60 * 60 * 1000, // 1 hour
  })
}