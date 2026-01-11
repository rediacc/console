import {
  parseProtocolUrl,
  buildCliCommand,
  buildProtocolUrl,
  registerProtocol,
  unregisterProtocol,
  getProtocolStatus,
  isProtocolSupported,
  PROTOCOL_SCHEME,
  VALID_ACTIONS,
} from '@rediacc/shared-desktop/protocol';
import { getPlatform } from '@rediacc/shared-desktop/utils';
import { Command } from 'commander';
import { t } from '../i18n/index.js';
import { authService } from '../services/auth.js';
import { handleError } from '../utils/errors.js';
import { withSpinner } from '../utils/spinner.js';
// ProtocolAction type used by VALID_ACTIONS

interface ProtocolRegisterOptions {
  system?: boolean;
  force?: boolean;
}

interface ProtocolOpenOptions {
  team?: string;
}

/**
 * Registers the protocol handler on the system
 */
async function handleRegister(options: ProtocolRegisterOptions): Promise<void> {
  if (!isProtocolSupported()) {
    throw new Error(t('errors.protocol.notSupported', { platform: getPlatform() }));
  }

  const systemWide = options.system ?? false;

  if (systemWide) {
    // eslint-disable-next-line no-console
    console.log(t('commands.protocol.register.systemWide'));
    // eslint-disable-next-line no-console
    console.log(t('commands.protocol.register.adminRequired'));
  } else {
    // eslint-disable-next-line no-console
    console.log(t('commands.protocol.register.currentUser'));
  }

  await withSpinner(t('commands.protocol.register.registering'), () => {
    registerProtocol(options.force, systemWide);
    return Promise.resolve();
  });

  // eslint-disable-next-line no-console
  console.log(t('commands.protocol.register.success', { scheme: PROTOCOL_SCHEME }));
  // eslint-disable-next-line no-console
  console.log(t('commands.protocol.register.exampleUrls'));
  // eslint-disable-next-line no-console
  console.log(`  ${PROTOCOL_SCHEME}://token/team/machine/terminal`);
  // eslint-disable-next-line no-console
  console.log(`  ${PROTOCOL_SCHEME}://token/team/machine/repository/browser`);
}

/**
 * Unregisters the protocol handler from the system
 */
async function handleUnregister(options: { system?: boolean }): Promise<void> {
  if (!isProtocolSupported()) {
    throw new Error(t('errors.protocol.notSupported', { platform: getPlatform() }));
  }

  const systemWide = options.system ?? false;

  await withSpinner(t('commands.protocol.unregister.unregistering'), () => {
    unregisterProtocol(systemWide);
    return Promise.resolve();
  });

  // eslint-disable-next-line no-console
  console.log(t('commands.protocol.unregister.success', { scheme: PROTOCOL_SCHEME }));
}

function formatYesNo(value: boolean): string {
  return value ? t('common.yes') : t('common.no');
}

function displayBasicStatus(status: ReturnType<typeof getProtocolStatus>): void {
  // eslint-disable-next-line no-console
  console.log(`${t('commands.protocol.status.platform')}           ${status.platform}`);
  // eslint-disable-next-line no-console
  console.log(
    `${t('commands.protocol.status.supported')}          ${formatYesNo(status.supported)}`
  );
  // eslint-disable-next-line no-console
  console.log(
    `${t('commands.protocol.status.registered')}         ${formatYesNo(status.registered)}`
  );
}

function displaySupportedStatus(status: ReturnType<typeof getProtocolStatus>): void {
  if (!status.supported) return;

  // eslint-disable-next-line no-console
  console.log(
    `${t('commands.protocol.status.userRegistration')}  ${formatYesNo(status.userRegistered)}`
  );
  // eslint-disable-next-line no-console
  console.log(
    `${t('commands.protocol.status.systemRegistration')} ${formatYesNo(status.systemRegistered)}`
  );

  if (status.command) {
    // eslint-disable-next-line no-console
    console.log(`${t('commands.protocol.status.handlerCommand')}    ${status.command}`);
  }
}

