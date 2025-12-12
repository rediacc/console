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

// Get repositories for a team or multiple teams
export const useRepositories = createResourceQuery<GetTeamRepositories_ResultSet1>({
  queryKey: 'repositories',
  fetcher: (teamFilter) => {
    if (!teamFilter) {
      throw new Error('Team filter is required to load repositories');
    }
    return api.repositories.list(
      Array.isArray(teamFilter) ? { teamName: teamFilter } : { teamName: teamFilter }
    );
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

export const useCreateRepository = createMutation<CreateRepositoryHookParams>({
  request: ({ teamName, repositoryName, repositoryTag, vaultContent, parentRepositoryName, repositoryGuid }) =>
    api.repositories.create(teamName, repositoryName, {
      repositoryTag,
      vaultContent,
      parentRepositoryName,
      repositoryGuid,
    }),
  invalidateKeys: ['repositories', 'teams', 'machines'],
  successMessage: (vars) =>
    `Repository "${vars.repositoryName}:${vars.repositoryTag || 'latest'}" created successfully`,
  errorMessage: 'Failed to create repository',
  transformData: (data) => ({
    ...data,
    vaultContent: data.vaultContent || '{}',
    repositoryTag: data.repositoryTag || 'latest',
  }),
  operationName: 'repositories.create',
});

// Update repository name
export const useUpdateRepositoryName = createMutation<UpdateRepositoryNameParams>({
  request: (params) => api.repositories.rename(params),
  invalidateKeys: ['repositories', 'machines'],
  successMessage: (vars) => `Repository renamed to "${vars.newRepositoryName}"`,
  errorMessage: 'Failed to update repository name',
  operationName: 'repositories.rename',
});

// Update repository tag
export const useUpdateRepositoryTag = createMutation<UpdateRepositoryTagParams>({
  request: (params) => api.repositories.renameTag(params),
  invalidateKeys: ['repositories', 'machines'],
  successMessage: (vars) => `Tag renamed to "${vars.newTag}"`,
  errorMessage: 'Failed to update tag',
  operationName: 'repositories.renameTag',
});

// Update repository vault
export const useUpdateRepositoryVault = createMutation<UpdateRepositoryVaultParams>({
  request: (params) => api.repositories.updateVault(params),
  invalidateKeys: ['repositories'],
  successMessage: (vars) => `Repository vault updated for "${vars.repositoryName}"`,
  errorMessage: 'Failed to update repository vault',
  transformData: (data) => ({
    ...data,
    vaultContent: minifyJSON(data.vaultContent),
  }),
  operationName: 'repositories.updateVault',
});

// Delete repository - uses custom type to match service signature with optional repositoryTag
type DeleteRepositoryHookParams = Pick<DeleteRepositoryParams, 'teamName' | 'repositoryName'> & {
  repositoryTag?: string;
};

export const useDeleteRepository = createMutation<DeleteRepositoryHookParams>({
  request: ({ teamName, repositoryName, repositoryTag }) =>
    api.repositories.delete({ teamName, repositoryName, repositoryTag: repositoryTag || 'latest' }),
  invalidateKeys: ['repositories', 'teams', 'machines'],
  successMessage: (vars) =>
    `Repository "${vars.repositoryName}:${vars.repositoryTag || 'latest'}" deleted successfully`,
  errorMessage: 'Failed to delete repository',
  transformData: (data) => ({
    ...data,
    repositoryTag: data.repositoryTag || 'latest',
  }),
  operationName: 'repositories.delete',
});

// Promote repository to grand (convert clone to original)
export const usePromoteRepositoryToGrand = createMutation<PromoteRepositoryToGrandParams>({
  request: (params) => api.repositories.promoteToGrand(params),
  invalidateKeys: ['repositories'],
  successMessage: (vars) => `Repository "${vars.repositoryName}" promoted to original successfully`,
  errorMessage: 'Failed to promote repository',
  operationName: 'repositories.promoteToGrand',
});

export type { GetTeamRepositories_ResultSet1, GetTeamRepositories_ResultSet1 as Repository };
