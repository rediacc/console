import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import { QUERY_KEYS, QUERY_KEY_STRINGS } from '@/api/queryKeys';
import {
  createResourceMutation,
  createVaultUpdateMutation,
  createMutation,
} from '@/hooks/api/mutationFactory';
import type { Team, TeamMember } from '@rediacc/shared/types';

// Get all teams
export const useTeams = () => {
  return useQuery<Team[]>({
    queryKey: QUERY_KEYS.teams.all,
    queryFn: async () => {
      return api.teams.list();
    },
    staleTime: 30 * 1000, // 30 seconds
  });
};

// Get team members
export const useTeamMembers = (teamName: string) => {
  return useQuery<TeamMember[]>({
    queryKey: QUERY_KEYS.teams.members(teamName),
    queryFn: async () => {
      return api.teams.getMembers(teamName);
    },
    enabled: !!teamName,
  });
};

export type { Team, TeamMember };

// Create team
export const useCreateTeam = createResourceMutation<{ teamName: string; vaultContent?: string }>(
  'Team',
  'create',
  (variables) => api.teams.create(variables.teamName, variables.vaultContent),
  'teamName'
);

// Update team name
export const useUpdateTeamName = createMutation<{ currentTeamName: string; newTeamName: string }>({
  request: ({ currentTeamName, newTeamName }) => api.teams.rename(currentTeamName, newTeamName),
  invalidateKeys: [QUERY_KEY_STRINGS.teams, QUERY_KEY_STRINGS.dropdown],
  successMessage: (variables) => `Team renamed to "${variables.newTeamName}"`,
  errorMessage: 'Failed to update team name',
  operationName: 'teams.rename',
});

// Update team vault
export const useUpdateTeamVault = createVaultUpdateMutation<{
  teamName: string;
  vaultContent: string;
  vaultVersion: number;
}>(
  'Team',
  (data) => api.teams.updateVault(data.teamName, data.vaultContent, data.vaultVersion),
  'teamName',
  'vaultContent'
);

// Delete team
export const useDeleteTeam = createMutation<string>({
  request: (teamName) => api.teams.delete(teamName),
  invalidateKeys: [QUERY_KEY_STRINGS.teams, QUERY_KEY_STRINGS.dropdown],
  successMessage: (teamName) => `Team "${teamName}" deleted successfully`,
  errorMessage: 'Failed to delete team',
  operationName: 'teams.delete',
});

// Add team member
export const useAddTeamMember = createMutation<{ teamName: string; newUserEmail: string }>({
  request: ({ teamName, newUserEmail }) => api.teams.addMember(teamName, newUserEmail),
  invalidateKeys: (variables) => [QUERY_KEY_STRINGS.teamMembers, variables.teamName],
  successMessage: (variables) => `User "${variables.newUserEmail}" added to team`,
  errorMessage: 'Failed to add team member',
  operationName: 'teams.addMember',
});

// Remove team member
export const useRemoveTeamMember = createMutation<{ teamName: string; removeUserEmail: string }>({
  request: ({ teamName, removeUserEmail }) => api.teams.removeMember(teamName, removeUserEmail),
  invalidateKeys: (variables) => [QUERY_KEY_STRINGS.teamMembers, variables.teamName],
  successMessage: (variables) => `User "${variables.removeUserEmail}" removed from team`,
  errorMessage: 'Failed to remove team member',
  operationName: 'teams.removeMember',
});
