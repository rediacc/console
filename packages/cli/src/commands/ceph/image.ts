import { Command } from 'commander';
import { parseGetCephRbdImages } from '@rediacc/shared/api';
import type {
  CreateCephRbdImageParams,
  DeleteCephRbdImageParams,
  GetCephRbdImagesParams,
} from '@rediacc/shared/types';
import { t } from '../../i18n/index.js';
import { typedApi } from '../../services/api.js';
import { authService } from '../../services/auth.js';
import { outputService } from '../../services/output.js';
import { handleError } from '../../utils/errors.js';
import { withSpinner } from '../../utils/spinner.js';
import type { OutputFormat } from '../../types/index.js';

export function registerImageCommands(ceph: Command, program: Command): void {
  const image = ceph.command('image').description(t('commands.ceph.image.description'));

  // image list
  image
    .command('list')
    .description(t('commands.ceph.image.list.description'))
    .option('--pool <name>', t('options.pool'))
    .option('--team <name>', t('options.team'))
    .action(async (options: { pool?: string; team?: string }) => {
      try {
        await authService.requireAuth();

        const params: GetCephRbdImagesParams = {
          poolName: options.pool,
          teamName: options.team,
        };

        const apiResponse = await withSpinner(
          t('commands.ceph.image.list.fetching'),
          () => typedApi.GetCephRbdImages(params),
          t('commands.ceph.image.list.success')
        );

        const images = parseGetCephRbdImages(apiResponse as never);
        const format = program.opts().output as OutputFormat;

        outputService.print(images, format);
      } catch (error) {
        handleError(error);
      }
    });

  // image create
  image
    .command('create <name>')
    .description(t('commands.ceph.image.create.description'))
    .requiredOption('--pool <name>', t('options.pool'))
    .requiredOption('--team <name>', t('options.team'))
    .requiredOption('--machine <name>', t('options.machine'))
    .option('--vault <content>', t('options.vaultContent'))
    .action(
      async (
        name: string,
        options: { pool: string; team: string; machine: string; vault?: string }
      ) => {
        try {
          await authService.requireAuth();

          const params: CreateCephRbdImageParams = {
            imageName: name,
            poolName: options.pool,
            teamName: options.team,
            machineName: options.machine,
            vaultContent: options.vault,
          };

          await withSpinner(
            t('commands.ceph.image.create.creating', { name }),
            () => typedApi.CreateCephRbdImage(params),
            t('commands.ceph.image.create.success', { name })
          );
        } catch (error) {
          handleError(error);
        }
      }
    );

  // image delete
  image
    .command('delete <name>')
    .description(t('commands.ceph.image.delete.description'))
    .requiredOption('--pool <name>', t('options.pool'))
    .requiredOption('--team <name>', t('options.team'))
    .option('-f, --force', t('options.force'))
    .action(async (name: string, options: { pool: string; team: string; force?: boolean }) => {
      try {
        await authService.requireAuth();

        if (!options.force) {
          const { askConfirm } = await import('../../utils/prompt.js');
          const confirm = await askConfirm(t('commands.ceph.image.delete.confirm', { name }));
          if (!confirm) {
            outputService.info(t('prompts.cancelled'));
            return;
          }
        }

        const params: DeleteCephRbdImageParams = {
          imageName: name,
          poolName: options.pool,
          teamName: options.team,
        };

        await withSpinner(
          t('commands.ceph.image.delete.deleting', { name }),
          () => typedApi.DeleteCephRbdImage(params),
          t('commands.ceph.image.delete.success', { name })
        );
      } catch (error) {
        handleError(error);
      }
    });
}
