import { Command } from 'commander';
import { parseGetCloneMachines } from '@rediacc/shared/api';
import type {
  GetCloneMachinesParams,
  UpdateCloneMachineAssignmentsParams,
  UpdateCloneMachineRemovalsParams,
} from '@rediacc/shared/types';
import { t } from '../../i18n/index.js';
import { typedApi } from '../../services/api.js';
import { authService } from '../../services/auth.js';
import { outputService } from '../../services/output.js';
import { addCloudOnlyGuard, markCloudOnly } from '../../utils/cloud-guard.js';
import { handleError } from '../../utils/errors.js';
import { withSpinner } from '../../utils/spinner.js';
import { getOrCreateCommand } from '../bridge-utils.js';
import type { OutputFormat } from '../../types/index.js';

export function registerCloneCommands(ceph: Command, program: Command): void {
  const clone = getOrCreateCommand(ceph, 'clone', t('commands.ceph.clone.description'));

  // clone machines (cloud-only)
  const machinesCmd = clone
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
  addCloudOnlyGuard(machinesCmd);
  markCloudOnly(machinesCmd);

  // clone assign (cloud-only)
  const assignCmd = clone
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
  addCloudOnlyGuard(assignCmd);
  markCloudOnly(assignCmd);

  // clone unassign (cloud-only)
  const unassignCmd = clone
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
  addCloudOnlyGuard(unassignCmd);
  markCloudOnly(unassignCmd);
}
