import { useQuery } from '@tanstack/react-query'
import apiClient from '@/api/client'
import { createResourceMutation, createVaultUpdateMutation, createMutation } from '@/api/utils/mutationFactory'
import { extractResourceData, extractTableData } from '@/api/utils/responseHelpers'

export interface Team {
  teamName: string
  memberCount: number
  machineCount: number
  repoCount: number
  storageCount: number
  vaultContent?: string
  vaultVersion: number
}

export interface TeamMember {
  userEmail: string
  isMember: boolean
  hasAccess: boolean
}

// Get all teams
export const useTeams = () => {
  return useQuery<Team[]>({
    queryKey: ['teams'],
    queryFn: async () => {
      const response = await apiClient.get('/GetCompanyTeams')
      return extractResourceData<Team>(response, 'teamName')
    },
    staleTime: 30 * 1000, // 30 seconds
  })
}

// Get team members
export const useTeamMembers = (teamName: string) => {
  return useQuery({
    queryKey: ['team-members', teamName],
    queryFn: async () => {
      const response = await apiClient.get('/GetTeamMembers', { teamName })
      return extractTableData(response, 1, [])
    },
    enabled: !!teamName,
  })
}

// Create team
export const useCreateTeam = createResourceMutation<{ teamName: string; teamVault?: string }>(
  'Team', 'create', '/CreateTeam', 'teamName'
)

// Update team name
export const useUpdateTeamName = createMutation<{ currentTeamName: string; newTeamName: string }>({
  endpoint: '/UpdateTeamName',
  method: 'put',
  invalidateKeys: ['teams', 'dropdown-data'],
  successMessage: (variables) => `Team renamed to "${variables.newTeamName}"`,
  errorMessage: 'Failed to update team name'
})

// Update team vault
export const useUpdateTeamVault = createVaultUpdateMutation<{ teamName: string; teamVault: string; vaultVersion: number }>(
  'Team', '/UpdateTeamVault', 'teamName', 'teamVault'
)

// Delete team
export const useDeleteTeam = createMutation<string>({
  endpoint: '/DeleteTeam',
  method: 'delete',
  invalidateKeys: ['teams', 'dropdown-data'],
  successMessage: (teamName) => `Team "${teamName}" deleted successfully`,
  errorMessage: 'Failed to delete team',
  transformData: (teamName) => ({ teamName })
})

// Add team member
export const useAddTeamMember = createMutation<{ teamName: string; newUserEmail: string }>({
  endpoint: '/CreateTeamMembership',
  method: 'post',
  invalidateKeys: (variables) => ['team-members', variables.teamName],
  successMessage: (variables) => `User "${variables.newUserEmail}" added to team`,
  errorMessage: 'Failed to add team member'
})

// Remove team member
export const useRemoveTeamMember = createMutation<{ teamName: string; removeUserEmail: string }>({
  endpoint: '/DeleteUserFromTeam',
  method: 'delete',
  invalidateKeys: (variables) => ['team-members', variables.teamName],
  successMessage: (variables) => `User "${variables.removeUserEmail}" removed from team`,
  errorMessage: 'Failed to remove team member'
})