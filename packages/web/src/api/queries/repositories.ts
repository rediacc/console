import { useQueryClient } from '@tanstack/react-query';
import { typedApi } from '@/api/client';
import { createResourceQuery } from '@/hooks/api/queryFactory';
import { useMutationWithFeedback } from '@/hooks/useMutationWithFeedback';
import { minifyJSON } from '@/platform/utils/json';
import { parseGetTeamRepositories } from '@rediacc/shared/api';
import type {
  CreateRepositoryParams,
  DeleteRepositoryParams,
  GetTeamRepositories_ResultSet1,
  PromoteRepositoryToGrandParams,
  UpdateRepositoryNameParams,
  UpdateRepositoryTagParams,
  UpdateRepositoryVaultParams,
} from '@rediacc/shared/types';

// Get repositories for a team or multiple teams
export const useRepositories = createResourceQuery<GetTeamRepositories_ResultSet1>({
  queryKey: 'repositories',
  fetcher: async (teamFilter) => {
    if (!teamFilter) {
      throw new Error('Team filter is required to load repositories');
    }
    const teamName = Array.isArray(teamFilter) ? teamFilter.join(',') : teamFilter;
    const response = await typedApi.GetTeamRepositories({ teamName });
    return parseGetTeamRepositories(response as never);
  },
  enabledCheck: (teamFilter) =>
    !!teamFilter && (!Array.isArray(teamFilter) || teamFilter.length > 0),
  operationName: 'repositories.list',
});

// Create repository - uses custom type until service is refactored
type CreateRepositoryHookParams = Pick<CreateRepositoryParams, 'teamName' | 'repositoryName'> & {
  repositoryTag?: string;
  vaultContent?: string;
  parentRepositoryName?: string;
  repositoryGuid?: string;
};

export const useCreateRepository = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, CreateRepositoryHookParams>({
    mutationFn: ({
      teamName,
      repositoryName,
      repositoryTag = 'latest',
      vaultContent = '{}',
      parentRepositoryName,
      repositoryGuid,
    }) =>
      typedApi.CreateRepository({
        teamName,
        repositoryName,
        repositoryTag,
        vaultContent,
        parentRepositoryName,
        repositoryGuid,
      }),
    successMessage: (_, vars) =>
      `Repository "${vars.repositoryName}:${vars.repositoryTag ?? 'latest'}" created successfully`,
    errorMessage: 'Failed to create repository',
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['repositories'] });
      void queryClient.invalidateQueries({ queryKey: ['teams'] });
      void queryClient.invalidateQueries({ queryKey: ['machines'] });
    },
  });
};

// Update repository name
export const useUpdateRepositoryName = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, UpdateRepositoryNameParams>({
    mutationFn: (params) => typedApi.UpdateRepositoryName(params),
    successMessage: (_, vars) => `Repository renamed to "${vars.newRepositoryName}"`,
    errorMessage: 'Failed to update repository name',
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['repositories'] });
      void queryClient.invalidateQueries({ queryKey: ['machines'] });
    },
  });
};

// Update repository tag
export const useUpdateRepositoryTag = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, UpdateRepositoryTagParams>({
    mutationFn: (params) => typedApi.UpdateRepositoryTag(params),
    successMessage: (_, vars) => `Tag renamed to "${vars.newTag}"`,
    errorMessage: 'Failed to update tag',
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['repositories'] });
      void queryClient.invalidateQueries({ queryKey: ['machines'] });
    },
  });
};

// Update repository vault
export const useUpdateRepositoryVault = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, UpdateRepositoryVaultParams>({
    mutationFn: (params) =>
      typedApi.UpdateRepositoryVault({
        ...params,
        vaultContent: minifyJSON(params.vaultContent),
      }),
    successMessage: (_, vars) => `Repository vault updated for "${vars.repositoryName}"`,
    errorMessage: 'Failed to update repository vault',
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['repositories'] });
    },
  });
};

// Delete repository - uses custom type to match service signature with optional repositoryTag
type DeleteRepositoryHookParams = Pick<DeleteRepositoryParams, 'teamName' | 'repositoryName'> & {
  repositoryTag?: string;
};

export const useDeleteRepository = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, DeleteRepositoryHookParams>({
    mutationFn: ({ teamName, repositoryName, repositoryTag = 'latest' }) =>
      typedApi.DeleteRepository({ teamName, repositoryName, repositoryTag }),
    successMessage: (_, vars) =>
      `Repository "${vars.repositoryName}:${vars.repositoryTag ?? 'latest'}" deleted successfully`,
    errorMessage: 'Failed to delete repository',
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['repositories'] });
      void queryClient.invalidateQueries({ queryKey: ['teams'] });
      void queryClient.invalidateQueries({ queryKey: ['machines'] });
    },
  });
};

// Promote repository to grand (convert clone to original)
export const usePromoteRepositoryToGrand = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, PromoteRepositoryToGrandParams>({
    mutationFn: (params) => typedApi.PromoteRepositoryToGrand(params),
    successMessage: (_, vars) =>
      `Repository "${vars.repositoryName}" promoted to original successfully`,
    errorMessage: 'Failed to promote repository',
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['repositories'] });
    },
  });
};

export type {
  GetTeamRepositories_ResultSet1,
  GetTeamRepositories_ResultSet1 as Repository,
} from '@rediacc/shared/types';
