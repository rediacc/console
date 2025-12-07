import { parseResponse, responseExtractors } from '../parseResponse';
import type { ApiClient } from './types';
import type { Storage } from '../../types';
import type {
  WithOptionalVault,
  CreateStorageParams,
  GetTeamStoragesParams,
  UpdateStorageNameParams,
  DeleteStorageParams,
  UpdateStorageVaultParams,
} from '../../types';

export function createStorageService(client: ApiClient) {
  return {
    list: async (params: GetTeamStoragesParams): Promise<Storage[]> => {
      const response = await client.get<Storage>('/GetTeamStorages', params);
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<Storage>(1),
        filter: (storage) => Boolean(storage.storageName),
      });
    },

    create: (params: WithOptionalVault<CreateStorageParams>) =>
      client.post('/CreateStorage', {
        ...params,
        vaultContent: params.vaultContent ?? '{}',
      }),

    rename: (params: UpdateStorageNameParams) => client.post('/UpdateStorageName', params),

    delete: (params: DeleteStorageParams) => client.post('/DeleteStorage', params),

    updateVault: (params: UpdateStorageVaultParams) => client.post('/UpdateStorageVault', params),
  };
}
