import { Command } from 'commander'
import { authService } from '../services/auth.js'
import { apiClient } from '../services/api.js'
import { contextService } from '../services/context.js'
import { outputService } from '../services/output.js'
import { withSpinner } from '../utils/spinner.js'
import { handleError } from '../utils/errors.js'
import type { OutputFormat } from '../types/index.js'
import { getFirstRow, type BridgeAuthResponse } from '../types/api-responses.js'

export function registerBridgeCommands(program: Command): void {
  const bridge = program
    .command('bridge')
    .description('Bridge management commands')

  // bridge list
  bridge
    .command('list')
    .description('List bridges')
    .option('-r, --region <name>', 'Region name')
    .action(async (options) => {
      try {
        await authService.requireAuth()
        const opts = await contextService.applyDefaults(options)

        if (!opts.region) {
          outputService.error('Region name required. Use --region or set context.')
          process.exit(1)
        }

        const response = await withSpinner(
          'Fetching bridges...',
          () => apiClient.get('/GetRegionBridges', { regionName: opts.region }),
          'Bridges fetched'
        )

        const bridges = response.resultSets?.[0]?.data || []
        const format = program.opts().output as OutputFormat

        outputService.print(bridges, format)
      } catch (error) {
        handleError(error)
      }
    })

  // bridge create
  bridge
    .command('create <name>')
    .description('Create a new bridge')
    .option('-r, --region <name>', 'Region name')
    .action(async (name, options) => {
      try {
        await authService.requireAuth()
        const opts = await contextService.applyDefaults(options)

        if (!opts.region) {
          outputService.error('Region name required. Use --region or set context.')
          process.exit(1)
        }

        await withSpinner(
          `Creating bridge "${name}"...`,
          () => apiClient.post('/CreateBridge', {
            bridgeName: name,
            regionName: opts.region,
          }),
          `Bridge "${name}" created`
        )
      } catch (error) {
        handleError(error)
      }
    })

  // bridge rename
  bridge
    .command('rename <oldName> <newName>')
    .description('Rename a bridge')
    .option('-r, --region <name>', 'Region name')
    .action(async (oldName, newName, options) => {
      try {
        await authService.requireAuth()
        const opts = await contextService.applyDefaults(options)

        if (!opts.region) {
          outputService.error('Region name required. Use --region or set context.')
          process.exit(1)
        }

        await withSpinner(
          `Renaming bridge "${oldName}" to "${newName}"...`,
          () => apiClient.post('/UpdateBridgeName', {
            currentBridgeName: oldName,
            newBridgeName: newName,
            regionName: opts.region,
          }),
          `Bridge renamed to "${newName}"`
        )
      } catch (error) {
        handleError(error)
      }
    })

  // bridge delete
  bridge
    .command('delete <name>')
    .description('Delete a bridge')
    .option('-r, --region <name>', 'Region name')
    .option('-f, --force', 'Skip confirmation')
    .action(async (name, options) => {
      try {
        await authService.requireAuth()
        const opts = await contextService.applyDefaults(options)

        if (!opts.region) {
          outputService.error('Region name required. Use --region or set context.')
          process.exit(1)
        }

        if (!options.force) {
          const { askConfirm } = await import('../utils/prompt.js')
          const confirm = await askConfirm(`Delete bridge "${name}"? This cannot be undone.`)
          if (!confirm) {
            outputService.info('Cancelled')
            return
          }
        }

        await withSpinner(
          `Deleting bridge "${name}"...`,
          () => apiClient.post('/DeleteBridge', {
            bridgeName: name,
            regionName: opts.region,
          }),
          `Bridge "${name}" deleted`
        )
      } catch (error) {
        handleError(error)
      }
    })

  // bridge reset-auth
  bridge
    .command('reset-auth <name>')
    .description('Reset bridge authorization token')
    .option('-r, --region <name>', 'Region name')
    .action(async (name, options) => {
      try {
        await authService.requireAuth()
        const opts = await contextService.applyDefaults(options)

        if (!opts.region) {
          outputService.error('Region name required. Use --region or set context.')
          process.exit(1)
        }

        const response = await withSpinner(
          `Resetting authorization for bridge "${name}"...`,
          () => apiClient.post('/ResetBridgeAuthorization', {
            bridgeName: name,
            regionName: opts.region,
          }),
          'Authorization reset'
        )

        const data = getFirstRow<BridgeAuthResponse>(response.resultSets)
        if (data?.authToken) {
          outputService.success(`New token: ${data.authToken}`)
        }
      } catch (error) {
        handleError(error)
      }
    })
}
