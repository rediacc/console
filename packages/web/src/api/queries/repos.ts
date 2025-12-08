import { api } from '@/api/client';
import { createMutation } from '@/hooks/api/mutationFactory';
import { createResourceQuery } from '@/hooks/api/queryFactory';
import { minifyJSON } from '@/utils/json';
import type {
  CreateRepositoryParams,
  DeleteRepositoryParams,
  GetTeamRepositories_ResultSet1,
  PromoteRepositoryToGrandParams,
  UpdateRepositoryNameParams,
  UpdateRepositoryTagParams,
  UpdateRepositoryVaultParams,
} from '@rediacc/shared/types';

// Get repos for a team or multiple teams
export const useRepos = createResourceQuery<GetTeamRepositories_ResultSet1>({
  queryKey: 'repos',
  fetcher: (teamFilter) => {
    if (!teamFilter) {
      throw new Error('Team filter is required to load repositories');
    }
    return api.repos.list(
      Array.isArray(teamFilter) ? { teamName: teamFilter } : { teamName: teamFilter }
    );
  },
  enabledCheck: (teamFilter) =>
    !!teamFilter && (!Array.isArray(teamFilter) || teamFilter.length > 0),
  operationName: 'repos.list',
});

// Create repo - uses custom type until service is refactored
type CreateRepoHookParams = Pick<CreateRepositoryParams, 'teamName' | 'repoName'> & {
  repoTag?: string;
  vaultContent?: string;
  parentRepoName?: string;
  repoGuid?: string;
};

export const useCreateRepo = createMutation<CreateRepoHookParams>({
  request: ({ teamName, repoName, repoTag, vaultContent, parentRepoName, repoGuid }) =>
    api.repos.create(teamName, repoName, {
      repoTag,
      vaultContent,
      parentRepoName,
      repoGuid,
    }),
  invalidateKeys: ['repos', 'teams', 'machines'],
  successMessage: (vars) =>
    `Repo "${vars.repoName}:${vars.repoTag || 'latest'}" created successfully`,
  errorMessage: 'Failed to create repo',
  transformData: (data) => ({
    ...data,
    vaultContent: data.vaultContent || '{}',
    repoTag: data.repoTag || 'latest',
  }),
  operationName: 'repos.create',
});

// Update repo name
export const useUpdateRepoName = createMutation<UpdateRepositoryNameParams>({
  request: (params) => api.repos.rename(params),
  invalidateKeys: ['repos', 'machines'],
  successMessage: (vars) => `Repo renamed to "${vars.newRepoName}"`,
  errorMessage: 'Failed to update repo name',
  operationName: 'repos.rename',
});

// Update repo tag
export const useUpdateRepoTag = createMutation<UpdateRepositoryTagParams>({
  request: (params) => api.repos.renameTag(params),
  invalidateKeys: ['repos', 'machines'],
  successMessage: (vars) => `Tag renamed to "${vars.newTag}"`,
  errorMessage: 'Failed to update tag',
  operationName: 'repos.renameTag',
});

// Update repo vault
export const useUpdateRepoVault = createMutation<UpdateRepositoryVaultParams>({
  request: (params) => api.repos.updateVault(params),
  invalidateKeys: ['repos'],
  successMessage: (vars) => `Repo vault updated for "${vars.repoName}"`,
  errorMessage: 'Failed to update repo vault',
  transformData: (data) => ({
    ...data,
    vaultContent: minifyJSON(data.vaultContent),
  }),
  operationName: 'repos.updateVault',
});

// Delete repo - uses custom type to match service signature with optional repoTag
type DeleteRepoHookParams = Pick<DeleteRepositoryParams, 'teamName' | 'repoName'> & {
  repoTag?: string;
};

export const useDeleteRepo = createMutation<DeleteRepoHookParams>({
  request: ({ teamName, repoName, repoTag }) =>
    api.repos.delete({ teamName, repoName, repoTag: repoTag || 'latest' }),
  invalidateKeys: ['repos', 'teams', 'machines'],
  successMessage: (vars) =>
    `Repo "${vars.repoName}:${vars.repoTag || 'latest'}" deleted successfully`,
  errorMessage: 'Failed to delete repo',
  transformData: (data) => ({
    ...data,
    repoTag: data.repoTag || 'latest',
  }),
  operationName: 'repos.delete',
});

// Promote repo to grand (convert clone to original)
export const usePromoteRepoToGrand = createMutation<PromoteRepositoryToGrandParams>({
  request: (params) => api.repos.promoteToGrand(params),
  invalidateKeys: ['repos'],
  successMessage: (vars) => `Repo "${vars.repoName}" promoted to original successfully`,
  errorMessage: 'Failed to promote repo',
  operationName: 'repos.promoteToGrand',
});

export type { GetTeamRepositories_ResultSet1, GetTeamRepositories_ResultSet1 as Repo };
