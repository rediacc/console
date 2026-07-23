import { CLI_CONTRACT_VERSION, getCommand } from '@rediacc/shared/cli-contract';
import { TELEMETRY_SUBSCRIPTION_SOURCES } from '@rediacc/shared/telemetry';
import { Command } from 'commander';
import { registerBackupCommands } from './commands/backup.js';
import { registerClusterCommands } from './commands/cluster/index.js';
import { registerConfigCommands } from './commands/config.js';
import { registerCreditsCommand } from './commands/credits.js';
import { registerDatastoreCommands } from './commands/datastore.js';
import { registerDoctorCommand } from './commands/doctor.js';
import { registerExecutorDaemonCommands } from './commands/executor-daemon.js';
import { registerJobCommands } from './commands/job.js';
import { registerMachineCommands } from './commands/machine/index.js';
import { registerMcpCommands } from './commands/mcp/index.js';
import { registerOpsCommands } from './commands/ops/index.js';
import { registerRepoCommands } from './commands/repo.js';
import { registerServeCommand } from './commands/serve.js';
import { registerShortcuts } from './commands/shortcuts.js';
import { registerStorageCommands } from './commands/storage.js';
import { registerSubscriptionCommands } from './commands/subscription.js';
import { registerTermCommands } from './commands/term.js';
import { registerUpdateCommand } from './commands/update.js';
import { registerVSCodeCommands } from './commands/vscode.js';
import { changeLanguage, initI18n, SUPPORTED_LANGUAGES, t } from './i18n/index.js';
import { getSubscriptionTokenState } from './services/account/subscription-auth.js';
import { configService } from './services/config/config-resources.js';
import { auditService } from './services/core/audit.js';
import { outputService } from './services/core/output.js';
import { exitProcess } from './services/core/request-context.js';
import { setBackgroundRequested } from './services/executor/executor-factory.js';
import {
  assertDetachable,
  assertProxyCapable,
  runCommandThroughProxy,
} from './services/executor/proxy-command.js';
import { fetchOtlpCredentials } from './services/telemetry/otlp-credentials.js';
import { isTelemetryDisabled, telemetryService } from './services/telemetry/telemetry.js';
import type { OutputFormat } from './types/index.js';
import { isAgentEnvironment } from './utils/agent-guard.js';
import { attachExamples } from './utils/attach-examples.js';
import { setOutputFormat } from './utils/errors.js';
import { applyRegistry } from './utils/mode-guard.js';
import { isDevBuild } from './utils/platform.js';
import { VERSION } from './version.js';

// Track if i18n has been initialized
let i18nInitialized = false;

// Track command context for telemetry
const commandContext = new Map<string, { startTime: number }>();

/**
 * The deferred telemetry-setup chain started in preAction (credential fetch →
 * initialize → startCommand → user context). postAction awaits it before
 * closing the command span. Resolved-by-default so a postAction without a
 * matching preAction (or with telemetry disabled) never hangs.
 */
let telemetryReady: Promise<void> = Promise.resolve();

// formatDuration removed — timeline handles all timing display

