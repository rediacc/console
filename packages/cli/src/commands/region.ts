import type {
  CreateRegionParams,
  DeleteRegionParams,
  UpdateRegionNameParams,
  UpdateRegionVaultParams,
} from '@rediacc/shared/types';
import { Command } from 'commander';
import { api } from '../services/api.js';
import { createResourceCommands } from '../utils/commandFactory.js';

export function registerRegionCommands(program: Command): void {
  createResourceCommands(program, {
    resourceName: 'region',
    resourceNamePlural: 'regions',
    nameField: 'regionName',
    parentOption: 'none',
    operations: {
      list: () => api.regions.list(),
      create: (payload) => api.regions.create(payload as unknown as CreateRegionParams),
      rename: (payload) => api.regions.rename(payload as unknown as UpdateRegionNameParams),
      delete: (payload) => api.regions.delete(payload as unknown as DeleteRegionParams),
    },
    vaultConfig: {
      fetch: (params) => api.company.getAllVaults(params),
      vaultType: 'Region',
    },
    vaultUpdateConfig: {
      update: (payload) => api.regions.updateVault(payload as unknown as UpdateRegionVaultParams),
      vaultFieldName: 'vaultContent',
    },
  });
}
