import { Command } from 'commander';
import { registerAuditCommands } from './commands/audit.js';
import { registerAuthCommands } from './commands/auth.js';
import { registerBridgeCommands } from './commands/bridge.js';
import { registerCompanyCommands } from './commands/company.js';
import { registerContextCommands } from './commands/context.js';
import { registerMachineCommands } from './commands/machine.js';
import { registerPermissionCommands } from './commands/permission.js';
import { registerQueueCommands } from './commands/queue.js';
import { registerRegionCommands } from './commands/region.js';
import { registerRepositoryCommands } from './commands/repository.js';
import { registerShortcuts } from './commands/shortcuts.js';
import { registerStorageCommands } from './commands/storage.js';
import { registerTeamCommands } from './commands/team.js';
import { registerUserCommands } from './commands/user.js';
import { contextService } from './services/context.js';
import { setOutputFormat } from './utils/errors.js';
import { VERSION } from './version.js';
import type { OutputFormat } from './types/index.js';

export const cli = new Command();

cli
  .name('rdc')
  .description('Rediacc Console CLI - Command line interface for Rediacc operations')
  .version(VERSION)
  .option('-o, --output <format>', 'Output format (table|json|yaml|csv)', 'table')
  .option('-C, --context <name>', 'Use specific context for this command')
  .hook('preAction', (thisCommand) => {
    const opts = thisCommand.opts();
    // Set output format before any command runs
    setOutputFormat(opts.output as OutputFormat);
    // Set runtime context override if --context flag is provided
    if (opts.context) {
      contextService.setRuntimeContext(opts.context);
    }
  });

// Register all command groups
registerAuthCommands(cli);
registerTeamCommands(cli);
registerMachineCommands(cli);
registerRepositoryCommands(cli);
registerStorageCommands(cli);
registerQueueCommands(cli);
registerRegionCommands(cli);
registerBridgeCommands(cli);
registerCompanyCommands(cli);
registerUserCommands(cli);
registerContextCommands(cli);
registerPermissionCommands(cli);
registerAuditCommands(cli);
registerShortcuts(cli);
