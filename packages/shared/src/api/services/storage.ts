import { endpoints } from '../../endpoints';
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
      const response = await client.get<Storage>(endpoints.storage.getTeamStorages, params);
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<Storage>(1),
        filter: (storage) => Boolean(storage.storageName),
      });
    },

    create: (params: WithOptionalVault<CreateStorageParams>) =>
      client.post(endpoints.storage.createStorage, {
        ...params,
        vaultContent: params.vaultContent ?? '{}',
      }),

    rename: (params: UpdateStorageNameParams) =>
      client.post(endpoints.storage.updateStorageName, params),

    delete: (params: DeleteStorageParams) =>
      client.post(endpoints.storage.deleteStorage, params),

    updateVault: (params: UpdateStorageVaultParams) =>
      client.post(endpoints.storage.updateStorageVault, params),
  };
}
