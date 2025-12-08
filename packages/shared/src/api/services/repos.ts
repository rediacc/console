import { parseFirst, parseResponse, responseExtractors } from '../parseResponse';
import type { ApiClient } from './types';
import type { GetTeamRepositories_ResultSet1 } from '../../types';
import type {
  GetTeamRepositoriesParams,
  UpdateRepositoryNameParams,
  UpdateRepositoryTagParams,
  DeleteRepositoryParams,
  UpdateRepositoryVaultParams,
  PromoteRepositoryToGrandParams,
} from '../../types';

export interface CreateRepoOptions {
  repoTag?: string;
  vaultContent?: string;
  parentRepoName?: string;
  parentRepoTag?: string;
  repoGuid?: string;
}

const mapRepo = (repo: GetTeamRepositories_ResultSet1): GetTeamRepositories_ResultSet1 => ({
  ...repo,
  repoTag: repo.repoTag || 'latest',
});

export function createReposService(client: ApiClient) {
  return {
    list: async (
      params: GetTeamRepositoriesParams | { teamName: string[] }
    ): Promise<GetTeamRepositories_ResultSet1[]> => {
      const teamName = Array.isArray(params.teamName) ? params.teamName.join(',') : params.teamName;
      const response = await client.get<GetTeamRepositories_ResultSet1>('/GetTeamRepositories', {
        teamName,
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
    ): Promise<GetTeamRepositories_ResultSet1 | null> => {
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
      const response = await client.post<GetTeamRepositories_ResultSet1>(
        '/CreateRepository',
        payload
      );

      return parseFirst(response, {
        extractor: responseExtractors.primaryOrSecondary,
        map: mapRepo,
      });
    },

    rename: async (params: UpdateRepositoryNameParams): Promise<void> => {
      await client.post('/UpdateRepositoryName', params);
    },

    renameTag: async (params: UpdateRepositoryTagParams): Promise<void> => {
      await client.post('/UpdateRepositoryTag', params);
    },

    delete: async (params: DeleteRepositoryParams): Promise<void> => {
      await client.post('/DeleteRepository', params);
    },

    updateVault: async (params: UpdateRepositoryVaultParams): Promise<void> => {
      await client.post('/UpdateRepositoryVault', params);
    },

    promoteToGrand: async (params: PromoteRepositoryToGrandParams): Promise<void> => {
      await client.post('/PromoteRepositoryToGrand', params);
    },
  };
}
