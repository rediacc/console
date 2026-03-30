import type { Command } from 'commander';
import { t } from '../../i18n/index.js';
import { outputService } from '../../services/output.js';
import { handleError } from '../../utils/errors.js';

export function registerDeployBackupCommand(machine: Command): void {
  const backup = machine.command('backup').description(t('commands.machine.backup.description'));

  backup
    .command('schedule')
    .description(t('commands.machine.backup.schedule.description'))
    .requiredOption('-m, --machine <name>', t('options.machine'))
    .option('--debug', t('options.debug'))
    .action(async (options) => {
      try {
        const machineName = options.machine;
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
