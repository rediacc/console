import { Command } from 'commander';
import { parseGetCompanyRegions, parseGetCompanyVaults } from '@rediacc/shared/api';
import type {
  CreateRegionParams,
  DeleteRegionParams,
  UpdateRegionNameParams,
  UpdateRegionVaultParams,
  GetCompanyVaults_ResultSet1,
} from '@rediacc/shared/types';
import { typedApi } from '../services/api.js';
import { createResourceCommands } from '../utils/commandFactory.js';

export function registerRegionCommands(program: Command): void {
  createResourceCommands(program, {
    resourceName: 'region',
    resourceNamePlural: 'regions',
    nameField: 'regionName',
    parentOption: 'none',
    operations: {
      list: async () => {
        const response = await typedApi.GetCompanyRegions({});
        return parseGetCompanyRegions(response as never);
      },
      create: async (payload) => {
        await typedApi.CreateRegion(payload as unknown as CreateRegionParams);
      },
      rename: async (payload) => {
        await typedApi.UpdateRegionName(payload as unknown as UpdateRegionNameParams);
      },
      delete: async (payload) => {
        await typedApi.DeleteRegion(payload as unknown as DeleteRegionParams);
      },
    },
    transformCreatePayload: (name, _opts) => ({
      regionName: name,
    }),
    vaultConfig: {
      fetch: async () => {
        const response = await typedApi.GetCompanyVaults({});
        const vaults = parseGetCompanyVaults(response as never);
        return vaults as unknown as (GetCompanyVaults_ResultSet1 & { vaultType?: string })[];
      },
      vaultType: 'Region',
    },
    vaultUpdateConfig: {
      update: async (payload) => {
        await typedApi.UpdateRegionVault(payload as unknown as UpdateRegionVaultParams);
      },
      vaultFieldName: 'vaultContent',
    },
  });
}
