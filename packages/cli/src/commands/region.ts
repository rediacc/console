import { Command } from 'commander';
import { createResourceCommands } from '../utils/commandFactory.js';
import { api } from '../services/api.js';

export function registerRegionCommands(program: Command): void {
  createResourceCommands(program, {
    resourceName: 'region',
    resourceNamePlural: 'regions',
    nameField: 'regionName',
    parentOption: 'none',
    operations: {
      list: () => api.regions.list(),
      create: (payload) => api.regions.create(payload.regionName as string),
      rename: (payload) =>
        api.regions.rename(payload.currentRegionName as string, payload.newRegionName as string),
      delete: (payload) => api.regions.delete(payload.regionName as string),
    },
    vaultConfig: {
      fetch: (params) => api.company.getAllVaults(params),
      vaultType: 'Region',
    },
    vaultUpdateConfig: {
      update: (payload) =>
        api.regions.updateVault(
          payload.regionName as string,
          payload.vaultContent as string,
          payload.vaultVersion as number
        ),
      vaultFieldName: 'vaultContent',
    },
  });
}
