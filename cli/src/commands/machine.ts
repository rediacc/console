import { Command } from 'commander'
import { authService } from '../services/auth.js'
import { apiClient } from '../services/api.js'
import { contextService } from '../services/context.js'
import { outputService } from '../services/output.js'
import { withSpinner } from '../utils/spinner.js'
import { handleError } from '../utils/errors.js'
import { createResourceCommands, addStatusCommand, addAssignCommand } from '../utils/commandFactory.js'
import type { OutputFormat } from '../types/index.js'

export function registerMachineCommands(program: Command): void {
  // Create standard CRUD commands using factory
  const machine = createResourceCommands(program, {
    resourceName: 'machine',
    resourceNamePlural: 'machines',
    nameField: 'machineName',
    parentOption: 'team',
    endpoints: {
      list: '/GetTeamMachines',
      create: '/CreateMachine',
      rename: '/UpdateMachineName',
      delete: '/DeleteMachine'
    },
    createOptions: [
      { flags: '-b, --bridge <name>', description: 'Bridge name', required: true }
    ],
    transformCreatePayload: (name, opts) => ({
      machineName: name,
      teamName: opts.team,
      bridgeName: opts.bridge
    }),
    vaultConfig: {
      endpoint: '/GetCompanyVaults',
      vaultType: 'Machine'
    },
    vaultUpdateConfig: {
      endpoint: '/UpdateMachineVault',
      vaultFieldName: 'machineVault'
    }
  })

  // Add status command
  addStatusCommand(machine, {
    resourceName: 'machine',
    nameField: 'machineName',
    parentOption: 'team',
    listEndpoint: '/GetTeamMachines'
  })

  // Add assign-bridge command
  addAssignCommand(machine, {
    resourceName: 'machine',
    nameField: 'machineName',
    targetName: 'bridge',
    targetField: 'newBridgeName',
    parentOption: 'team',
    endpoint: '/UpdateMachineAssignedBridge'
  })
}
