import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/client'
import { showMessage } from '@/utils/messages'

export interface Team {
  teamName: string
  memberCount: number
  machineCount: number
  repoCount: number
  storageCount: number
  scheduleCount: number
  vaultVersion: number
}

export interface TeamMember {
  userEmail: string
  isMember: boolean
  hasAccess: boolean
}

// Get all teams
export const useTeams = () => {
  return useQuery({
    queryKey: ['teams'],
    queryFn: async () => {
      const response = await apiClient.get<Team[]>('/GetCompanyTeams')
      return response.tables[1]?.data || []
    },
  })
}

// Get team members
export const useTeamMembers = (teamName: string) => {
  return useQuery({
    queryKey: ['team-members', teamName],
    queryFn: async () => {
      const response = await apiClient.get<TeamMember[]>('/GetTeamMembers', { teamName })
      return response.tables[1]?.data || []
    },
    enabled: !!teamName,
  })
}

// Create team
export const useCreateTeam = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (data: { teamName: string; teamVault?: string }) => {
      const response = await apiClient.post('/CreateTeam', {
        teamName: data.teamName,
        teamVault: data.teamVault || '{}',
      })
      return response
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['teams'] })
      queryClient.invalidateQueries({ queryKey: ['dropdown-data'] })
      showMessage('success', `Team "${variables.teamName}" created successfully`)
    },
    onError: (error: any) => {
      showMessage('error', error.message || 'Failed to create team')
    },
  })
}

// Update team name
export const useUpdateTeamName = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (data: { currentTeamName: string; newTeamName: string }) => {
      const response = await apiClient.put('/UpdateTeamName', data)
      return response
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['teams'] })
      queryClient.invalidateQueries({ queryKey: ['dropdown-data'] })
      showMessage('success', `Team renamed to "${variables.newTeamName}"`)
    },
    onError: (error: any) => {
      showMessage('error', error.message || 'Failed to update team name')
    },
  })
}

// Update team vault
export const useUpdateTeamVault = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (data: { teamName: string; teamVault: string; vaultVersion: number }) => {
      const response = await apiClient.put('/UpdateTeamVault', data)
      return response
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['teams'] })
      showMessage('success', `Team vault updated for "${variables.teamName}"`)
    },
    onError: (error: any) => {
      showMessage('error', error.message || 'Failed to update team vault')
    },
  })
}

// Delete team
export const useDeleteTeam = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (teamName: string) => {
      const response = await apiClient.delete('/DeleteTeam', { teamName })
      return response
    },
    onSuccess: (_, teamName) => {
      queryClient.invalidateQueries({ queryKey: ['teams'] })
      queryClient.invalidateQueries({ queryKey: ['dropdown-data'] })
      showMessage('success', `Team "${teamName}" deleted successfully`)
    },
    onError: (error: any) => {
      showMessage('error', error.message || 'Failed to delete team')
    },
  })
}

// Add team member
export const useAddTeamMember = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (data: { teamName: string; newUserEmail: string }) => {
      const response = await apiClient.post('/CreateTeamMembership', data)
      return response
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['team-members', variables.teamName] })
      showMessage('success', `User "${variables.newUserEmail}" added to team`)
    },
    onError: (error: any) => {
      showMessage('error', error.message || 'Failed to add team member')
    },
  })
}

// Remove team member
export const useRemoveTeamMember = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (data: { teamName: string; removeUserEmail: string }) => {
      const response = await apiClient.delete('/DeleteUserFromTeam', data)
      return response
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['team-members', variables.teamName] })
      showMessage('success', `User "${variables.removeUserEmail}" removed from team`)
    },
    onError: (error: any) => {
      showMessage('error', error.message || 'Failed to remove team member')
    },
  })
}