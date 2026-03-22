import { Command } from 'commander';
import { t } from '../../i18n/index.js';
import { registerOpsCheckCommand } from './check.js';
import { registerOpsDownCommand } from './down.js';
import { registerOpsSetupCommand } from './setup.js';
import { registerOpsSSHCommand } from './ssh.js';
import { registerOpsStatusCommand } from './status.js';
import { registerOpsUpCommand } from './up.js';

export function registerOpsCommands(program: Command): void {
  const ops = program
    .command('ops')
    .summary(t('commands.ops.descriptionShort'))
    .description(t('commands.ops.description'));

  registerOpsUpCommand(ops, program);
  registerOpsDownCommand(ops, program);
  registerOpsStatusCommand(ops, program);
  registerOpsSSHCommand(ops, program);
  registerOpsSetupCommand(ops, program);
  registerOpsCheckCommand(ops, program);
}
