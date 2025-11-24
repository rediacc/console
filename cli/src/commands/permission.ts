import { Command } from 'commander'
import { authService } from '../services/auth.js'
import { apiClient } from '../services/api.js'
import { outputService } from '../services/output.js'
import { withSpinner } from '../utils/spinner.js'
import { handleError } from '../utils/errors.js'
import type { OutputFormat } from '../types/index.js'

export function registerPermissionCommands(program: Command): void {
  const permission = program
    .command('permission')
    .description('Permission management commands')

  // permission group subcommand
  const group = permission
    .command('group')
    .description('Permission group management')

  // permission group list
  group
    .command('list')
    .description('List all permission groups')
    .action(async () => {
      try {
        await authService.requireAuth()

        const response = await withSpinner(
          'Fetching permission groups...',
          () => apiClient.get('/GetCompanyPermissionGroups', {}),
          'Permission groups fetched'
        )

        const groups = response.resultSets?.[0]?.data || []
        const format = program.opts().output as OutputFormat

        outputService.print(groups, format)
      } catch (error) {
        handleError(error)
      }
    })

  // permission group create
  group
    .command('create <name>')
    .description('Create a new permission group')
    .action(async (name) => {
      try {
        await authService.requireAuth()

        await withSpinner(
          `Creating permission group "${name}"...`,
          () => apiClient.post('/CreatePermissionGroup', { groupName: name }),
          `Permission group "${name}" created`
        )
      } catch (error) {
        handleError(error)
      }
    })

  // permission group delete
  group
    .command('delete <name>')
    .description('Delete a permission group')
    .option('-f, --force', 'Skip confirmation')
    .action(async (name, options) => {
      try {
        await authService.requireAuth()

        if (!options.force) {
          const { askConfirm } = await import('../utils/prompt.js')
          const confirm = await askConfirm(`Delete permission group "${name}"?`)
          if (!confirm) {
            outputService.info('Cancelled')
            return
          }
        }

        await withSpinner(
          `Deleting permission group "${name}"...`,
          () => apiClient.post('/DeletePermissionGroup', { groupName: name }),
          `Permission group "${name}" deleted`
        )
      } catch (error) {
        handleError(error)
      }
    })

  // permission group show
  group
    .command('show <name>')
    .description('Show permission group details')
    .action(async (name) => {
      try {
        await authService.requireAuth()

        const response = await withSpinner(
          'Fetching permission group details...',
          () => apiClient.get('/GetPermissionGroupDetails', { groupName: name }),
          'Details fetched'
        )

        const details = response.resultSets?.[0]?.data?.[0]
        const format = program.opts().output as OutputFormat

        if (details) {
          outputService.print(details, format)
        } else {
          outputService.info('Permission group not found')
        }
      } catch (error) {
        handleError(error)
      }
    })

  // permission add
  permission
    .command('add <groupName> <permission>')
    .description('Add a permission to a group')
    .action(async (groupName, permissionName) => {
      try {
        await authService.requireAuth()

        await withSpinner(
          `Adding permission "${permissionName}" to group "${groupName}"...`,
          () => apiClient.post('/CreatePermissionInGroup', {
            groupName,
            permissionName,
          }),
          'Permission added'
        )
      } catch (error) {
        handleError(error)
      }
    })

  // permission remove
  permission
    .command('remove <groupName> <permission>')
    .description('Remove a permission from a group')
    .action(async (groupName, permissionName) => {
      try {
        await authService.requireAuth()

        await withSpinner(
          `Removing permission "${permissionName}" from group "${groupName}"...`,
          () => apiClient.post('/DeletePermissionFromGroup', {
            groupName,
            permissionName,
          }),
          'Permission removed'
        )
      } catch (error) {
        handleError(error)
      }
    })
}
