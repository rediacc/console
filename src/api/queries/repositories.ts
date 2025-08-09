import { createResourceQuery, dataExtractors, filters, createFieldMapper } from '@/api/utils/queryFactory'
import { createResourceMutation, createVaultUpdateMutation, createMutation } from '@/api/utils/mutationFactory'
import { minifyJSON } from '@/utils/json'

export interface Repository {
  repositoryName: string
  repositoryGuid: string     // Repository GUID/Credential
  teamName: string
  vaultVersion: number
  vaultContent?: string
  grandGuid?: string         // Top-most parent repository GUID
}

// Get repositories for a team or multiple teams
export const useRepositories = createResourceQuery<Repository>({
  endpoint: '/GetTeamRepositories',
  queryKey: 'repositories',
  dataExtractor: dataExtractors.primaryOrSecondary,
  filter: filters.hasName('repoName'),
  mapper: createFieldMapper<Repository>({
    repositoryName: 'repoName',
    repositoryGuid: 'repoGuid',
    teamName: 'teamName',
    vaultVersion: 'vaultVersion',
    vaultContent: 'vaultContent',
    grandGuid: 'grandGuid'
  }),
  enabledCheck: (teamFilter) => !!teamFilter && (!Array.isArray(teamFilter) || teamFilter.length > 0)
})

// Create repository
export const useCreateRepository = createMutation<{
  teamName: string
  repositoryName: string
  repositoryVault?: string
  parentRepoName?: string  // Optional parent repository name
  repositoryGuid?: string  // Optional repository GUID
}>({
  endpoint: '/CreateRepository',
  method: 'post',
  invalidateKeys: ['repositories', 'teams', 'machines'],
  successMessage: (vars) => `Repository "${vars.repositoryName}" created successfully`,
  errorMessage: 'Failed to create repository',
  transformData: (data) => {
    const apiData: any = {
      teamName: data.teamName,
      repoName: data.repositoryName, // Map repositoryName to repoName for API
      repoVault: data.repositoryVault || '{}', // Map repositoryVault to repoVault for API
    }
    
    // Only include optional parameters if they have values
    if (data.parentRepoName) {
      apiData.parentRepoName = data.parentRepoName
    }
    if (data.repositoryGuid && data.repositoryGuid.trim() !== '') {
      apiData.repoGuid = data.repositoryGuid
    }
    
    return apiData
  }
})

// Update repository name
export const useUpdateRepositoryName = createMutation<{
  teamName: string
  currentRepositoryName: string
  newRepositoryName: string
}>({
  endpoint: '/UpdateRepositoryName',
  method: 'put',
  invalidateKeys: ['repositories', 'machines'],
  successMessage: (vars) => `Repository renamed to "${vars.newRepositoryName}"`,
  errorMessage: 'Failed to update repository name',
  transformData: (data) => ({
    teamName: data.teamName,
    currentRepoName: data.currentRepositoryName, // Map to API format
    newRepoName: data.newRepositoryName, // Map to API format
  })
})

// Update repository vault
export const useUpdateRepositoryVault = createMutation<{
  teamName: string
  repositoryName: string
  repositoryVault: string
  vaultVersion: number
}>({
  endpoint: '/UpdateRepositoryVault',
  method: 'put',
  invalidateKeys: ['repositories'],
  successMessage: (vars) => `Repository vault updated for "${vars.repositoryName}"`,
  errorMessage: 'Failed to update repository vault',
  transformData: (data) => ({
    teamName: data.teamName,
    repoName: data.repositoryName, // Map repositoryName to repoName for API
    repoVault: minifyJSON(data.repositoryVault), // Map repositoryVault to repoVault for API and minify
    vaultVersion: data.vaultVersion,
  })
})

// Delete repository
export const useDeleteRepository = createMutation<{
  teamName: string
  repositoryName: string
}>({
  endpoint: '/DeleteRepository',
  method: 'delete',
  invalidateKeys: ['repositories', 'teams', 'machines'],
  successMessage: (vars) => `Repository "${vars.repositoryName}" deleted successfully`,
  errorMessage: 'Failed to delete repository',
  transformData: (data) => ({
    teamName: data.teamName,
    repoName: data.repositoryName, // Map repositoryName to repoName for API
  })
})