function displayStatusFooter(status: ReturnType<typeof getProtocolStatus>): void {
  if (status.error) {
    // eslint-disable-next-line no-console
    console.log(t('commands.protocol.status.error', { error: status.error }));
  }

  if (!status.registered && status.supported) {
    // eslint-disable-next-line no-console
    console.log(t('commands.protocol.status.registerHint'));
    // eslint-disable-next-line no-console
    console.log('  rdc protocol register');
  }
}

/**
 * Shows protocol handler status
 */
function handleStatus(options: { output?: string }): void {
  const status = getProtocolStatus();

  if (options.output === 'json') {
    // eslint-disable-next-line no-console
    console.log(JSON.stringify(status, null, 2));
    return;
  }

  // eslint-disable-next-line no-console
  console.log(t('commands.protocol.status.title'));
  // eslint-disable-next-line no-console
  console.log('=======================\n');

  displayBasicStatus(status);
  displaySupportedStatus(status);
  displayStatusFooter(status);
}

/**
 * Opens a protocol URL
 */
async function handleOpen(url: string, _options: ProtocolOpenOptions): Promise<void> {
  // Parse the URL
  let parsedUrl;
  try {
    parsedUrl = parseProtocolUrl(url);
  } catch (error) {
    throw new Error(
      t('errors.protocol.invalidUrl', {
        error: error instanceof Error ? error.message : String(error),
      })
    );
  }

  // eslint-disable-next-line no-console
  console.log(t('commands.protocol.open.parsedUrl'));
  // eslint-disable-next-line no-console
  console.log(`  ${t('commands.protocol.open.token')}      ${parsedUrl.token.substring(0, 10)}...`);
  // eslint-disable-next-line no-console
  console.log(`  ${t('commands.protocol.open.team')}       ${parsedUrl.teamName}`);
  // eslint-disable-next-line no-console
  console.log(`  ${t('commands.protocol.open.machine')}    ${parsedUrl.machineName}`);
  if (parsedUrl.repositoryName) {
    // eslint-disable-next-line no-console
    console.log(`  ${t('commands.protocol.open.repository')} ${parsedUrl.repositoryName}`);
  }
  // eslint-disable-next-line no-console
  console.log(`  ${t('commands.protocol.open.action')}     ${parsedUrl.action}`);
  if (parsedUrl.params && Object.keys(parsedUrl.params).length > 0) {
    // eslint-disable-next-line no-console
    console.log(`  ${t('commands.protocol.open.params')}     ${JSON.stringify(parsedUrl.params)}`);
  }

  // Build CLI command
  const cliCommand = buildCliCommand(parsedUrl);
  // eslint-disable-next-line no-console
  console.log(t('commands.protocol.open.cliCommand'));
  // eslint-disable-next-line no-console
  console.log(`  rdc ${cliCommand.join(' ')}`);

  // Execute the action
  // eslint-disable-next-line no-console
  console.log(t('commands.protocol.open.executing'));

  // Import and execute the appropriate command
  const { spawn } = await import('node:child_process');

  // Build the full command
  const rdcPath = process.argv[1];
  const args = cliCommand;

  const child = spawn(process.execPath, [rdcPath, ...args], {
    stdio: 'inherit',
    env: {
      ...process.env,
      REDIACC_PROTOCOL_TOKEN: parsedUrl.token,
    },
  });

  await new Promise<void>((resolve, reject) => {
    child.on('exit', (code) => {
      if (code === 0 || code === null) {
        resolve();
      } else {
        reject(new Error(t('errors.protocol.commandExitCode', { code })));
      }
    });
    child.on('error', reject);
  });
}

interface BuildOptions {
  token?: string;
  team?: string;
  machine?: string;
  repository?: string;
  action?: string;
  params?: string[];
}

function validateBuildOptions(
  options: BuildOptions
): asserts options is BuildOptions & { token: string; team: string; machine: string } {
  if (!options.token) {
    throw new Error(t('errors.protocol.tokenRequired'));
  }
  if (!options.team) {
    throw new Error(t('errors.protocol.teamRequired'));
  }
  if (!options.machine) {
    throw new Error(t('errors.protocol.machineRequired'));
  }
}

function parseParamsArray(paramsArray: string[] | undefined): Record<string, string> {
  if (!paramsArray) return {};

  const params: Record<string, string> = {};
  for (const param of paramsArray) {
    const [key, value] = param.split('=');
    if (key && value) {
      params[key] = value;
    }
  }
  return params;
}

