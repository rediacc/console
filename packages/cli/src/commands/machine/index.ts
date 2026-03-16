import { Command } from 'commander';
import { t } from '../../i18n/index.js';
import { isAgentEnvironment } from '../../utils/agent-guard.js';
import { registerCloudCommands } from './cloud.js';
import { registerContainersCommand } from './containers.js';
import { registerCrudCommands } from './crud.js';
import { registerDeployBackupCommand } from './deploy-backup.js';
import { registerHealthCommand } from './health.js';
import { registerPruneCommand } from './prune.js';
import { registerRepositoriesCommand } from './repositories.js';
import { registerServicesCommand } from './services.js';
import { registerQueryCommand } from './status.js';
import { registerTestConnectionCommand } from './test-connection.js';
import { registerVaultStatusCommand } from './vault-status.js';

export function registerMachineCommands(program: Command): void {
  // Create machine command and register CRUD commands
  const machine = registerCrudCommands(program);
  machine.summary(t('commands.machine.descriptionShort'));

  // Register all other command modules
  registerVaultStatusCommand(machine, program);
  registerRepositoriesCommand(machine, program);
  registerHealthCommand(machine, program);
  registerContainersCommand(machine, program);
  registerServicesCommand(machine, program);
  registerTestConnectionCommand(machine, program);
  registerQueryCommand(machine, program);
  registerCloudCommands(machine, program);
  registerDeployBackupCommand(machine);
  registerPruneCommand(machine);

  machine.addHelpText(
    'after',
    `
${t('help.examples')}
  $ rdc machine query server-1                          ${t('help.machine.query')}
  $ rdc machine query server-1 --containers             ${t('help.machine.containers')}
  $ rdc machine query server-1 --system --output json   ${t('help.machine.health')}
`
  );

  if (isAgentEnvironment() || process.argv.includes('--help-all')) {
    machine.addHelpText('after', t('help.machine.keyConcepts'));
  }
}
