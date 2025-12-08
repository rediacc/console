import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import { QUERY_KEYS, QUERY_KEY_STRINGS } from '@/api/queryKeys';
import {
  createResourceMutation,
  createVaultUpdateMutation,
  createMutation,
} from '@/hooks/api/mutationFactory';
import type {
  GetCompanyTeams_ResultSet1,
  GetTeamMembers_ResultSet1,
  CreateTeamParams,
  UpdateTeamNameParams,
  UpdateTeamVaultParams,
  DeleteTeamParams,
  CreateTeamMembershipParams,
  DeleteUserFromTeamParams,
  WithOptionalVault,
} from '@rediacc/shared/types';

// Get all teams
export const useTeams = () => {
  return useQuery<GetCompanyTeams_ResultSet1[]>({
    queryKey: QUERY_KEYS.teams.all,
    queryFn: async () => {
      return api.teams.list();
    },
    staleTime: 30 * 1000, // 30 seconds
  });
};

// Get team members
export const useTeamMembers = (teamName: string) => {
  return useQuery<GetTeamMembers_ResultSet1[]>({
    queryKey: QUERY_KEYS.teams.members(teamName),
    queryFn: async () => {
      return api.teams.getMembers({ teamName });
    },
    enabled: !!teamName,
  });
};

export type {
  GetCompanyTeams_ResultSet1,
  GetCompanyTeams_ResultSet1 as Team,
  GetTeamMembers_ResultSet1,
  GetTeamMembers_ResultSet1 as TeamMember,
};

// Create team
export const useCreateTeam = createResourceMutation<WithOptionalVault<CreateTeamParams>>(
  'Team',
  'create',
  (params) => api.teams.create(params),
  'teamName'
);

// Update team name
export const useUpdateTeamName = createMutation<UpdateTeamNameParams>({
  request: (params) => api.teams.rename(params),
  invalidateKeys: [QUERY_KEY_STRINGS.teams, QUERY_KEY_STRINGS.dropdown],
  successMessage: (variables) => `Team renamed to "${variables.newTeamName}"`,
  errorMessage: 'Failed to update team name',
  operationName: 'teams.rename',
});

// Update team vault
export const useUpdateTeamVault = createVaultUpdateMutation<
  UpdateTeamVaultParams & Record<string, unknown>
>('Team', (params) => api.teams.updateVault(params), 'teamName', 'vaultContent');

// Delete team
export const useDeleteTeam = createMutation<DeleteTeamParams>({
  request: (params) => api.teams.delete(params),
  invalidateKeys: [QUERY_KEY_STRINGS.teams, QUERY_KEY_STRINGS.dropdown],
  successMessage: (params) => `Team "${params.teamName}" deleted successfully`,
  errorMessage: 'Failed to delete team',
  operationName: 'teams.delete',
});

// Add team member
export const useAddTeamMember = createMutation<CreateTeamMembershipParams>({
  request: (params) => api.teams.addMember(params),
  invalidateKeys: (variables) => [QUERY_KEY_STRINGS.teamMembers, variables.teamName],
  successMessage: (variables) => `User "${variables.newUserEmail}" added to team`,
  errorMessage: 'Failed to add team member',
  operationName: 'teams.addMember',
});

// Remove team member
export const useRemoveTeamMember = createMutation<DeleteUserFromTeamParams>({
  request: (params) => api.teams.removeMember(params),
  invalidateKeys: (variables) => [QUERY_KEY_STRINGS.teamMembers, variables.teamName],
  successMessage: (variables) => `User "${variables.removeUserEmail}" removed from team`,
  errorMessage: 'Failed to remove team member',
  operationName: 'teams.removeMember',
});
