import { Command } from 'commander'
import { registerAuthCommands } from './commands/auth.js'
import { registerTeamCommands } from './commands/team.js'
import { registerMachineCommands } from './commands/machine.js'
import { registerRepoCommands } from './commands/repo.js'
import { registerStorageCommands } from './commands/storage.js'
import { registerQueueCommands } from './commands/queue.js'
import { registerRegionCommands } from './commands/region.js'
import { registerBridgeCommands } from './commands/bridge.js'
import { registerCompanyCommands } from './commands/company.js'
import { registerUserCommands } from './commands/user.js'
import { registerContextCommands } from './commands/context.js'
import { registerPermissionCommands } from './commands/permission.js'
import { registerAuditCommands } from './commands/audit.js'
import { registerShortcuts } from './commands/shortcuts.js'

const VERSION = '1.0.0'

export const cli = new Command()

cli
  .name('rediacc')
  .description('Rediacc CLI - Command line interface for Rediacc operations')
  .version(VERSION)
  .option('-o, --output <format>', 'Output format (table|json|yaml|csv)', 'table')

// Register all command groups
registerAuthCommands(cli)
registerTeamCommands(cli)
registerMachineCommands(cli)
registerRepoCommands(cli)
registerStorageCommands(cli)
registerQueueCommands(cli)
registerRegionCommands(cli)
registerBridgeCommands(cli)
registerCompanyCommands(cli)
registerUserCommands(cli)
registerContextCommands(cli)
registerPermissionCommands(cli)
registerAuditCommands(cli)
registerShortcuts(cli)
