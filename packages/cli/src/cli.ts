import { TELEMETRY_SUBSCRIPTION_SOURCES } from '@rediacc/shared/telemetry';
import { Command } from 'commander';
import { registerAgentCommands } from './commands/agent.js';
import { registerAuditCommands } from './commands/audit.js';
import { registerAuthCommands } from './commands/auth.js';
import { registerBridgeCommands } from './commands/bridge.js';
import { registerCephCommands } from './commands/ceph/index.js';
import { registerConfigCommands } from './commands/config.js';
import { registerDatastoreCommands } from './commands/datastore.js';
import { registerDoctorCommand } from './commands/doctor.js';
import { registerMachineCommands } from './commands/machine/index.js';
import { registerMcpCommands } from './commands/mcp/index.js';
import { registerOpsCommands } from './commands/ops/index.js';
import { registerOrganizationCommands } from './commands/organization.js';
import { registerPermissionCommands } from './commands/permission.js';
import { registerProtocolCommands } from './commands/protocol.js';
import { registerQueueCommands } from './commands/queue.js';
import { registerRegionCommands } from './commands/region.js';
import { registerRepoCommands } from './commands/repo.js';
import { registerRepositoryCommands } from './commands/repository.js';
import { registerShortcuts } from './commands/shortcuts.js';
import { registerStorageCommands } from './commands/storage.js';
import { registerStoreCommands } from './commands/store.js';
import { registerSubscriptionCommands } from './commands/subscription.js';
import { registerTeamCommands } from './commands/team.js';
import { registerTermCommands } from './commands/term.js';
import { registerUpdateCommand } from './commands/update.js';
import { registerUserCommands } from './commands/user.js';
import { registerVSCodeCommands } from './commands/vscode.js';
import { changeLanguage, initI18n, SUPPORTED_LANGUAGES, t } from './i18n/index.js';
import { configService } from './services/config-resources.js';
import { outputService } from './services/output.js';
import { getSubscriptionTokenState } from './services/subscription-auth.js';
import { telemetryService } from './services/telemetry.js';
import type { OutputFormat } from './types/index.js';
import { isAgentEnvironment } from './utils/agent-guard.js';
import { setOutputFormat } from './utils/errors.js';
import { applyRegistry } from './utils/mode-guard.js';
import { VERSION } from './version.js';

// Track if i18n has been initialized
let i18nInitialized = false;

// Track command context for telemetry
const commandContext = new Map<string, { startTime: number }>();

// formatDuration removed — timeline handles all timing display

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

async function ensureI18n(language: string, explicitLang?: string): Promise<void> {
  if (!i18nInitialized) {
    await initI18n(language);
    i18nInitialized = true;
  } else if (explicitLang) {
    await changeLanguage(language);
  }
}

async function setUserAndSubscriptionContext(): Promise<void> {
  try {
    const email = await configService.getUserEmail();
    const team = await configService.getTeam();
    const tokenState = getSubscriptionTokenState();

    if (isAgentEnvironment() && tokenState.kind !== 'ready') {
      outputService.warn(t('errors.subscription.tokenWarning'));
    }
    const subscriptionContext =
      tokenState.kind === 'ready' && tokenState.token.subscriptionId
        ? {
            subscriptionId: tokenState.token.subscriptionId,
            subscriptionSource: TELEMETRY_SUBSCRIPTION_SOURCES.storedToken,
          }
        : {};

    if (email || team || Object.keys(subscriptionContext).length > 0) {
      telemetryService.setUserContext({
        email: email ?? undefined,
        teamName: team ?? undefined,
        ...subscriptionContext,
      });
    }
  } catch {
    // Ignore errors getting user context
  }
}

export const cli = new Command();

