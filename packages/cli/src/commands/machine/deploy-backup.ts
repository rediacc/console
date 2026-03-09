import type { Command } from 'commander';
import { t } from '../../i18n/index.js';
import { outputService } from '../../services/output.js';
import { handleError } from '../../utils/errors.js';

export function registerDeployBackupCommand(machine: Command): void {
  machine
    .command('deploy-backup <machine>')
    .description(t('commands.machine.deployBackup.description'))
    .option('--debug', t('options.debug'))
    .action(async (machineName, options) => {
      try {
        const { pushBackupSchedule } = await import('../../services/backup-schedule.js');
        await pushBackupSchedule(machineName, { debug: options.debug });
        outputService.success(t('commands.machine.deployBackup.success', { machine: machineName }));
      } catch (error) {
        handleError(error);
      }
    });
}
