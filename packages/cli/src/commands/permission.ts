import { Command } from 'commander';
import { api } from '../services/api.js';
import { authService } from '../services/auth.js';
import { outputService } from '../services/output.js';
import { handleError } from '../utils/errors.js';
import { withSpinner } from '../utils/spinner.js';
import type { OutputFormat } from '../types/index.js';
export function registerPermissionCommands(program: Command): void {
  const permission = program.command('permission').description('Permission management commands');

  // permission group subcommand
  const group = permission.command('group').description('Permission group management');

  // permission group list
  group
    .command('list')
    .description('List all permission groups')
    .action(async () => {
      try {
        await authService.requireAuth();

        const groups = await withSpinner(
          'Fetching permission groups...',
          () => api.permissions.listGroups(),
          'Permission groups fetched'
        );

        const format = program.opts().output as OutputFormat;

        outputService.print(groups, format);
      } catch (error) {
        handleError(error);
      }
    });

  // permission group create
  group
    .command('create <name>')
    .description('Create a new permission group')
    .action(async (name) => {
      try {
        await authService.requireAuth();

        await withSpinner(
          `Creating permission group "${name}"...`,
          () => api.permissions.createGroup(name),
          `Permission group "${name}" created`
        );
      } catch (error) {
        handleError(error);
      }
    });

  // permission group delete
  group
    .command('delete <name>')
    .description('Delete a permission group')
    .option('-f, --force', 'Skip confirmation')
    .action(async (name, options) => {
      try {
        await authService.requireAuth();

        if (!options.force) {
          const { askConfirm } = await import('../utils/prompt.js');
          const confirm = await askConfirm(`Delete permission group "${name}"?`);
          if (!confirm) {
            outputService.info('Cancelled');
            return;
          }
        }

        await withSpinner(
          `Deleting permission group "${name}"...`,
          () => api.permissions.deleteGroup(name),
          `Permission group "${name}" deleted`
        );
      } catch (error) {
        handleError(error);
      }
    });

  // permission group show
  group
    .command('show <name>')
    .description('Show permission group details')
    .action(async (name) => {
      try {
        await authService.requireAuth();

        const details = await withSpinner(
          'Fetching permission group details...',
          () => api.permissions.getGroupDetails(name),
          'Details fetched'
        );

        const format = program.opts().output as OutputFormat;

        outputService.print(details, format);
      } catch (error) {
        handleError(error);
      }
    });

  // permission add
  permission
    .command('add <groupName> <permission>')
    .description('Add a permission to a group')
    .action(async (groupName, permissionName) => {
      try {
        await authService.requireAuth();

        await withSpinner(
          `Adding permission "${permissionName}" to group "${groupName}"...`,
          () => api.permissions.addPermission(groupName, permissionName),
          'Permission added'
        );
      } catch (error) {
        handleError(error);
      }
    });

  // permission remove
  permission
    .command('remove <groupName> <permission>')
    .description('Remove a permission from a group')
    .action(async (groupName, permissionName) => {
      try {
        await authService.requireAuth();

        await withSpinner(
          `Removing permission "${permissionName}" from group "${groupName}"...`,
          () => api.permissions.removePermission(groupName, permissionName),
          'Permission removed'
        );
      } catch (error) {
        handleError(error);
      }
    });
}
