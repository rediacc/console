import { Command } from 'commander';
import { t } from '../../i18n/index.js';
import { registerCloudCommands } from './cloud.js';
import { registerContainersCommand } from './containers.js';
import { registerCrudCommands } from './crud.js';
import { registerHealthCommand } from './health.js';
import { registerRepositoriesCommand } from './repositories.js';
import { registerServicesCommand } from './services.js';
import { registerDeployBackupCommand } from './deploy-backup.js';
import { registerStatusCommand } from './status.js';
import { registerTestConnectionCommand } from './test-connection.js';
import { registerVaultStatusCommand } from './vault-status.js';

export function registerMachineCommands(program: Command): void {
  // Create machine command and register CRUD commands
  const machine = registerCrudCommands(program);

  // Register all other command modules
  registerVaultStatusCommand(machine, program);
  registerRepositoriesCommand(machine, program);
  registerHealthCommand(machine, program);
  registerContainersCommand(machine, program);
  registerServicesCommand(machine, program);
  registerTestConnectionCommand(machine, program);
  registerStatusCommand(machine, program);
  registerCloudCommands(machine, program);
  registerDeployBackupCommand(machine);

  machine.addHelpText(
    'after',
    `
${t('help.examples')}
  $ rdc machine info server-1                  ${t('help.machine.info')}
  $ rdc machine containers server-1            ${t('help.machine.containers')}
  $ rdc machine health server-1 --output json  ${t('help.machine.health')}
`
  );
}
