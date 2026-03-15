import { parseGetCephRbdSnapshots } from '@rediacc/shared/api';
import type {
  CreateCephRbdSnapshotParams,
  DeleteCephRbdSnapshotParams,
  GetCephRbdSnapshotsParams,
} from '@rediacc/shared/types';
import { Command } from 'commander';
import { t } from '../../i18n/index.js';
import { typedApi } from '../../services/api.js';
import { authService } from '../../services/auth.js';
import { outputService } from '../../services/output.js';
import type { OutputFormat } from '../../types/index.js';
import { handleError } from '../../utils/errors.js';
import { withSpinner } from '../../utils/spinner.js';

export function registerSnapshotCommands(ceph: Command, program: Command): void {
  const snapshot = ceph.command('snapshot').description(t('commands.ceph.snapshot.description'));

  // snapshot list
  snapshot
    .command('list')
    .description(t('commands.ceph.snapshot.list.description'))
    .option('--image <name>', t('options.image'))
    .option('--pool <name>', t('options.pool'))
    .option('--team <name>', t('options.team'))
    .action(async (options: { image?: string; pool?: string; team?: string }) => {
      try {
        await authService.requireAuth();

        const params: GetCephRbdSnapshotsParams = {
          imageName: options.image,
          poolName: options.pool,
          teamName: options.team,
        };

        const apiResponse = await withSpinner(
          t('commands.ceph.snapshot.list.fetching'),
          () => typedApi.GetCephRbdSnapshots(params),
          t('commands.ceph.snapshot.list.success')
        );

        const snapshots = parseGetCephRbdSnapshots(apiResponse as never);
        const format = program.opts().output as OutputFormat;

        outputService.print(snapshots, format);
      } catch (error) {
        handleError(error);
      }
    });

  // snapshot create
  snapshot
    .command('create <name>')
    .description(t('commands.ceph.snapshot.create.description'))
    .requiredOption('--image <name>', t('options.image'))
    .requiredOption('--pool <name>', t('options.pool'))
    .requiredOption('--team <name>', t('options.team'))
    .option('--vault <content>', t('options.vaultContent'))
    .action(
      async (
        name: string,
        options: { image: string; pool: string; team: string; vault?: string }
      ) => {
        try {
          await authService.requireAuth();

          const params: CreateCephRbdSnapshotParams = {
            snapshotName: name,
            imageName: options.image,
            poolName: options.pool,
            teamName: options.team,
            vaultContent: options.vault,
          };

          await withSpinner(
            t('commands.ceph.snapshot.create.creating', { name }),
            () => typedApi.CreateCephRbdSnapshot(params),
            t('commands.ceph.snapshot.create.success', { name })
          );
        } catch (error) {
          handleError(error);
        }
      }
    );

  // snapshot delete
  snapshot
    .command('delete <name>')
    .description(t('commands.ceph.snapshot.delete.description'))
    .requiredOption('--image <name>', t('options.image'))
    .requiredOption('--pool <name>', t('options.pool'))
    .requiredOption('--team <name>', t('options.team'))
    .option('-f, --force', t('options.force'))
    .action(
      async (
        name: string,
        options: { image: string; pool: string; team: string; force?: boolean }
      ) => {
        try {
          await authService.requireAuth();

          if (!options.force) {
            const { askConfirm } = await import('../../utils/prompt.js');
            const confirm = await askConfirm(t('commands.ceph.snapshot.delete.confirm', { name }));
            if (!confirm) {
              outputService.info(t('prompts.cancelled'));
              return;
            }
          }

          const params: DeleteCephRbdSnapshotParams = {
            snapshotName: name,
            imageName: options.image,
            poolName: options.pool,
            teamName: options.team,
          };

          await withSpinner(
            t('commands.ceph.snapshot.delete.deleting', { name }),
            () => typedApi.DeleteCephRbdSnapshot(params),
            t('commands.ceph.snapshot.delete.success', { name })
          );
        } catch (error) {
          handleError(error);
        }
      }
    );
}
