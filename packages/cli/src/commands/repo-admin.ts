import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import type { OutputFormat } from '../types/index.js';
import { handleError } from '../utils/errors.js';

/** `repo admin archive {list,restore,purge}` — archived-record bookkeeping. */
function registerArchive(admin: Command, program: Command): void {
  const archive = admin
    .command('archive')
    .description(t('commands.repo.admin.archive.description'));

  archive
    .command('list')
    .description(t('commands.repo.admin.archive.list.description'))
    .action(async () => {
      try {
        const archived = await configService.listArchivedRepositories();
        const format = program.opts().output as OutputFormat;

        if (archived.length === 0) {
          outputService.info(t('commands.repo.admin.archive.list.noArchived'));
          return;
        }

        outputService.print(
          archived.map((r) => ({
            name: r.name,
            tag: r.tag,
            guid: r.repositoryGuid,
            credential: r.credential ? 'set' : '-',
            deletedAt: r.deletedAt,
          })),
          format
        );
      } catch (error) {
        handleError(error);
      }
    });

  archive
    .command('restore')
    .argument('<name>', t('options.name'))
    .description(t('commands.repo.admin.archive.restore.description'))
    .option('--new-name <name>', t('options.newName'))
    .action(async (name: string, options: { newName?: string }) => {
      try {
        const restoredName = await configService.restoreArchivedRepository(name, options.newName);
        outputService.success(
          t('commands.repo.admin.archive.restore.success', { name: restoredName, guid: name })
        );
      } catch (error) {
        handleError(error);
      }
    });

  archive
    .command('purge')
    .argument('[name]', t('options.name'))
    .description(t('commands.repo.admin.archive.purge.description'))
    .option('-y, --yes', t('options.yes'))
    .action(async (_name: string | undefined, options: { yes?: boolean }) => {
      try {
        if (!options.yes) {
          const { askConfirm } = await import('../utils/prompt.js');
          const confirmed = await askConfirm(t('commands.repo.admin.archive.purge.confirm'));
          if (!confirmed) {
            outputService.info(t('status.cancelled'));
            return;
          }
        }
        const count = await configService.purgeArchivedRepositories();
        if (count === 0) {
          outputService.info(t('commands.repo.admin.archive.purge.noArchived'));
        } else {
          outputService.success(t('commands.repo.admin.archive.purge.success', { count }));
        }
      } catch (error) {
        handleError(error);
      }
    });
}

/**
 * Create the `repo admin` parent — the niche plumbing verbs moved off the daily
 * surface (spec/03 §5.4). `archive` lands here; the rest of the subtree
 * (validate/fsck/ownership/autostart/template) is registered onto the returned
 * parent by repo-maintenance.ts and repo-extended.ts, which own those verbs'
 * implementations. The parent is created once and handed to them.
 */
export function createRepoAdminCommand(repo: Command, program: Command): Command {
  const admin = repo.command('admin').description(t('commands.repo.admin.description'));
  registerArchive(admin, program);
  return admin;
}