// Telemetry is initialized in the preAction hook after `fetchOtlpCredentials()`
// resolves so the OTel SDK is constructed with the correct per-region auth
// header from the start. Before that, any telemetry calls are no-ops.

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

    if (isAgentEnvironment() && tokenState.kind !== 'ready' && !isDevBuild()) {
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

// Output-format precedence when --output not explicitly set:
//   1. REDIACC_DEFAULT_OUTPUT env var (whitelist: table|json|yaml|csv)
//   2. Auto-JSON for non-TTY or agent environments
//   3. Default 'table' from .option()
// Used by tutorial recording to keep human-readable output even though
// CLAUDECODE=1 in the parent shell triggers agent detection.
function resolveOutputFormat(optsValue: OutputFormat, source: string | undefined): OutputFormat {
  if (source !== 'default') {
    return optsValue;
  }
  const envOverride = process.env.REDIACC_DEFAULT_OUTPUT;
  if (
    envOverride === 'table' ||
    envOverride === 'json' ||
    envOverride === 'yaml' ||
    envOverride === 'csv'
  ) {
    return envOverride;
  }
  if (process.stdout.isTTY !== true || isAgentEnvironment()) {
    return 'json';
  }
  return optsValue;
}

/**
 * The contract key for a Commander command: its path with the root dropped,
 * space-joined. "rdc repo fork" becomes "repo fork".
 */
function commandPathOf(command: Command): string {
  const segments: string[] = [];
  for (let node: Command | null = command; node; node = node.parent) {
    if (node.parent) segments.unshift(node.name());
  }
  return segments.join(' ');
}

/**
 * Build a Commander tree.
 *
 * A FACTORY, not just a singleton, because the executor dispatches commands
 * in-process and serves many at once. Commander keeps parse state on the Command
 * objects themselves, so two concurrent parses of one shared tree write over each
 * other: one tenant's --tag could land in another tenant's running command.
 * Commander 15 happens to rebind its option store per parse, which hides most of
 * this today, but multi-tenant isolation must not rest on an implementation
 * detail of a dependency. Each dispatch takes a fresh tree
 * (services/serve/command-dispatch.ts); the CLI process keeps the shared `cli`
 * below, because it only ever parses once.
 */
export function createCli(): Command {
  const cli = new Command();

  cli
    .name('rdc')
    .description(t('cli.description'))
    .version(VERSION)
    .showHelpAfterError(true)
    .option('-o, --output <format>', t('options.output'), 'table')
    .option('--config <name>', t('options.config'))
    .option('-l, --lang <code>', t('options.lang', { languages: SUPPORTED_LANGUAGES.join('|') }))
    .option('-q, --quiet', t('options.quiet'))
    .option('-y, --yes', t('options.yes'))
    .option('--fields <fields>', t('options.fields'))
    .option('--proxy <url>', t('options.proxy'))
    .option('-b, --background', t('options.background'))
    .hook('preAction', async (thisCommand, actionCommand) => {
      const opts = thisCommand.opts();
      const effectiveFormat = resolveOutputFormat(
        opts.output as OutputFormat,
        thisCommand.getOptionValueSource('output')
      );
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

      // Initialize or update i18n language. Before the proxy branch: a proxied
      // run still renders here, so it needs its strings.
      await ensureI18n(opts.lang ?? (await configService.getLanguage()), opts.lang);

      // Fire-and-forget: start the machine work as a detached job and return the
      // instant it starts, leaving it running (finding #2 of the detach handoff).
      // Refuse it up front for a command that cannot become a job, so the
      // operator gets a clear message rather than a flag that silently did
      // nothing. Set before the proxy branch, which never returns.
      if (opts.background) {
        const commandPath = commandPathOf(actionCommand);
        assertDetachable(commandPath, getCommand(commandPath));
        setBackgroundRequested(true);
      }

      // Run the command at a remote executor instead of here. Explicit opt-in
      // only: an inferred mode was what made the retired cloud adapter leak
      // conditionals through every layer.
      //
      // Interception is at the COMMAND, not deeper. A command's action body reads
      // and writes local config on its way to the executor seam, and a proxy
      // client holds no config, so intercepting at the seam meant dying with
      // "Repository not found in context" before the wire was ever touched. This
      // hook runs before every action, so exiting here means the local action
      // never runs at all, which is what makes the client genuinely thin.
      const proxyUrl = (opts.proxy as string | undefined) ?? process.env.REDIACC_PROXY_URL;
      if (proxyUrl) {
        // Refuse a command the proxy cannot serve (interactive TTY, client-side
        // file transfer, or an effect that only exists on this laptop) up front,
        // so the operator gets a clear message instead of a confusing failure
        // mid-request.
        const commandPath = commandPathOf(actionCommand);
        const entry = getCommand(commandPath);
        assertProxyCapable(commandPath, entry?.proxyCapable ?? false, entry?.proxyBlockedReason);

        // Never returns: it ends the process with the executor's exit code.
        await runCommandThroughProxy(commandPath, actionCommand, {
          baseUrl: proxyUrl,
          contractVersion: CLI_CONTRACT_VERSION,
          getToken: () => {
            const state = getSubscriptionTokenState();
            if (state.kind !== 'ready') {
              throw new Error(
                'Proxy mode needs an account login. Run "rdc subscription login" first.'
              );
            }
            return Promise.resolve(state.token.token);
          },
        });
      }

      // Telemetry must never gate the user's command. The OTLP credential
      // fetch (unauthenticated, ~100-300ms to the account server) used to be
      // awaited here on EVERY invocation; it now runs CONCURRENTLY with the
      // command. Ordering inside the chain is unchanged (credentials before
      // `initialize()` so the exporter gets its auth header; user context
      // after initialize). Executor paths that inject the credentials into
      // renet env await the same memoized fetch, and the postAction hook
      // awaits this chain before ending the command span, so no telemetry is
      // lost — the span's duration comes from the startTime captured here.
      const commandName = getFullCommandName(actionCommand);
      const startTime = Date.now();
      commandContext.set(commandName, { startTime });
      outputService.setCommandContext(commandName, startTime);
      telemetryReady = (async () => {
        if (!isTelemetryDisabled()) {
          try {
            const otlpCreds = await fetchOtlpCredentials();
            telemetryService.setRuntimeOtlpCredentials(otlpCreds);
          } catch {
            // Any failure (network, malformed response) leaves the token null
            // and telemetry disabled. Never blocks the actual command.
          }
        }
        await telemetryService.initialize({ serviceVersion: VERSION });
        telemetryService.startCommand(commandName, {
          args: actionCommand.args,
          options: actionCommand.opts(),
        });
        telemetryService.startProfiling(commandName);
        // Set user context and subscription state (extracted to reduce complexity)
        await setUserAndSubscriptionContext();
      })().catch(() => {
        // Telemetry setup failures never surface into the command.
      });

      // License auto-refresh is now handled per-operation in services/license.ts
    })
    .hook('postAction', async (_thisCommand, actionCommand) => {
      // Timeline rendering handles timing display for executor commands.
      // No additional "Completed in X (total: Y)" message needed.

      // The deferred telemetry chain from preAction must land before the
      // command span is closed — for fast commands it may still be in flight.
      await telemetryReady;

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

      // Flush audit events (fire-and-forget, timeout-bounded)
      await auditService.flush();
    });

  // Register all command groups
  registerJobCommands(cli);
  registerMachineCommands(cli);
  registerBackupCommands(cli);
  registerRepoCommands(cli);
  registerStorageCommands(cli);
  registerConfigCommands(cli);
  registerDoctorCommand(cli);
  registerCreditsCommand(cli);
  registerClusterCommands(cli);
  registerTermCommands(cli);
  registerVSCodeCommands(cli);
  registerUpdateCommand(cli);
  registerOpsCommands(cli);
  registerDatastoreCommands(cli);
  registerSubscriptionCommands(cli);
  registerMcpCommands(cli);
  registerServeCommand(cli);
  registerExecutorDaemonCommands(cli);
  registerShortcuts(cli);

  // Apply mode guards, help tags, and domain grouping from the command registry
  applyRegistry(cli);

  // Append curated "Examples:" help blocks to every command that has them
  attachExamples(cli);

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
    $ rdc machine status server-1                    ${t('help.cli.machineQuery')}
    $ rdc term connect my-app                        ${t('help.cli.termRepo')}
    $ rdc repo up my-app@server-1                    ${t('help.cli.repoUp')}
    $ rdc repo sync upload my-app --local ./src      ${t('help.cli.syncUpload')}
    $ rdc repo sync download my-app --local ./out    ${t('help.cli.syncDownload')}
  `
  );

  // Provide a clear error for unsupported subcommands
  cli.on('command:*', (operands) => {
    const [first, second] = operands;
    const commandList = cli.commands
      .filter((c) => !(c as Command & { _hidden?: boolean })._hidden)
      .map((c) => c.name())
      .filter((n) => n && n !== 'help');
    const parent = first ? cli.commands.find((c) => c.name() === first) : undefined;

    if (parent && second) {
      const subcommands = parent.commands
        .filter((c) => !(c as Command & { _hidden?: boolean })._hidden)
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

    exitProcess(1);
  });

  return cli;
}

/** The CLI process's program. One process, one parse. */
export const cli = createCli();