cli
  .name('rdc')
  .description(t('cli.description'))
  .version(VERSION)
  .showHelpAfterError(true)
  .option('-o, --output <format>', t('options.output'), 'table')
  .option('--config <name>', t('options.config'))
  .option('-l, --lang <code>', t('options.lang', { languages: SUPPORTED_LANGUAGES.join('|') }))
  .option('-q, --quiet', t('options.quiet'))
  .option('--fields <fields>', t('options.fields'))
  .hook('preAction', async (thisCommand, actionCommand) => {
    const opts = thisCommand.opts();
    // Auto-detect: default to JSON when stdout is piped or running in an AI agent
    const outputSource = thisCommand.getOptionValueSource('output');
    let effectiveFormat = opts.output as OutputFormat;
    if (outputSource === 'default' && (process.stdout.isTTY !== true || isAgentEnvironment())) {
      effectiveFormat = 'json';
    }
    setOutputFormat(effectiveFormat);
    thisCommand.setOptionValue('output', effectiveFormat);
    // Set --yes flag globally for prompt bypass
    if (opts.yes) {
      process.env.REDIACC_YES = '1';
    }
    // Set --quiet mode to suppress informational output
    if (opts.quiet) {
      outputService.setQuiet(true);
    }
    // Set --fields for output filtering
    if (opts.fields) {
      outputService.setFields(opts.fields);
    }
    // Set runtime config override if --config flag is provided
    if (opts.config) {
      configService.setRuntimeConfig(opts.config);
    }
    // Initialize or update i18n language
    await ensureI18n(opts.lang ?? (await configService.getLanguage()), opts.lang);

    // Start telemetry tracking for the command
    const commandName = getFullCommandName(actionCommand);
    const startTime = Date.now();
    commandContext.set(commandName, { startTime });
    outputService.setCommandContext(commandName, startTime);
    telemetryService.startCommand(commandName, {
      args: actionCommand.args,
      options: actionCommand.opts(),
    });
    telemetryService.startProfiling(commandName);

    // Set user context and subscription state (extracted to reduce complexity)
    await setUserAndSubscriptionContext();

    // License auto-refresh is now handled per-operation in services/license.ts
  })
  .hook('postAction', async (_thisCommand, actionCommand) => {
    // Timeline rendering handles timing display for executor commands.
    // No additional "Completed in X (total: Y)" message needed.

    // Stop profiling before ending telemetry
    await telemetryService.stopProfiling();

    // End telemetry tracking for the command
    const commandName = getFullCommandName(actionCommand);
    const ctx = commandContext.get(commandName);
    const duration = ctx ? Date.now() - ctx.startTime : 0;

    telemetryService.endCommand(commandName, {
      success: true,
      exitCode: 0,
      duration,
    });

    commandContext.delete(commandName);
  });

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
registerConfigCommands(cli);
registerStoreCommands(cli);
registerDoctorCommand(cli);
registerPermissionCommands(cli);
registerAuditCommands(cli);
registerTermCommands(cli);
registerProtocolCommands(cli);
registerVSCodeCommands(cli);
registerUpdateCommand(cli);
registerOpsCommands(cli);
registerDatastoreCommands(cli);
registerSubscriptionCommands(cli);
registerAgentCommands(cli);
registerMcpCommands(cli);
registerShortcuts(cli);

// Apply mode guards, help tags, and domain grouping from the command registry
applyRegistry(cli);

// Add Key Concepts and Agent Mode sections for extended help (agents + --help-all)
const showExtendedHelp = isAgentEnvironment() || process.argv.includes('--help-all');
if (showExtendedHelp) {
  cli.addHelpText('after', t('help.keyConcepts'));
  if (isAgentEnvironment()) {
    cli.addHelpText('after', t('help.agentMode'));
  }
}

// Add usage examples to top-level help
cli.addHelpText(
  'after',
  `
${t('help.examples')}
  $ rdc machine query server-1             ${t('help.cli.machineQuery')}
  $ rdc term server-1 my-app               ${t('help.cli.termRepo')}
  $ rdc repo up my-app -m server-1         ${t('help.cli.repoUp')}
  $ rdc repo sync upload -m server-1 -r my-app  ${t('help.cli.syncUpload')}
`
);

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
