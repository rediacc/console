import { Command } from 'commander'
import { authService } from '../services/auth.js'
import { apiClient } from '../services/api.js'
import { contextService } from '../services/context.js'
import { outputService } from '../services/output.js'
import { withSpinner } from '../utils/spinner.js'
import { handleError } from '../utils/errors.js'
import type { OutputFormat } from '../types/index.js'

export function registerStorageCommands(program: Command): void {
  const storage = program
    .command('storage')
    .description('Storage management commands')

  // storage list
  storage
    .command('list')
    .description('List storage systems')
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
          'Fetching storage systems...',
          () => apiClient.get('/GetTeamStorages', { teamName: opts.team }),
          'Storage systems fetched'
        )

        const storages = response.resultSets?.[0]?.data || []
        const format = program.opts().output as OutputFormat

        outputService.print(storages, format)
      } catch (error) {
        handleError(error)
      }
    })

  // storage create
  storage
    .command('create <name>')
    .description('Create a new storage system')
    .option('-t, --team <name>', 'Team name')
    .action(async (name, options) => {
      try {
        await authService.requireAuth()
        const opts = await contextService.applyDefaults(options)

        if (!opts.team) {
          outputService.error('Team name required. Use --team or set context.')
          process.exit(1)
        }

        await withSpinner(
          `Creating storage "${name}"...`,
          () => apiClient.post('/CreateStorage', {
            storageName: name,
            teamName: opts.team,
          }),
          `Storage "${name}" created`
        )
      } catch (error) {
        handleError(error)
      }
    })

  // storage rename
  storage
    .command('rename <oldName> <newName>')
    .description('Rename a storage system')
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
          `Renaming storage "${oldName}" to "${newName}"...`,
          () => apiClient.post('/UpdateStorageName', {
            currentStorageName: oldName,
            newStorageName: newName,
            teamName: opts.team,
          }),
          `Storage renamed to "${newName}"`
        )
      } catch (error) {
        handleError(error)
      }
    })

  // storage delete
  storage
    .command('delete <name>')
    .description('Delete a storage system')
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
          const confirm = await askConfirm(`Delete storage "${name}"? This cannot be undone.`)
          if (!confirm) {
            outputService.info('Cancelled')
            return
          }
        }

        await withSpinner(
          `Deleting storage "${name}"...`,
          () => apiClient.post('/DeleteStorage', {
            storageName: name,
            teamName: opts.team,
          }),
          `Storage "${name}" deleted`
        )
      } catch (error) {
        handleError(error)
      }
    })

  // storage vault subcommand
  const vault = storage
    .command('vault')
    .description('Storage vault management')

  // storage vault get
  vault
    .command('get <storageName>')
    .description('Get storage vault data')
    .option('-t, --team <name>', 'Team name')
    .action(async (storageName, options) => {
      try {
        await authService.requireAuth()
        const opts = await contextService.applyDefaults(options)

        if (!opts.team) {
          outputService.error('Team name required. Use --team or set context.')
          process.exit(1)
        }

        const response = await withSpinner(
          'Fetching storage vault...',
          () => apiClient.get('/GetCompanyVaults', {
            teamName: opts.team,
            storageName,
          }),
          'Vault fetched'
        )

        const vaults = response.resultSets?.[0]?.data || []
        const storageVault = vaults.find((v: any) => v.vaultType === 'Storage')
        const format = program.opts().output as OutputFormat

        if (storageVault) {
          outputService.print(storageVault, format)
        } else {
          outputService.info('No storage vault found')
        }
      } catch (error) {
        handleError(error)
      }
    })
}
