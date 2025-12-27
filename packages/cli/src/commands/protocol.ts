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
    throw new Error(`Protocol registration is not supported on ${getPlatform()}`);
  }

  const systemWide = options.system ?? false;

  if (systemWide) {
    // eslint-disable-next-line no-console
    console.log('Registering protocol handler system-wide...');
    // eslint-disable-next-line no-console
    console.log('Note: This may require administrator/root privileges.');
  } else {
    // eslint-disable-next-line no-console
    console.log('Registering protocol handler for current user...');
  }

  await withSpinner('Registering protocol handler...', async () => {
    registerProtocol(options.force, systemWide);
  });

  // eslint-disable-next-line no-console
  console.log(`\nSuccessfully registered ${PROTOCOL_SCHEME}:// protocol handler.`);
  // eslint-disable-next-line no-console
  console.log('\nYou can now open URLs like:');
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
    throw new Error(`Protocol registration is not supported on ${getPlatform()}`);
  }

  const systemWide = options.system ?? false;

  await withSpinner('Unregistering protocol handler...', async () => {
    unregisterProtocol(systemWide);
  });

  // eslint-disable-next-line no-console
  console.log(`\nSuccessfully unregistered ${PROTOCOL_SCHEME}:// protocol handler.`);
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
  console.log('\nProtocol Handler Status');
  // eslint-disable-next-line no-console
  console.log('=======================\n');

  // eslint-disable-next-line no-console
  console.log(`Platform:           ${status.platform}`);
  // eslint-disable-next-line no-console
  console.log(`Supported:          ${status.supported ? 'Yes' : 'No'}`);
  // eslint-disable-next-line no-console
  console.log(`Registered:         ${status.registered ? 'Yes' : 'No'}`);

  if (status.supported) {
    // eslint-disable-next-line no-console
    console.log(`User Registration:  ${status.userRegistered ? 'Yes' : 'No'}`);
    // eslint-disable-next-line no-console
    console.log(`System Registration: ${status.systemRegistered ? 'Yes' : 'No'}`);

    if (status.command) {
      // eslint-disable-next-line no-console
      console.log(`Handler Command:    ${status.command}`);
    }
  }

  if (status.error) {
    // eslint-disable-next-line no-console
    console.log(`\nError: ${status.error}`);
  }

  if (!status.registered && status.supported) {
    // eslint-disable-next-line no-console
    console.log('\nTo register the protocol handler, run:');
    // eslint-disable-next-line no-console
    console.log('  rdc protocol register');
  }
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
    throw new Error(`Invalid protocol URL: ${error instanceof Error ? error.message : error}`);
  }

  // eslint-disable-next-line no-console
  console.log('\nParsed Protocol URL:');
  // eslint-disable-next-line no-console
  console.log(`  Token:      ${parsedUrl.token.substring(0, 10)}...`);
  // eslint-disable-next-line no-console
  console.log(`  Team:       ${parsedUrl.teamName}`);
  // eslint-disable-next-line no-console
  console.log(`  Machine:    ${parsedUrl.machineName}`);
  if (parsedUrl.repositoryName) {
    // eslint-disable-next-line no-console
    console.log(`  Repository: ${parsedUrl.repositoryName}`);
  }
  // eslint-disable-next-line no-console
  console.log(`  Action:     ${parsedUrl.action}`);
  if (parsedUrl.params && Object.keys(parsedUrl.params).length > 0) {
    // eslint-disable-next-line no-console
    console.log(`  Params:     ${JSON.stringify(parsedUrl.params)}`);
  }

  // Build CLI command
  const cliCommand = buildCliCommand(parsedUrl);
  // eslint-disable-next-line no-console
  console.log(`\nEquivalent CLI command:`);
  // eslint-disable-next-line no-console
  console.log(`  rdc ${cliCommand.join(' ')}`);

  // Execute the action
  // eslint-disable-next-line no-console
  console.log('\nExecuting action...\n');

  // Import and execute the appropriate command
  const { spawn } = await import('child_process');

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
        reject(new Error(`Command exited with code ${code}`));
      }
    });
    child.on('error', reject);
  });
}

