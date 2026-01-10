import { Command } from 'commander';
import { parseGetCephRbdClones, parseGetCloneMachines } from '@rediacc/shared/api';
import type {
  CreateCephRbdCloneParams,
  DeleteCephRbdCloneParams,
  GetCephRbdClonesParams,
  GetCloneMachinesParams,
  UpdateCloneMachineAssignmentsParams,
  UpdateCloneMachineRemovalsParams,
} from '@rediacc/shared/types';
import { t } from '../../i18n/index.js';
import { typedApi } from '../../services/api.js';
import { authService } from '../../services/auth.js';
import { outputService } from '../../services/output.js';
import { handleError } from '../../utils/errors.js';
import { withSpinner } from '../../utils/spinner.js';
import type { OutputFormat } from '../../types/index.js';

export function registerCloneCommands(ceph: Command, program: Command): void {
  const clone = ceph.command('clone').description(t('commands.ceph.clone.description'));

  // clone list
  clone
    .command('list')
    .description(t('commands.ceph.clone.list.description'))
    .option('--snapshot <name>', t('options.snapshot'))
    .option('--image <name>', t('options.image'))
    .option('--pool <name>', t('options.pool'))
    .option('--team <name>', t('options.team'))
    .action(
      async (options: { snapshot?: string; image?: string; pool?: string; team?: string }) => {
        try {
          await authService.requireAuth();

          const params: GetCephRbdClonesParams = {
            snapshotName: options.snapshot,
            imageName: options.image,
            poolName: options.pool,
            teamName: options.team,
          };

          const apiResponse = await withSpinner(
            t('commands.ceph.clone.list.fetching'),
            () => typedApi.GetCephRbdClones(params),
            t('commands.ceph.clone.list.success')
          );

          const clones = parseGetCephRbdClones(apiResponse as never);
          const format = program.opts().output as OutputFormat;

          outputService.print(clones, format);
        } catch (error) {
          handleError(error);
        }
      }
    );

  // clone create
  clone
    .command('create <name>')
    .description(t('commands.ceph.clone.create.description'))
    .requiredOption('--snapshot <name>', t('options.snapshot'))
    .requiredOption('--image <name>', t('options.image'))
    .requiredOption('--pool <name>', t('options.pool'))
    .requiredOption('--team <name>', t('options.team'))
    .option('--vault <content>', t('options.vaultContent'))
    .action(
      async (
        name: string,
        options: { snapshot: string; image: string; pool: string; team: string; vault?: string }
      ) => {
        try {
          await authService.requireAuth();

          const params: CreateCephRbdCloneParams = {
            cloneName: name,
            snapshotName: options.snapshot,
            imageName: options.image,
            poolName: options.pool,
            teamName: options.team,
            vaultContent: options.vault ?? '',
          };

          await withSpinner(
            t('commands.ceph.clone.create.creating', { name }),
            () => typedApi.CreateCephRbdClone(params),
            t('commands.ceph.clone.create.success', { name })
          );
        } catch (error) {
          handleError(error);
        }
      }
    );

  // clone delete
  clone
    .command('delete <name>')
    .description(t('commands.ceph.clone.delete.description'))
    .requiredOption('--snapshot <name>', t('options.snapshot'))
    .requiredOption('--image <name>', t('options.image'))
    .requiredOption('--pool <name>', t('options.pool'))
    .requiredOption('--team <name>', t('options.team'))
    .option('-f, --force', t('options.force'))
    .action(
      async (
        name: string,
        options: { snapshot: string; image: string; pool: string; team: string; force?: boolean }
      ) => {
        try {
          await authService.requireAuth();

          if (!options.force) {
            const { askConfirm } = await import('../../utils/prompt.js');
            const confirm = await askConfirm(t('commands.ceph.clone.delete.confirm', { name }));
            if (!confirm) {
              outputService.info(t('prompts.cancelled'));
              return;
            }
          }

          const params: DeleteCephRbdCloneParams = {
            cloneName: name,
            snapshotName: options.snapshot,
            imageName: options.image,
            poolName: options.pool,
            teamName: options.team,
          };

          await withSpinner(
            t('commands.ceph.clone.delete.deleting', { name }),
            () => typedApi.DeleteCephRbdClone(params),
            t('commands.ceph.clone.delete.success', { name })
          );
        } catch (error) {
          handleError(error);
        }
      }
    );

  // clone machines
  clone
    .command('machines <name>')
    .description(t('commands.ceph.clone.machines.description'))
    .requiredOption('--snapshot <name>', t('options.snapshot'))
    .requiredOption('--image <name>', t('options.image'))
    .requiredOption('--pool <name>', t('options.pool'))
    .requiredOption('--team <name>', t('options.team'))
    .action(
      async (
        name: string,
        options: { snapshot: string; image: string; pool: string; team: string }
      ) => {
        try {
          await authService.requireAuth();

          const params: GetCloneMachinesParams = {
            cloneName: name,
            snapshotName: options.snapshot,
            imageName: options.image,
            poolName: options.pool,
            teamName: options.team,
          };

          const apiResponse = await withSpinner(
            t('commands.ceph.clone.machines.fetching'),
            () => typedApi.GetCloneMachines(params),
            t('commands.ceph.clone.machines.success')
          );

          const machines = parseGetCloneMachines(apiResponse as never);
          const format = program.opts().output as OutputFormat;

          outputService.print(machines, format);
        } catch (error) {
          handleError(error);
        }
      }
    );

  // clone assign
  clone
    .command('assign <name>')
    .description(t('commands.ceph.clone.assign.description'))
    .requiredOption('--snapshot <name>', t('options.snapshot'))
    .requiredOption('--image <name>', t('options.image'))
    .requiredOption('--pool <name>', t('options.pool'))
    .requiredOption('--team <name>', t('options.team'))
    .requiredOption('--machines <names>', t('options.machineNames'))
    .action(
      async (
        name: string,
        options: { snapshot: string; image: string; pool: string; team: string; machines: string }
      ) => {
        try {
          await authService.requireAuth();

          const params: UpdateCloneMachineAssignmentsParams = {
            cloneName: name,
            snapshotName: options.snapshot,
            imageName: options.image,
            poolName: options.pool,
            teamName: options.team,
            machineNames: options.machines,
          };

          await withSpinner(
            t('commands.ceph.clone.assign.assigning', { name }),
            () => typedApi.UpdateCloneMachineAssignments(params),
            t('commands.ceph.clone.assign.success', { name })
          );
        } catch (error) {
          handleError(error);
        }
      }
    );

  // clone unassign
  clone
    .command('unassign <name>')
    .description(t('commands.ceph.clone.unassign.description'))
    .requiredOption('--snapshot <name>', t('options.snapshot'))
    .requiredOption('--image <name>', t('options.image'))
    .requiredOption('--pool <name>', t('options.pool'))
    .requiredOption('--team <name>', t('options.team'))
    .requiredOption('--machines <names>', t('options.machineNames'))
    .action(
      async (
        name: string,
        options: { snapshot: string; image: string; pool: string; team: string; machines: string }
      ) => {
        try {
          await authService.requireAuth();

          const params: UpdateCloneMachineRemovalsParams = {
            cloneName: name,
            snapshotName: options.snapshot,
            imageName: options.image,
            poolName: options.pool,
            teamName: options.team,
            machineNames: options.machines,
          };

          await withSpinner(
            t('commands.ceph.clone.unassign.unassigning', { name }),
            () => typedApi.UpdateCloneMachineRemovals(params),
            t('commands.ceph.clone.unassign.success', { name })
          );
        } catch (error) {
          handleError(error);
        }
      }
    );
}
