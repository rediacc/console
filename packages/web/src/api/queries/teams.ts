import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import { QUERY_KEY_STRINGS, QUERY_KEYS } from '@/api/queryKeys';
import { useMutationWithFeedback } from '@/hooks/useMutationWithFeedback';
import { minifyJSON } from '@/utils/json';
import type {
  CreateTeamMembershipParams,
  CreateTeamParams,
  DeleteTeamParams,
  DeleteUserFromTeamParams,
  GetCompanyTeams_ResultSet1,
  GetTeamMembers_ResultSet1,
  UpdateTeamNameParams,
  UpdateTeamVaultParams,
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
export const useCreateTeam = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, WithOptionalVault<CreateTeamParams>>({
    mutationFn: (params) =>
      api.teams.create({
        ...params,
        vaultContent: params.vaultContent || '{}',
      }),
    successMessage: (_, vars) => `Team "${vars.teamName}" created successfully`,
    errorMessage: 'Failed to create team',
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [QUERY_KEY_STRINGS.teams] });
    },
  });
};

// Update team name
export const useUpdateTeamName = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, UpdateTeamNameParams>({
    mutationFn: (params) => api.teams.rename(params),
    successMessage: (_, vars) => `Team renamed to "${vars.newTeamName}"`,
    errorMessage: 'Failed to update team name',
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [QUERY_KEY_STRINGS.teams] });
      queryClient.invalidateQueries({ queryKey: [QUERY_KEY_STRINGS.dropdown] });
    },
  });
};

// Update team vault
export const useUpdateTeamVault = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, UpdateTeamVaultParams & Record<string, unknown>>({
    mutationFn: (params) =>
      api.teams.updateVault({
        ...params,
        vaultContent: minifyJSON(params.vaultContent),
      }),
    successMessage: (_, vars) => `Team "${vars.teamName}" vault updated successfully`,
    errorMessage: 'Failed to update team vault',
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [QUERY_KEY_STRINGS.teams] });
    },
  });
};

// Delete team
export const useDeleteTeam = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, DeleteTeamParams>({
    mutationFn: (params) => api.teams.delete(params),
    successMessage: (_, vars) => `Team "${vars.teamName}" deleted successfully`,
    errorMessage: 'Failed to delete team',
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [QUERY_KEY_STRINGS.teams] });
      queryClient.invalidateQueries({ queryKey: [QUERY_KEY_STRINGS.dropdown] });
    },
  });
};

// Add team member
export const useAddTeamMember = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, CreateTeamMembershipParams>({
    mutationFn: (params) => api.teams.addMember(params),
    successMessage: (_, vars) => `User "${vars.newUserEmail}" added to team`,
    errorMessage: 'Failed to add team member',
    onSuccess: (_, vars) => {
      queryClient.invalidateQueries({ queryKey: [QUERY_KEY_STRINGS.teamMembers, vars.teamName] });
    },
  });
};

// Remove team member
export const useRemoveTeamMember = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, DeleteUserFromTeamParams>({
    mutationFn: (params) => api.teams.removeMember(params),
    successMessage: (_, vars) => `User "${vars.removeUserEmail}" removed from team`,
    errorMessage: 'Failed to remove team member',
    onSuccess: (_, vars) => {
      queryClient.invalidateQueries({ queryKey: [QUERY_KEY_STRINGS.teamMembers, vars.teamName] });
    },
  });
};
