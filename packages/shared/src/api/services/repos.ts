import { endpoints } from '../../endpoints';
import type { Repo } from '../../types';
import { parseFirst, parseResponse, responseExtractors } from '../parseResponse';
import type { ApiClient } from './types';

export interface CreateRepoOptions {
  repoTag?: string;
  vaultContent?: string;
  parentRepoName?: string;
  parentRepoTag?: string;
  repoGuid?: string;
}

const mapRepo = (repo: Repo): Repo => ({
  ...repo,
  repoTag: repo.repoTag || 'latest',
});

const normalizeTeamParam = (teamName: string | string[]): string =>
  Array.isArray(teamName) ? teamName.join(',') : teamName;

export function createReposService(client: ApiClient) {
  return {
    list: async (teamName: string | string[]): Promise<Repo[]> => {
      const response = await client.get<Repo>(endpoints.repos.getTeamRepos, {
        teamName: normalizeTeamParam(teamName),
      });
      return parseResponse(response, {
        extractor: responseExtractors.primaryOrSecondary,
        filter: (repo) => Boolean(repo.repoName),
        map: mapRepo,
      });
    },

    create: async (
      teamName: string,
      repoName: string,
      options: CreateRepoOptions = {}
    ): Promise<Repo | null> => {
      const payload: Record<string, unknown> = {
        teamName,
        repoName,
        vaultContent: options.vaultContent ?? '{}',
      };
      // Only include optional params if they have non-empty values
      if (options.repoTag) {
        payload.repoTag = options.repoTag;
      }
      if (options.parentRepoName && options.parentRepoName.trim() !== '') {
        payload.parentRepoName = options.parentRepoName;
      }
      if (options.parentRepoTag && options.parentRepoTag.trim() !== '') {
        payload.parentRepoTag = options.parentRepoTag;
      }
      if (options.repoGuid && options.repoGuid.trim() !== '') {
        payload.repoGuid = options.repoGuid;
      }
      const response = await client.post<Repo>(endpoints.repos.createRepo, payload);

      return parseFirst(response, {
        extractor: responseExtractors.primaryOrSecondary,
        map: mapRepo,
      });
    },

    rename: async (teamName: string, currentName: string, newName: string): Promise<void> => {
      await client.post(endpoints.repos.updateRepoName, {
        teamName,
        currentRepoName: currentName,
        newRepoName: newName,
      });
    },

    renameTag: async (
      teamName: string,
      repoName: string,
      currentTag: string,
      newTag: string
    ): Promise<void> => {
      await client.post(endpoints.repos.updateRepoTag, {
        teamName,
        repoName,
        currentTag,
        newTag,
      });
    },

    delete: async (teamName: string, repoName: string, repoTag?: string): Promise<void> => {
      const payload: Record<string, unknown> = { teamName, repoName };
      if (repoTag) {
        payload.repoTag = repoTag;
      }
      await client.post(endpoints.repos.deleteRepo, payload);
    },

    updateVault: async (
      teamName: string,
      repoName: string,
      vault: string,
      vaultVersion: number
    ): Promise<void> => {
      await client.post(endpoints.repos.updateRepoVault, {
        teamName,
        repoName,
        vaultContent: vault,
        vaultVersion,
      });
    },

    promoteToGrand: async (teamName: string, repoName: string): Promise<void> => {
      await client.post(endpoints.repos.promoteRepoToGrand, {
        teamName,
        repoName,
      });
    },
  };
}
