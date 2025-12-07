import { api } from '@/api/client';
import { createMutation } from '@/hooks/api/mutationFactory';
import { createResourceQuery } from '@/hooks/api/queryFactory';
import { minifyJSON } from '@/utils/json';
import type { Repo } from '@rediacc/shared/types';

// Get repos for a team or multiple teams
export const useRepos = createResourceQuery<Repo>({
  queryKey: 'repos',
  fetcher: (teamFilter) => {
    if (!teamFilter) {
      throw new Error('Team filter is required to load repositories');
    }
    return api.repos.list(teamFilter);
  },
  enabledCheck: (teamFilter) =>
    !!teamFilter && (!Array.isArray(teamFilter) || teamFilter.length > 0),
  operationName: 'repos.list',
});

// Create repo
export const useCreateRepo = createMutation<{
  teamName: string;
  repoName: string;
  repoTag?: string; // Optional repo tag (defaults to 'latest')
  vaultContent?: string;
  parentRepoName?: string; // Optional parent repo name
  repoGuid?: string; // Optional repo GUID
}>({
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
export const useUpdateRepoName = createMutation<{
  teamName: string;
  currentRepoName: string;
  newRepoName: string;
}>({
  request: ({ teamName, currentRepoName, newRepoName }) =>
    api.repos.rename(teamName, currentRepoName, newRepoName),
  invalidateKeys: ['repos', 'machines'],
  successMessage: (vars) => `Repo renamed to "${vars.newRepoName}"`,
  errorMessage: 'Failed to update repo name',
  operationName: 'repos.rename',
});

// Update repo tag
export const useUpdateRepoTag = createMutation<{
  teamName: string;
  repoName: string;
  currentTag: string;
  newTag: string;
}>({
  request: ({ teamName, repoName, currentTag, newTag }) =>
    api.repos.renameTag(teamName, repoName, currentTag, newTag),
  invalidateKeys: ['repos', 'machines'],
  successMessage: (vars) => `Tag renamed to "${vars.newTag}"`,
  errorMessage: 'Failed to update tag',
  operationName: 'repos.renameTag',
});

// Update repo vault
export const useUpdateRepoVault = createMutation<{
  teamName: string;
  repoName: string;
  vaultContent: string;
  vaultVersion: number;
}>({
  request: ({ teamName, repoName, vaultContent, vaultVersion }) =>
    api.repos.updateVault(teamName, repoName, vaultContent, vaultVersion),
  invalidateKeys: ['repos'],
  successMessage: (vars) => `Repo vault updated for "${vars.repoName}"`,
  errorMessage: 'Failed to update repo vault',
  transformData: (data) => ({
    ...data,
    vaultContent: minifyJSON(data.vaultContent),
  }),
  operationName: 'repos.updateVault',
});

// Delete repo
export const useDeleteRepo = createMutation<{
  teamName: string;
  repoName: string;
  repoTag?: string; // Optional repo tag (defaults to 'latest')
}>({
  request: ({ teamName, repoName, repoTag }) => api.repos.delete(teamName, repoName, repoTag),
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
export const usePromoteRepoToGrand = createMutation<{
  teamName: string;
  repoName: string;
}>({
  request: ({ teamName, repoName }) => api.repos.promoteToGrand(teamName, repoName),
  invalidateKeys: ['repos'],
  successMessage: (vars) => `Repo "${vars.repoName}" promoted to original successfully`,
  errorMessage: 'Failed to promote repo',
  operationName: 'repos.promoteToGrand',
});

export type { Repo };
