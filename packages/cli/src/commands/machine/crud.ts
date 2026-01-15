import { Command } from 'commander';
import {
  parseCreateMachine,
  parseGetOrganizationVaults,
  parseGetTeamMachines,
} from '@rediacc/shared/api';
import type {
  CreateMachineParams,
  DeleteMachineParams,
  GetOrganizationVaults_ResultSet1,
  UpdateMachineAssignedBridgeParams,
  UpdateMachineNameParams,
  UpdateMachineVaultParams,
} from '@rediacc/shared/types';
import { t } from '../../i18n/index.js';
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
        const response = await typedApi.GetTeamMachines({
          teamName: params?.teamName as string | undefined,
        });
        return parseGetTeamMachines(response as never);
      },
      create: async (payload) => {
        const response = await typedApi.CreateMachine(payload as unknown as CreateMachineParams);
        return parseCreateMachine(response as never);
      },
      rename: (payload) =>
        typedApi.UpdateMachineName(payload as unknown as UpdateMachineNameParams),
      delete: (payload) => typedApi.DeleteMachine(payload as unknown as DeleteMachineParams),
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
      fetch: async () => {
        const response = await typedApi.GetOrganizationVaults({});
        const vaults = parseGetOrganizationVaults(response as never);
        return vaults as unknown as (GetOrganizationVaults_ResultSet1 & { vaultType?: string })[];
      },
      vaultType: 'Machine',
    },
    vaultUpdateConfig: {
      update: (payload) =>
        typedApi.UpdateMachineVault(payload as unknown as UpdateMachineVaultParams),
      vaultFieldName: 'vaultContent',
    },
  });

  // Add status command
  addStatusCommand(machine, {
    resourceName: 'machine',
    nameField: 'machineName',
    parentOption: 'team',
    fetch: async (params) => {
      const response = await typedApi.GetTeamMachines({
        teamName: params.teamName as string | undefined,
      });
      return parseGetTeamMachines(response as never);
    },
  });

  // Add assign-bridge command
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
