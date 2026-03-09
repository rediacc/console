import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { registerRepoBackupCommands } from './repo-backup.js';

export function registerBackupCommands(program: Command): void {
  const backup = program.command('backup').description(t('commands.backup.description'));

  // push, pull, list-backups
  registerRepoBackupCommands(backup);

  // sync subcommand group
  const sync = backup.command('sync').description(t('commands.backup.sync.description'));
  sync.command('help').action(() => sync.help());

  // schedule subcommand
  backup
    .command('schedule <machine>')
    .description(t('commands.backup.schedule.description'))
    .option('--debug', t('options.debug'))
    .action(async (machine, options) => {
      const { pushBackupSchedule } = await import('../services/backup-schedule.js');
      await pushBackupSchedule(machine, options);
    });
}
