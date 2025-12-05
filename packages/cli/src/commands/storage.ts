import { Command } from 'commander';
import { createResourceCommands } from '../utils/commandFactory.js';
import { api } from '../services/api.js';

export function registerStorageCommands(program: Command): void {
  createResourceCommands(program, {
    resourceName: 'storage',
    resourceNamePlural: 'storage systems',
    nameField: 'storageName',
    parentOption: 'team',
    operations: {
      list: (params) => api.storage.list(params?.teamName as string),
      create: (payload) =>
        api.storage.create(payload.teamName as string, payload.storageName as string),
      rename: (payload) =>
        api.storage.rename(
          payload.teamName as string,
          payload.currentStorageName as string,
          payload.newStorageName as string
        ),
      delete: (payload) =>
        api.storage.delete(payload.teamName as string, payload.storageName as string),
    },
    vaultConfig: {
      fetch: (params) => api.company.getAllVaults(params),
      vaultType: 'Storage',
    },
    vaultUpdateConfig: {
      update: (payload) =>
        api.storage.updateVault(
          payload.teamName as string,
          payload.storageName as string,
          payload.storageVault as string,
          payload.vaultVersion as number
        ),
      vaultFieldName: 'storageVault',
    },
  });
}
