import { Command } from 'commander';
import { api } from '../services/api.js';
import {
  createResourceCommands,
  addStatusCommand,
  addAssignCommand,
} from '../utils/commandFactory.js';
export function registerMachineCommands(program: Command): void {
  // Create standard CRUD commands using factory
  const machine = createResourceCommands(program, {
    resourceName: 'machine',
    resourceNamePlural: 'machines',
    nameField: 'machineName',
    parentOption: 'team',
    operations: {
      list: (params) => api.machines.list(params?.teamName as string | undefined),
      create: (payload) =>
        api.machines.create(
          payload.teamName as string,
          payload.machineName as string,
          payload.bridgeName as string,
          payload.vaultContent as string | undefined
        ),
      rename: (payload) =>
        api.machines.rename(
          payload.teamName as string,
          payload.currentMachineName as string,
          payload.newMachineName as string
        ),
      delete: (payload) =>
        api.machines.delete(payload.teamName as string, payload.machineName as string),
    },
    createOptions: [{ flags: '-b, --bridge <name>', description: 'Bridge name', required: true }],
    transformCreatePayload: (name, opts) => ({
      machineName: name,
      teamName: opts.team,
      bridgeName: opts.bridge,
    }),
    vaultConfig: {
      fetch: (params) => api.company.getAllVaults(params),
      vaultType: 'Machine',
    },
    vaultUpdateConfig: {
      update: (payload) =>
        api.machines.updateVault(
          payload.teamName as string,
          payload.machineName as string,
          payload.vaultContent as string,
          payload.vaultVersion as number
        ),
      vaultFieldName: 'vaultContent',
    },
  });

  // Add status command
  addStatusCommand(machine, {
    resourceName: 'machine',
    nameField: 'machineName',
    parentOption: 'team',
    fetch: (params) => api.machines.list(params.teamName as string | undefined),
  });

  // Add assign-bridge command
  addAssignCommand(machine, {
    resourceName: 'machine',
    nameField: 'machineName',
    targetName: 'bridge',
    targetField: 'newBridgeName',
    parentOption: 'team',
    perform: (payload) =>
      api.machines.assignBridge(
        payload.teamName as string,
        payload.machineName as string,
        payload.newBridgeName as string
      ),
  });
}
