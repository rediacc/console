import type { Command } from 'commander';
import { t } from '../../i18n/index.js';
import { isAgentEnvironment } from '../../utils/agent-guard.js';
import { registerHealthCommand } from './health.js';
import { registerInfraCommands } from './infra.js';
import { registerProviderCommands } from './provider.js';
import { registerCloudCommands } from './provision.js';
import { registerPruneCommand } from './prune.js';
import { registerMachineRegistrationCommands } from './register.js';
import { registerStatusCommand } from './status.js';

export function registerMachineCommands(program: Command): void {
  const machine = program
    .command('machine')
    .summary(t('commands.machine.descriptionShort'))
    .description(t('commands.machine.description'));

  // Config-CRUD + lifecycle: add/remove/list/scan-keys/setup, then the
  // machine-reaching verbs. `machine query` is now `machine status` and folds in
  // the retired containers/services/repos section commands as flags.
  registerMachineRegistrationCommands(machine, program);
  registerStatusCommand(machine, program);
  registerHealthCommand(machine, program);
  registerCloudCommands(machine, program);
  registerPruneCommand(machine);
  registerProviderCommands(machine, program);
  registerInfraCommands(machine, program);

  machine.addHelpText(
    'after',
    `
${t('help.examples')}
  $ rdc machine status server-1                          ${t('help.machine.query')}
  $ rdc machine status server-1 --containers             ${t('help.machine.containers')}
  $ rdc machine status server-1 --system   ${t('help.machine.health')}
`
  );

  if (isAgentEnvironment() || process.argv.includes('--help-all')) {
    machine.addHelpText('after', t('help.machine.keyConcepts'));
  }
}
