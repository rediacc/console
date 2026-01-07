import { Command } from 'commander';
import {
  parseGetOrganizationPermissionGroups,
  parseGetPermissionGroupDetails,
} from '@rediacc/shared/api';
import { t } from '../i18n/index.js';
import { typedApi } from '../services/api.js';
import { authService } from '../services/auth.js';
import { outputService } from '../services/output.js';
import { handleError } from '../utils/errors.js';
import { withSpinner } from '../utils/spinner.js';
import type { OutputFormat } from '../types/index.js';
export function registerPermissionCommands(program: Command): void {
  const permission = program
    .command('permission')
    .description(t('commands.permission.description'));

  // permission group subcommand
  const group = permission.command('group').description(t('commands.permission.group.description'));

  // permission group list
  group
    .command('list')
    .description(t('commands.permission.group.list.description'))
    .action(async () => {
      try {
        await authService.requireAuth();

        const apiResponse = await withSpinner(
          t('commands.permission.group.list.fetching'),
          () => typedApi.GetOrganizationPermissionGroups({}),
          t('commands.permission.group.list.success')
        );

        const groups = parseGetOrganizationPermissionGroups(apiResponse as never);
        const format = program.opts().output as OutputFormat;

        outputService.print(groups, format);
      } catch (error) {
        handleError(error);
      }
    });

  // permission group create
  group
    .command('create <name>')
    .description(t('commands.permission.group.create.description'))
    .action(async (name: string) => {
      try {
        await authService.requireAuth();

        await withSpinner(
          t('commands.permission.group.create.creating', { name }),
          () => typedApi.CreatePermissionGroup({ permissionGroupName: name }),
          t('commands.permission.group.create.success', { name })
        );
      } catch (error) {
        handleError(error);
      }
    });

  // permission group delete
  group
    .command('delete <name>')
    .description(t('commands.permission.group.delete.description'))
    .option('-f, --force', t('options.force'))
    .action(async (name: string, options: { force?: boolean }) => {
      try {
        await authService.requireAuth();

        if (!options.force) {
          const { askConfirm } = await import('../utils/prompt.js');
          const confirm = await askConfirm(t('commands.permission.group.delete.confirm', { name }));
          if (!confirm) {
            outputService.info(t('prompts.cancelled'));
            return;
          }
        }

        await withSpinner(
          t('commands.permission.group.delete.deleting', { name }),
          () => typedApi.DeletePermissionGroup({ permissionGroupName: name }),
          t('commands.permission.group.delete.success', { name })
        );
      } catch (error) {
        handleError(error);
      }
    });

  // permission group show
  group
    .command('show <name>')
    .description(t('commands.permission.group.show.description'))
    .action(async (name: string) => {
      try {
        await authService.requireAuth();

        const apiResponse = await withSpinner(
          t('commands.permission.group.show.fetching'),
          () => typedApi.GetPermissionGroupDetails({ permissionGroupName: name }),
          t('commands.permission.group.show.success')
        );

        const details = parseGetPermissionGroupDetails(apiResponse as never);
        const format = program.opts().output as OutputFormat;

        outputService.print(details, format);
      } catch (error) {
        handleError(error);
      }
    });

  // permission add
  permission
    .command('add <groupName> <permission>')
    .description(t('commands.permission.add.description'))
    .action(async (groupName: string, permissionName: string) => {
      try {
        await authService.requireAuth();

        await withSpinner(
          t('commands.permission.add.adding', { permission: permissionName, group: groupName }),
          () =>
            typedApi.CreatePermissionInGroup({ permissionGroupName: groupName, permissionName }),
          t('commands.permission.add.success')
        );
      } catch (error) {
        handleError(error);
      }
    });

  // permission remove
  permission
    .command('remove <groupName> <permission>')
    .description(t('commands.permission.remove.description'))
    .action(async (groupName: string, permissionName: string) => {
      try {
        await authService.requireAuth();

        await withSpinner(
          t('commands.permission.remove.removing', {
            permission: permissionName,
            group: groupName,
          }),
          () =>
            typedApi.DeletePermissionFromGroup({ permissionGroupName: groupName, permissionName }),
          t('commands.permission.remove.success')
        );
      } catch (error) {
        handleError(error);
      }
    });
}
