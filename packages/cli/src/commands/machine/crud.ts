import { Command } from 'commander';
import type { UpdateMachineAssignedBridgeParams } from '@rediacc/shared/types';
import { t } from '../../i18n/index.js';
import { getStateProvider } from '../../providers/index.js';
import { typedApi } from '../../services/api.js';
import {
  addAssignCommand,
  addStatusCommand,
  createResourceCommands,
} from '../../utils/commandFactory.js';

export function registerCrudCommands(parentCommand: Command): Command {
  // Create standard CRUD commands using factory
  const machine = createResourceCommands(parentCommand, {
    resourceName: 'machine',
    resourceNamePlural: 'machines',
    nameField: 'machineName',
    parentOption: 'team',
    operations: {
      list: async (params) => {
        const provider = await getStateProvider();
        return provider.machines.list({ teamName: params?.teamName as string });
      },
      create: async (payload) => {
        const provider = await getStateProvider();
        return provider.machines.create(payload);
      },
      rename: async (payload) => {
        const provider = await getStateProvider();
        return provider.machines.rename(payload);
      },
      delete: async (payload) => {
        const provider = await getStateProvider();
        return provider.machines.delete(payload);
      },
    },
    createOptions: [
      { flags: '-b, --bridge <name>', description: t('options.bridge'), required: true },
      { flags: '--vault <json>', description: t('options.vaultJsonMachine') },
    ],
    transformCreatePayload: (name, opts) => ({
      machineName: name,
      teamName: opts.team,
      bridgeName: opts.bridge,
      vaultContent: opts.vault,
    }),
    vaultConfig: {
      fetch: async (params) => {
        const provider = await getStateProvider();
        return provider.machines.getVault(params) as Promise<never>;
      },
      vaultType: 'Machine',
    },
    vaultUpdateConfig: {
      update: async (payload) => {
        const provider = await getStateProvider();
        return provider.machines.updateVault(payload);
      },
      vaultFieldName: 'vaultContent',
    },
  });

  // Add status command
  addStatusCommand(machine, {
    resourceName: 'machine',
    nameField: 'machineName',
    parentOption: 'team',
    fetch: async (params) => {
      const provider = await getStateProvider();
      return provider.machines.list({ teamName: params.teamName as string });
    },
  });

  // Add assign-bridge command (cloud-only — uses typedApi directly)
  addAssignCommand(machine, {
    resourceName: 'machine',
    nameField: 'machineName',
    targetName: 'bridge',
    targetField: 'newBridgeName',
    parentOption: 'team',
    perform: (payload) =>
      typedApi.UpdateMachineAssignedBridge(payload as unknown as UpdateMachineAssignedBridgeParams),
  });

  return machine;
}
