import { Command } from 'commander';
import { registerContainersCommand } from './containers.js';
import { registerCrudCommands } from './crud.js';
import { registerHealthCommand } from './health.js';
import { registerRepositoriesCommand } from './repositories.js';
import { registerServicesCommand } from './services.js';
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
}
