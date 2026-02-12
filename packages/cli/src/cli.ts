import { Command } from 'commander';
import { registerAuditCommands } from './commands/audit.js';
import { registerAuthCommands } from './commands/auth.js';
import { registerBridgeCommands } from './commands/bridge.js';
import { registerCephCommands } from './commands/ceph/index.js';
import { registerContextCommands } from './commands/context.js';
import { registerDoctorCommand } from './commands/doctor.js';
import { registerMachineCommands } from './commands/machine/index.js';
import { registerOrganizationCommands } from './commands/organization.js';
import { registerPermissionCommands } from './commands/permission.js';
import { registerProtocolCommands } from './commands/protocol.js';
import { registerQueueCommands } from './commands/queue.js';
import { registerRegionCommands } from './commands/region.js';
import { registerRepoCommands } from './commands/repo.js';
import { registerRepositoryCommands } from './commands/repository.js';
import { registerShortcuts } from './commands/shortcuts.js';
import { registerStorageCommands } from './commands/storage.js';
import { registerSyncCommands } from './commands/sync.js';
import { registerTeamCommands } from './commands/team.js';
import { registerTermCommands } from './commands/term.js';
import { registerUpdateCommand } from './commands/update.js';
import { registerUserCommands } from './commands/user.js';
import { registerVSCodeCommands } from './commands/vscode.js';
import { changeLanguage, initI18n, SUPPORTED_LANGUAGES, t } from './i18n/index.js';
import { contextService } from './services/context.js';
import { outputService } from './services/output.js';
import { telemetryService } from './services/telemetry.js';
import { addCloudOnlyGuard, markCloudOnly } from './utils/cloud-guard.js';
import { setOutputFormat } from './utils/errors.js';
import { VERSION } from './version.js';
import type { OutputFormat } from './types/index.js';

// Track if i18n has been initialized
let i18nInitialized = false;

// Track command context for telemetry
const commandContext = new Map<string, { startTime: number }>();

// Initialize telemetry at startup (non-blocking)
telemetryService.initialize({ serviceVersion: VERSION });

/**
 * Get the full command name including parent commands.
 * For example: "auth login" or "machine list"
 */
function getFullCommandName(command: Command): string {
  const names: string[] = [];
  let current: Command | null = command;

  while (current) {
    const name = current.name();
    if (name && name !== 'rdc') {
      names.unshift(name);
    }
    current = current.parent;
  }

  return names.join(' ') || 'unknown';
}

export const cli = new Command();

cli
  .name('rdc')
  .description(t('cli.description'))
  .version(VERSION)
  .option('-o, --output <format>', t('options.output'), 'table')
  .option('--context <name>', t('options.context'))
  .option('-l, --lang <code>', t('options.lang', { languages: SUPPORTED_LANGUAGES.join('|') }))
  .hook('preAction', async (thisCommand, actionCommand) => {
    const opts = thisCommand.opts();
    // Set output format before any command runs
    setOutputFormat(opts.output as OutputFormat);
    // Set runtime context override if --context flag is provided
    if (opts.context) {
      contextService.setRuntimeContext(opts.context);
    }
    // Initialize or update i18n language
    const language = opts.lang ?? (await contextService.getLanguage());
    if (!i18nInitialized) {
      await initI18n(language);
      i18nInitialized = true;
    } else if (opts.lang) {
      // Only change if explicitly set via flag
      await changeLanguage(language);
    }

    // Start telemetry tracking for the command
    const commandName = getFullCommandName(actionCommand);
    commandContext.set(commandName, { startTime: Date.now() });
    telemetryService.startCommand(commandName, {
      args: actionCommand.args,
      options: actionCommand.opts(),
    });

    // Set user context if available
    try {
      const email = await contextService.getUserEmail();
      const team = await contextService.getTeam();
      if (email || team) {
        telemetryService.setUserContext({ email: email ?? undefined, teamName: team ?? undefined });
      }
    } catch {
      // Ignore errors getting user context
    }
  })
  .hook('postAction', (_thisCommand, actionCommand) => {
    // End telemetry tracking for the command
    const commandName = getFullCommandName(actionCommand);
    const ctx = commandContext.get(commandName);
    const duration = ctx ? Date.now() - ctx.startTime : 0;

    telemetryService.endCommand(commandName, {
      success: true,
      exitCode: 0,
    });

    // Track command duration metric
    telemetryService.trackMetric(`cli.command.${commandName}.duration`, duration, 'ms');

    commandContext.delete(commandName);
  });

// Cloud-only command names — these are not available in s3/local mode
const CLOUD_ONLY_COMMANDS = new Set([
  'auth',
  'bridge',
  'team',
  'region',
  'organization',
  'user',
  'permission',
  'audit',
  'ceph',
  'repository',
]);

// Register all command groups
registerAuthCommands(cli);
registerTeamCommands(cli);
registerMachineCommands(cli);
registerRepositoryCommands(cli);
registerRepoCommands(cli);
registerStorageCommands(cli);
registerQueueCommands(cli);
registerRegionCommands(cli);
registerBridgeCommands(cli);
registerCephCommands(cli);
registerOrganizationCommands(cli);
registerUserCommands(cli);
registerContextCommands(cli);
registerDoctorCommand(cli);
registerPermissionCommands(cli);
registerAuditCommands(cli);
registerTermCommands(cli);
registerSyncCommands(cli);
registerProtocolCommands(cli);
registerVSCodeCommands(cli);
registerUpdateCommand(cli);
registerShortcuts(cli);

// Apply cloud-only guards and help annotations to the appropriate top-level commands
for (const cmd of cli.commands) {
  if (CLOUD_ONLY_COMMANDS.has(cmd.name())) {
    addCloudOnlyGuard(cmd);
    markCloudOnly(cmd);
  }
}

// Provide a clear error for unsupported subcommands
cli.on('command:*', (operands) => {
  const [first, second] = operands;
  const commandList = cli.commands.map((c) => c.name()).filter((n) => n && n !== 'help');
  const parent = first ? cli.commands.find((c) => c.name() === first) : undefined;

  if (parent && second) {
    const subcommands = parent.commands
      .map((c) => c.name())
      .filter((n) => n && n !== 'help')
      .join(', ');
    outputService.error(
      t('errors.unknownSubcommand', {
        command: `${first} ${second}`,
        parent: first,
        available: subcommands || '-',
      })
    );
    parent.outputHelp();
  } else {
    outputService.error(
      t('errors.unknownCommand', {
        command: operands.join(' '),
        available: commandList.join(', '),
      })
    );
    cli.outputHelp();
  }

  process.exit(1);
});
