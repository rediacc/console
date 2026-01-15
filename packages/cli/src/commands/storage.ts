import { parseGetOrganizationVaults, parseGetTeamStorages } from '@rediacc/shared/api';
import type {
  CreateStorageParams,
  DeleteStorageParams,
  GetOrganizationVaults_ResultSet1,
  UpdateStorageNameParams,
  UpdateStorageVaultParams,
} from '@rediacc/shared/types';
import { Command } from 'commander';
import { typedApi } from '../services/api.js';
import { createResourceCommands } from '../utils/commandFactory.js';

export function registerStorageCommands(program: Command): void {
  createResourceCommands(program, {
    resourceName: 'storage',
    resourceNamePlural: 'storage systems',
    nameField: 'storageName',
    parentOption: 'team',
    operations: {
      list: async (params) => {
        const response = await typedApi.GetTeamStorages({ teamName: params?.teamName as string });
        return parseGetTeamStorages(response as never);
      },
      create: async (payload) => {
        await typedApi.CreateStorage(payload as unknown as CreateStorageParams);
      },
      rename: async (payload) => {
        await typedApi.UpdateStorageName(payload as unknown as UpdateStorageNameParams);
      },
      delete: async (payload) => {
        await typedApi.DeleteStorage(payload as unknown as DeleteStorageParams);
      },
    },
    transformCreatePayload: (name, opts) => ({
      storageName: name,
      teamName: opts.team,
    }),
    vaultConfig: {
      fetch: async () => {
        const response = await typedApi.GetOrganizationVaults({});
        const vaults = parseGetOrganizationVaults(response as never);
        return vaults as unknown as (GetOrganizationVaults_ResultSet1 & { vaultType?: string })[];
      },
      vaultType: 'Storage',
    },
    vaultUpdateConfig: {
      update: async (payload) => {
        await typedApi.UpdateStorageVault(payload as unknown as UpdateStorageVaultParams);
      },
      vaultFieldName: 'vaultContent',
    },
  });
}
