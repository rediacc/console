import { Command } from 'commander';
import { getStateProvider } from '../providers/index.js';
import { createResourceCommands } from '../utils/commandFactory.js';

export function registerStorageCommands(program: Command): void {
  createResourceCommands(program, {
    resourceName: 'storage',
    resourceNamePlural: 'storage systems',
    nameField: 'storageName',
    parentOption: 'team',
    operations: {
      list: async (params) => {
        const provider = await getStateProvider();
        return provider.storage.list({ teamName: params?.teamName as string });
      },
      create: async (payload) => {
        const provider = await getStateProvider();
        return provider.storage.create(payload as Record<string, unknown>);
      },
      rename: async (payload) => {
        const provider = await getStateProvider();
        return provider.storage.rename(payload as Record<string, unknown>);
      },
      delete: async (payload) => {
        const provider = await getStateProvider();
        return provider.storage.delete(payload as Record<string, unknown>);
      },
    },
    transformCreatePayload: (name, opts) => ({
      storageName: name,
      teamName: opts.team,
    }),
    vaultConfig: {
      fetch: async (params) => {
        const provider = await getStateProvider();
        return provider.storage.getVault(params) as Promise<never>;
      },
      vaultType: 'Storage',
    },
    vaultUpdateConfig: {
      update: async (payload) => {
        const provider = await getStateProvider();
        return provider.storage.updateVault(payload as Record<string, unknown>);
      },
      vaultFieldName: 'vaultContent',
    },
  });
}
