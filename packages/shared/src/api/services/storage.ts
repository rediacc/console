import { endpoints } from '../../endpoints';
import type { Storage } from '../../types';
import { parseResponse, responseExtractors } from '../parseResponse';
import type { ApiClient } from './types';

export function createStorageService(client: ApiClient) {
  return {
    list: async (teamName: string): Promise<Storage[]> => {
      const response = await client.get<Storage>(endpoints.storage.getTeamStorages, { teamName });
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<Storage>(1),
        filter: (storage) => Boolean(storage.storageName),
      });
    },

    create: (teamName: string, storageName: string) =>
      client.post(endpoints.storage.createStorage, { teamName, storageName }),

    rename: (teamName: string, currentName: string, newName: string) =>
      client.post(endpoints.storage.updateStorageName, {
        teamName,
        currentStorageName: currentName,
        newStorageName: newName,
      }),

    delete: (teamName: string, storageName: string) =>
      client.post(endpoints.storage.deleteStorage, { teamName, storageName }),

    updateVault: (teamName: string, storageName: string, vault: string, vaultVersion: number) =>
      client.post(endpoints.storage.updateStorageVault, {
        teamName,
        storageName,
        vaultContent: vault,
        vaultVersion,
      }),
  };
}