/**
 * Builds a protocol URL from components
 */
function handleBuild(options: {
  token?: string;
  team?: string;
  machine?: string;
  repository?: string;
  action?: string;
  params?: string[];
}): void {
  if (!options.token) {
    throw new Error('Token is required. Use --token <token>');
  }
  if (!options.team) {
    throw new Error('Team name is required. Use --team <name>');
  }
  if (!options.machine) {
    throw new Error('Machine name is required. Use --machine <name>');
  }

  // Parse params
  const params: Record<string, string> = {};
  if (options.params) {
    for (const param of options.params) {
      const [key, value] = param.split('=');
      if (key && value) {
        params[key] = value;
      }
    }
  }

  // Validate action
  const action = options.action ?? 'desktop';
  if (!VALID_ACTIONS.includes(action as (typeof VALID_ACTIONS)[number])) {
    throw new Error(`Invalid action '${action}'. Must be one of: ${VALID_ACTIONS.join(', ')}`);
  }

  const url = buildProtocolUrl({
    token: options.token,
    teamName: options.team,
    machineName: options.machine,
    repositoryName: options.repository,
    action: action as (typeof VALID_ACTIONS)[number],
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
    console.log('\nParsed Protocol URL:');
    // eslint-disable-next-line no-console
    console.log(JSON.stringify(parsed, null, 2));

    // eslint-disable-next-line no-console
    console.log('\nCLI Command:');
    const cmd = buildCliCommand(parsed);
    // eslint-disable-next-line no-console
    console.log(`rdc ${cmd.join(' ')}`);
  } catch (error) {
    throw new Error(`Failed to parse URL: ${error instanceof Error ? error.message : error}`);
  }
}

/**
 * Registers the protocol commands
 */
export function registerProtocolCommands(program: Command): void {
  const protocol = program
    .command('protocol')
    .description(`Manage ${PROTOCOL_SCHEME}:// protocol handler registration and URL handling`);

  protocol
    .command('register')
    .description('Register the protocol handler on the system')
    .option('--system', 'Register system-wide (requires admin privileges)')
    .option('--force', 'Force re-registration even if already registered')
    .action(async (options: ProtocolRegisterOptions) => {
      try {
        await handleRegister(options);
      } catch (error) {
        handleError(error);
      }
    });

  protocol
    .command('unregister')
    .description('Unregister the protocol handler from the system')
    .option('--system', 'Unregister system-wide registration (requires admin privileges)')
    .action(async (options: { system?: boolean }) => {
      try {
        await handleUnregister(options);
      } catch (error) {
        handleError(error);
      }
    });

  protocol
    .command('status')
    .description('Show protocol handler registration status')
    .option('-o, --output <format>', 'Output format (json)')
    .action((options: { output?: string }) => {
      try {
        handleStatus(options);
      } catch (error) {
        handleError(error);
      }
    });

  protocol
    .command('open <url>')
    .description(`Open a ${PROTOCOL_SCHEME}:// URL and execute the action`)
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
    .description(`Build a ${PROTOCOL_SCHEME}:// URL from components`)
    .requiredOption('--token <token>', 'Authentication token')
    .requiredOption('-t, --team <name>', 'Team name')
    .requiredOption('-m, --machine <name>', 'Machine name')
    .option('-r, --repository <name>', 'Repository name')
    .option('-a, --action <action>', `Action (${VALID_ACTIONS.join(', ')})`, 'desktop')
    .option('-p, --params <key=value...>', 'Additional parameters')
    .action((options) => {
      try {
        handleBuild(options);
      } catch (error) {
        handleError(error);
      }
    });

  protocol
    .command('parse <url>')
    .description(`Parse a ${PROTOCOL_SCHEME}:// URL and show components`)
    .action((url: string) => {
      try {
        handleParse(url);
      } catch (error) {
        handleError(error);
      }
    });
}