function validateAndGetAction(action: string | undefined): (typeof VALID_ACTIONS)[number] {
  const effectiveAction = action ?? 'desktop';
  if (!VALID_ACTIONS.includes(effectiveAction as (typeof VALID_ACTIONS)[number])) {
    throw new Error(
      t('errors.protocol.invalidAction', {
        action: effectiveAction,
        validActions: VALID_ACTIONS.join(', '),
      })
    );
  }
  return effectiveAction as (typeof VALID_ACTIONS)[number];
}

/**
 * Builds a protocol URL from components
 */
function handleBuild(options: BuildOptions): void {
  validateBuildOptions(options);

  const params = parseParamsArray(options.params);
  const action = validateAndGetAction(options.action);

  const url = buildProtocolUrl({
    token: options.token,
    teamName: options.team,
    machineName: options.machine,
    repositoryName: options.repository,
    action,
    params: Object.keys(params).length > 0 ? params : undefined,
  });

  // eslint-disable-next-line no-console
  console.log(url);
}

/**
 * Parses and displays a protocol URL
 */
function handleParse(url: string): void {
  try {
    const parsed = parseProtocolUrl(url);

    // eslint-disable-next-line no-console
    console.log(t('commands.protocol.parse.parsedUrl'));
    // eslint-disable-next-line no-console
    console.log(JSON.stringify(parsed, null, 2));

    // eslint-disable-next-line no-console
    console.log(t('commands.protocol.parse.cliCommand'));
    const cmd = buildCliCommand(parsed);
    // eslint-disable-next-line no-console
    console.log(`rdc ${cmd.join(' ')}`);
  } catch (error) {
    throw new Error(
      t('errors.protocol.parseFailed', {
        error: error instanceof Error ? error.message : String(error),
      })
    );
  }
}

/**
 * Registers the protocol commands
 */
export function registerProtocolCommands(program: Command): void {
  const protocol = program
    .command('protocol')
    .description(t('commands.protocol.description', { scheme: PROTOCOL_SCHEME }));

  protocol
    .command('register')
    .description(t('commands.protocol.register.description'))
    .option('--system', t('options.protocolSystem'))
    .option('--force', t('options.protocolForce'))
    .action(async (options: ProtocolRegisterOptions) => {
      try {
        await handleRegister(options);
      } catch (error) {
        handleError(error);
      }
    });

  protocol
    .command('unregister')
    .description(t('commands.protocol.unregister.description'))
    .option('--system', t('options.protocolSystemUnregister'))
    .action(async (options: { system?: boolean }) => {
      try {
        await handleUnregister(options);
      } catch (error) {
        handleError(error);
      }
    });

  protocol
    .command('status')
    .description(t('commands.protocol.status.description'))
    .option('-o, --output <format>', t('options.outputFormat'))
    .action((options: { output?: string }) => {
      try {
        handleStatus(options);
      } catch (error) {
        handleError(error);
      }
    });

  protocol
    .command('open <url>')
    .description(t('commands.protocol.open.description', { scheme: PROTOCOL_SCHEME }))
    .action(async (url: string, options: ProtocolOpenOptions) => {
      try {
        await authService.requireAuth();
        await handleOpen(url, options);
      } catch (error) {
        handleError(error);
      }
    });

  protocol
    .command('build')
    .description(t('commands.protocol.build.description', { scheme: PROTOCOL_SCHEME }))
    .requiredOption('--token <token>', t('options.protocolToken'))
    .requiredOption('-t, --team <name>', t('options.team'))
    .requiredOption('-m, --machine <name>', t('options.machine'))
    .option('-r, --repository <name>', t('options.repository'))
    .option(
      '-a, --action <action>',
      t('options.protocolAction', { actions: VALID_ACTIONS.join(', ') }),
      'desktop'
    )
    .option('-p, --params <key=value...>', t('options.protocolParams'))
    .action((options) => {
      try {
        handleBuild(options);
      } catch (error) {
        handleError(error);
      }
    });

  protocol
    .command('parse <url>')
    .description(t('commands.protocol.parse.description', { scheme: PROTOCOL_SCHEME }))
    .action((url: string) => {
      try {
        handleParse(url);
      } catch (error) {
        handleError(error);
      }
    });
}
