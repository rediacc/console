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

export const useDropdownData = (context?: string) => {
  return useQuery({
    queryKey: ['dropdown-data', context],
    queryFn: async () => {
      const response = await apiClient.get<any>('/GetLookupData', 
        context ? { context } : {}
      )
      
      // The stored procedure returns data wrapped in a 'dropdownValues' field as JSON string
      const rawData = response.tables[1]?.data[0] || response.tables[0]?.data[0];
      if (rawData?.dropdownValues) {
        try {
          // Parse the JSON string if it's a string
          const dropdownData = typeof rawData.dropdownValues === 'string' 
            ? JSON.parse(rawData.dropdownValues) 
            : rawData.dropdownValues;
          
          // Parse all nested JSON strings
          const fieldsToParser = [
            'teams', 'allTeams', 'regions', 'bridgesByRegion', 
            'machinesByTeam', 'users', 'permissionGroups', 'permissions', 'subscriptionPlans'
          ];
          
          fieldsToParser.forEach(field => {
            if (dropdownData[field] && typeof dropdownData[field] === 'string') {
              try {
                dropdownData[field] = JSON.parse(dropdownData[field]);
              } catch (e) {
                console.error(`Failed to parse ${field}:`, e);
              }
            }
          });
          
          // Special handling for bridgesByRegion which has nested bridges as JSON strings
          if (dropdownData.bridgesByRegion && Array.isArray(dropdownData.bridgesByRegion)) {
            dropdownData.bridgesByRegion = dropdownData.bridgesByRegion.map((region: any) => ({
              ...region,
              bridges: typeof region.bridges === 'string' 
                ? JSON.parse(region.bridges) 
                : region.bridges
            }));
          }
          
          return dropdownData as DropdownData;
        } catch (e) {
          console.error('Failed to parse dropdown data:', e);
          // Return structure with empty arrays on parse error
          return {
            teams: [],
            allTeams: [],
            regions: [],
            bridgesByRegion: [],
            machinesByTeam: [],
            users: [],
            permissionGroups: [],
            permissions: [],
            subscriptionPlans: []
          } as DropdownData;
        }
      }
      
      // Fallback to direct data if no dropdownValues field
      const fallbackData = response.tables[1]?.data[0] || response.tables[0]?.data[0] || {};
      
      // Ensure all arrays exist with empty defaults
      return {
        teams: [],
        allTeams: [],
        regions: [],
        bridgesByRegion: [],
        machinesByTeam: [],
        users: [],
        permissionGroups: [],
        permissions: [],
        subscriptionPlans: [],
        ...fallbackData
      } as DropdownData;
    },
    staleTime: 30 * 60 * 1000, // 30 minutes
    gcTime: 60 * 60 * 1000, // 1 hour
  })
}