import type { Command } from 'commander';
import { t } from '../../i18n/index.js';
import { outputService } from '../../services/output.js';
import { handleError } from '../../utils/errors.js';

export function registerDeployBackupCommand(machine: Command): void {
  const backup = machine.command('backup').description(t('commands.machine.backup.description'));

  backup
    .command('schedule <machine>')
    .description(t('commands.machine.backup.schedule.description'))
    .option('--debug', t('options.debug'))
    .action(async (machineName, options) => {
      try {
        const { pushBackupSchedule } = await import('../../services/backup-schedule.js');
        await pushBackupSchedule(machineName, { debug: options.debug });
        outputService.success(
          t('commands.machine.backup.schedule.success', { machine: machineName })
        );
      } catch (error) {
        handleError(error);
      }
    });
}
