import { Command } from 'commander'
import { authService } from '../services/auth.js'
import { apiClient } from '../services/api.js'
import { contextService } from '../services/context.js'
import { outputService } from '../services/output.js'
import { withSpinner } from '../utils/spinner.js'
import { handleError } from '../utils/errors.js'
import type { OutputFormat } from '../types/index.js'

export function registerMachineCommands(program: Command): void {
  const machine = program
    .command('machine')
    .description('Machine management commands')

  // machine list
  machine
    .command('list')
    .description('List machines')
    .option('-t, --team <name>', 'Team name')
    .action(async (options) => {
      try {
        await authService.requireAuth()
        const opts = await contextService.applyDefaults(options)

        if (!opts.team) {
          outputService.error('Team name required. Use --team or set context.')
          process.exit(1)
        }

        const response = await withSpinner(
          'Fetching machines...',
          () => apiClient.get('/GetTeamMachines', { teamName: opts.team }),
          'Machines fetched'
        )

        const machines = response.resultSets?.[0]?.data || []
        const format = program.opts().output as OutputFormat

        outputService.print(machines, format)
      } catch (error) {
        handleError(error)
      }
    })

  // machine create
  machine
    .command('create <name>')
    .description('Create a new machine')
    .option('-t, --team <name>', 'Team name')
    .option('-b, --bridge <name>', 'Bridge name')
    .action(async (name, options) => {
      try {
        await authService.requireAuth()
        const opts = await contextService.applyDefaults(options)

        if (!opts.team) {
          outputService.error('Team name required. Use --team or set context.')
          process.exit(1)
        }

        if (!opts.bridge) {
          outputService.error('Bridge name required. Use --bridge.')
          process.exit(1)
        }

        await withSpinner(
          `Creating machine "${name}"...`,
          () => apiClient.post('/CreateMachine', {
            machineName: name,
            teamName: opts.team,
            bridgeName: opts.bridge,
          }),
          `Machine "${name}" created`
        )
      } catch (error) {
        handleError(error)
      }
    })

  // machine rename
  machine
    .command('rename <oldName> <newName>')
    .description('Rename a machine')
    .option('-t, --team <name>', 'Team name')
    .action(async (oldName, newName, options) => {
      try {
        await authService.requireAuth()
        const opts = await contextService.applyDefaults(options)

        if (!opts.team) {
          outputService.error('Team name required. Use --team or set context.')
          process.exit(1)
        }

        await withSpinner(
          `Renaming machine "${oldName}" to "${newName}"...`,
          () => apiClient.post('/UpdateMachineName', {
            currentMachineName: oldName,
            newMachineName: newName,
            teamName: opts.team,
          }),
          `Machine renamed to "${newName}"`
        )
      } catch (error) {
        handleError(error)
      }
    })

  // machine delete
  machine
    .command('delete <name>')
    .description('Delete a machine')
    .option('-t, --team <name>', 'Team name')
    .option('-f, --force', 'Skip confirmation')
    .action(async (name, options) => {
      try {
        await authService.requireAuth()
        const opts = await contextService.applyDefaults(options)

        if (!opts.team) {
          outputService.error('Team name required. Use --team or set context.')
          process.exit(1)
        }

        if (!options.force) {
          const { askConfirm } = await import('../utils/prompt.js')
          const confirm = await askConfirm(`Delete machine "${name}"? This cannot be undone.`)
          if (!confirm) {
            outputService.info('Cancelled')
            return
          }
        }

        await withSpinner(
          `Deleting machine "${name}"...`,
          () => apiClient.post('/DeleteMachine', {
            machineName: name,
            teamName: opts.team,
          }),
          `Machine "${name}" deleted`
        )
      } catch (error) {
        handleError(error)
      }
    })

  // machine status
  machine
    .command('status <name>')
    .description('Get machine status')
    .option('-t, --team <name>', 'Team name')
    .action(async (name, options) => {
      try {
        await authService.requireAuth()
        const opts = await contextService.applyDefaults(options)

        if (!opts.team) {
          outputService.error('Team name required. Use --team or set context.')
          process.exit(1)
        }

        const response = await withSpinner(
          'Fetching machine status...',
          () => apiClient.get('/GetTeamMachines', { teamName: opts.team }),
          'Status fetched'
        )

        const machines = response.resultSets?.[0]?.data || []
        const machine = machines.find((m: any) => m.machineName === name)
        const format = program.opts().output as OutputFormat

        if (machine) {
          outputService.print(machine, format)
        } else {
          outputService.error(`Machine "${name}" not found`)
        }
      } catch (error) {
        handleError(error)
      }
    })

  // machine vault subcommand
  const vault = machine
    .command('vault')
    .description('Machine vault management')

  // machine vault get
  vault
    .command('get <machineName>')
    .description('Get machine vault data')
    .option('-t, --team <name>', 'Team name')
    .action(async (machineName, options) => {
      try {
        await authService.requireAuth()
        const opts = await contextService.applyDefaults(options)

        if (!opts.team) {
          outputService.error('Team name required. Use --team or set context.')
          process.exit(1)
        }

        const response = await withSpinner(
          'Fetching machine vault...',
          () => apiClient.get('/GetCompanyVaults', {
            teamName: opts.team,
            machineName,
          }),
          'Vault fetched'
        )

        const vaults = response.resultSets?.[0]?.data || []
        const machineVault = vaults.find((v: any) => v.vaultType === 'Machine')
        const format = program.opts().output as OutputFormat

        if (machineVault) {
          outputService.print(machineVault, format)
        } else {
          outputService.info('No machine vault found')
        }
      } catch (error) {
        handleError(error)
      }
    })

  // machine assign-bridge
  machine
    .command('assign-bridge <machineName> <bridgeName>')
    .description('Assign machine to a bridge')
    .option('-t, --team <name>', 'Team name')
    .action(async (machineName, bridgeName, options) => {
      try {
        await authService.requireAuth()
        const opts = await contextService.applyDefaults(options)

        if (!opts.team) {
          outputService.error('Team name required. Use --team or set context.')
          process.exit(1)
        }

        await withSpinner(
          `Assigning machine "${machineName}" to bridge "${bridgeName}"...`,
          () => apiClient.post('/UpdateMachineAssignedBridge', {
            machineName,
            newBridgeName: bridgeName,
            teamName: opts.team,
          }),
          `Machine assigned to bridge "${bridgeName}"`
        )
      } catch (error) {
        handleError(error)
      }
    })
}
