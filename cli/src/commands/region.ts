import { Command } from 'commander'
import { authService } from '../services/auth.js'
import { apiClient } from '../services/api.js'
import { outputService } from '../services/output.js'
import { withSpinner } from '../utils/spinner.js'
import { handleError } from '../utils/errors.js'
import type { OutputFormat } from '../types/index.js'

export function registerRegionCommands(program: Command): void {
  const region = program
    .command('region')
    .description('Region management commands')

  // region list
  region
    .command('list')
    .description('List all regions')
    .action(async () => {
      try {
        await authService.requireAuth()

        const response = await withSpinner(
          'Fetching regions...',
          () => apiClient.get('/GetCompanyRegions', {}),
          'Regions fetched'
        )

        const regions = response.resultSets?.[0]?.data || []
        const format = program.opts().output as OutputFormat

        outputService.print(regions, format)
      } catch (error) {
        handleError(error)
      }
    })

  // region create
  region
    .command('create <name>')
    .description('Create a new region')
    .action(async (name) => {
      try {
        await authService.requireAuth()

        await withSpinner(
          `Creating region "${name}"...`,
          () => apiClient.post('/CreateRegion', { regionName: name }),
          `Region "${name}" created`
        )
      } catch (error) {
        handleError(error)
      }
    })

  // region rename
  region
    .command('rename <oldName> <newName>')
    .description('Rename a region')
    .action(async (oldName, newName) => {
      try {
        await authService.requireAuth()

        await withSpinner(
          `Renaming region "${oldName}" to "${newName}"...`,
          () => apiClient.post('/UpdateRegionName', {
            currentRegionName: oldName,
            newRegionName: newName,
          }),
          `Region renamed to "${newName}"`
        )
      } catch (error) {
        handleError(error)
      }
    })

  // region delete
  region
    .command('delete <name>')
    .description('Delete a region')
    .option('-f, --force', 'Skip confirmation')
    .action(async (name, options) => {
      try {
        await authService.requireAuth()

        if (!options.force) {
          const { askConfirm } = await import('../utils/prompt.js')
          const confirm = await askConfirm(`Delete region "${name}"? This cannot be undone.`)
          if (!confirm) {
            outputService.info('Cancelled')
            return
          }
        }

        await withSpinner(
          `Deleting region "${name}"...`,
          () => apiClient.post('/DeleteRegion', { regionName: name }),
          `Region "${name}" deleted`
        )
      } catch (error) {
        handleError(error)
      }
    })
}
