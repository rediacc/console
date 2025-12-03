import { endpoints } from '../../endpoints'
import type { Repo } from '../../types'
import { parseFirst, parseResponse, responseExtractors } from '../parseResponse'
import type { ApiClient } from './types'

export interface CreateRepoOptions {
  repoTag?: string
  repoVault?: string
  parentRepoName?: string
  parentRepoTag?: string
  repoGuid?: string
}

const mapRepo = (repo: Repo): Repo => ({
  ...repo,
  repoTag: repo.repoTag || 'latest',
  repoVault: repo.repoVault || '{}',
})

const normalizeTeamParam = (teamName: string | string[]): string =>
  Array.isArray(teamName) ? teamName.join(',') : teamName

export function createReposService(client: ApiClient) {
  return {
    list: async (teamName: string | string[]): Promise<Repo[]> => {
      const response = await client.get<Repo>(endpoints.repos.getTeamRepos, {
        teamName: normalizeTeamParam(teamName),
      })
      return parseResponse(response, {
        extractor: responseExtractors.primaryOrSecondary,
        filter: (repo) => Boolean(repo.repoName),
        map: mapRepo,
      })
    },

    create: async (teamName: string, repoName: string, options: CreateRepoOptions = {}): Promise<Repo | null> => {
      const response = await client.post<Repo>(endpoints.repos.createRepo, {
        teamName,
        repoName,
        repoTag: options.repoTag,
        repoVault: options.repoVault,
        parentRepoName: options.parentRepoName,
        parentRepoTag: options.parentRepoTag,
        repoGuid: options.repoGuid,
      })

      return parseFirst(response, {
        extractor: responseExtractors.primaryOrSecondary,
        map: mapRepo,
      })
    },

    rename: async (teamName: string, currentName: string, newName: string): Promise<void> => {
      await client.post(endpoints.repos.updateRepoName, {
        teamName,
        currentRepoName: currentName,
        newRepoName: newName,
      })
    },

    delete: async (teamName: string, repoName: string, repoTag?: string): Promise<void> => {
      await client.post(endpoints.repos.deleteRepo, {
        teamName,
        repoName,
        repoTag,
      })
    },

    updateVault: async (teamName: string, repoName: string, vault: string, vaultVersion: number): Promise<void> => {
      await client.post(endpoints.repos.updateRepoVault, {
        teamName,
        repoName,
        repoVault: vault,
        vaultVersion,
      })
    },

    promoteToGrand: async (teamName: string, repoName: string): Promise<void> => {
      await client.post(endpoints.repos.promoteRepoToGrand, {
        teamName,
        repoName,
      })
    },
  }
}
