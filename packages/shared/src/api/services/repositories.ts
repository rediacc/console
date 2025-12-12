import { parseFirst, parseResponse, responseExtractors } from '../parseResponse';
import type { ApiClient } from './types';
import type {
  DeleteRepositoryParams,
  GetTeamRepositories_ResultSet1,
  GetTeamRepositoriesParams,
  PromoteRepositoryToGrandParams,
  UpdateRepositoryNameParams,
  UpdateRepositoryTagParams,
  UpdateRepositoryVaultParams,
} from '../../types';

export interface CreateRepositoryOptions {
  repositoryTag?: string;
  vaultContent?: string;
  parentRepositoryName?: string;
  parentRepositoryTag?: string;
  repositoryGuid?: string;
}

const mapRepository = (
  repository: GetTeamRepositories_ResultSet1
): GetTeamRepositories_ResultSet1 => ({
  ...repository,
  repositoryTag: repository.repositoryTag || 'latest',
});

export function createRepositorysitoriesService(client: ApiClient) {
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
        filter: (repository) => Boolean(repository.repositoryName),
        map: mapRepository,
      });
    },

    create: async (
      teamName: string,
      repositoryName: string,
      options: CreateRepositoryOptions = {}
    ): Promise<GetTeamRepositories_ResultSet1 | null> => {
      const payload: Record<string, unknown> = {
        teamName,
        repositoryName,
        vaultContent: options.vaultContent ?? '{}',
      };
      // Only include optional params if they have non-empty values
      if (options.repositoryTag) {
        payload.repositoryTag = options.repositoryTag;
      }
      if (options.parentRepositoryName && options.parentRepositoryName.trim() !== '') {
        payload.parentRepositoryName = options.parentRepositoryName;
      }
      if (options.parentRepositoryTag && options.parentRepositoryTag.trim() !== '') {
        payload.parentRepositoryTag = options.parentRepositoryTag;
      }
      if (options.repositoryGuid && options.repositoryGuid.trim() !== '') {
        payload.repositoryGuid = options.repositoryGuid;
      }
      const response = await client.post<GetTeamRepositories_ResultSet1>(
        '/CreateRepository',
        payload
      );

      return parseFirst(response, {
        extractor: responseExtractors.primaryOrSecondary,
        map: mapRepository,
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
