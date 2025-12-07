import { Command } from 'commander';
import type {
  CreateStorageParams,
  UpdateStorageNameParams,
  DeleteStorageParams,
  UpdateStorageVaultParams,
} from '@rediacc/shared/types';
import { api } from '../services/api.js';
import { createResourceCommands } from '../utils/commandFactory.js';

export function registerStorageCommands(program: Command): void {
  createResourceCommands(program, {
    resourceName: 'storage',
    resourceNamePlural: 'storage systems',
    nameField: 'storageName',
    parentOption: 'team',
    operations: {
      list: (params) => api.storage.list({ teamName: params?.teamName as string }),
      create: (payload) => api.storage.create(payload as unknown as CreateStorageParams),
      rename: (payload) => api.storage.rename(payload as unknown as UpdateStorageNameParams),
      delete: (payload) => api.storage.delete(payload as unknown as DeleteStorageParams),
    },
    vaultConfig: {
      fetch: (params) => api.company.getAllVaults(params),
      vaultType: 'Storage',
    },
    vaultUpdateConfig: {
      update: (payload) => api.storage.updateVault(payload as unknown as UpdateStorageVaultParams),
      vaultFieldName: 'vaultContent',
    },
  });
}
