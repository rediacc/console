/**
 * VS Code Remote SSH CLI Command
 * Opens VS Code with Remote SSH connection to machines and repositories
 */

import { SSHConnection, testSSHConnectivity } from '@rediacc/shared-desktop/ssh';
import {
  addSSHConfigEntry,
  buildVSCodeSSHConfigEntry,
  checkVSCodeConfiguration,
  cleanupAllPersistedKeys,
  configureVSCodeSettings,
  ensureVSCodeEnvSetup,
  findVSCode,
  generateConnectionName,
  generateRemoteUri,
  getSSHConfigPath,
  isRemoteSSHExtensionInstalled,
  launchVSCode,
  listPersistedKeys,
  listSSHConfigEntries,
  persistKnownHosts,
  persistSSHKey,
  removeHostFromRemotePlatform,
  removePersistedKeys,
  removeSSHConfigEntry,
  setHostServerInstallPath,
} from '@rediacc/shared-desktop/vscode';
import { Command } from 'commander';
import {
  type ConnectionDetails,
  debugLog,
  displayActiveConnections,
  displayConfigurationStatus,
  displayVSCodeInstallation,
  getSSHConnectionDetails,
} from './vscode-utils.js';
import { t } from '../i18n/index.js';
import { authService } from '../services/auth.js';
import { contextService } from '../services/context.js';
import { handleError } from '../utils/errors.js';
import { withSpinner } from '../utils/spinner.js';

interface VSCodeConnectOptions {
  team?: string;
  machine?: string;
  repository?: string;
  folder?: string;
  urlOnly?: boolean;
  newWindow?: boolean;
  skipEnvSetup?: boolean;
  insiders?: boolean;
}

interface VSCodeCleanupOptions {
  all?: boolean;
  connection?: string;
}

async function detectVSCode() {
  return withSpinner(t('commands.vscode.connect.detecting'), async () => {
    const info = await findVSCode();
    if (!info) {
      throw new Error(t('errors.vscode.notFound'));
    }
    return info;
  });
}

async function verifySSHConnectivity(connectionDetails: ConnectionDetails): Promise<void> {
  const connectivityResult = await withSpinner(
    t('commands.vscode.connect.testingConnectivity', {
      host: connectionDetails.host,
      port: connectionDetails.port,
    }),
    () => testSSHConnectivity(connectionDetails.host, connectionDetails.port, 10000)
  );

  if (!connectivityResult.success) {
    throw new Error(
      t('errors.vscode.connectivityFailed', {
        host: connectionDetails.host,
        port: connectionDetails.port,
        error: connectivityResult.error,
      })
    );
  }
}

async function setupSSHConfig(
  teamName: string,
  machineName: string,
  repositoryName: string | undefined,
  connectionDetails: ConnectionDetails
): Promise<{ connectionName: string; identityFile: string; knownHostsFile: string }> {
  const identityFile = await withSpinner(t('commands.vscode.connect.persistingKey'), () => {
    return Promise.resolve(
      persistSSHKey(teamName, machineName, repositoryName, connectionDetails.privateKey)
    );
  });

  const knownHostsFile = persistKnownHosts(teamName, machineName, connectionDetails.known_hosts);
  const connectionName = generateConnectionName(teamName, machineName, repositoryName);

  await withSpinner(t('commands.vscode.connect.configuringSSH'), () => {
    const sshConfigEntry = buildVSCodeSSHConfigEntry({
      teamName,
      machineName,
      repositoryName,
      host: connectionDetails.host,
      port: connectionDetails.port,
      sshUser: connectionDetails.user,
      identityFile,
      knownHostsFile,
      datastore: connectionDetails.datastore,
      repositoryPath: connectionDetails.repositoryPath,
      universalUser: connectionDetails.universalUser,
      networkId: connectionDetails.networkId,
      additionalEnv: connectionDetails.environment,
    });

    addSSHConfigEntry(sshConfigEntry);
    return Promise.resolve();
  });

  return { connectionName, identityFile, knownHostsFile };
}

interface VSCodeInfo {
  path: string;
  isInsiders?: boolean;
}

async function configureVSCodeAndSettings(
  connectionName: string,
  connectionDetails: ConnectionDetails,
  vscodeInfo: VSCodeInfo,
  insidersOption?: boolean
): Promise<void> {
  await withSpinner(t('commands.vscode.connect.configuringVSCode'), () => {
    const isInsiders = insidersOption ?? vscodeInfo.isInsiders;
    const result = configureVSCodeSettings(isInsiders);

    if (!result.success) {
      console.warn(t('commands.vscode.connect.settingsWarning', { error: result.error }));
    }

    if (connectionDetails.datastore) {
      setHostServerInstallPath(
        connectionName,
        `${connectionDetails.datastore}/.vscode-server`,
        isInsiders
      );
    }

    removeHostFromRemotePlatform(connectionName, isInsiders);
    return Promise.resolve();
  });
}

async function setupRemoteEnvironment(connectionDetails: ConnectionDetails): Promise<void> {
  const sshConnection = new SSHConnection(
    connectionDetails.privateKey,
    connectionDetails.known_hosts,
    { port: connectionDetails.port }
  );

  try {
    await sshConnection.setup();

    await withSpinner(t('commands.vscode.connect.settingUpEnv'), async () => {
      const setupResult = await ensureVSCodeEnvSetup({
        sshDestination: `${connectionDetails.user}@${connectionDetails.host}`,
        sshOptions: sshConnection.sshOptions,
        envVars: connectionDetails.environment ?? {},
        universalUser: connectionDetails.universalUser,
        sshUser: connectionDetails.user,
        serverInstallPath: connectionDetails.datastore,
        agentSocketPath: sshConnection.agentSocketPath,
      });

      if (!setupResult.success) {
        debugLog(`Remote env setup warning: ${setupResult.error}`);
      }
    });
  } catch (error) {
    debugLog(`Remote env setup error: ${error instanceof Error ? error.message : String(error)}`);
  } finally {
    await sshConnection.cleanup();
  }
}

/**
 * Connects to a machine or repository via VS Code Remote SSH
 */
async function connectVSCode(options: VSCodeConnectOptions): Promise<void> {
  const opts = await contextService.applyDefaults(options);

  if (!opts.team) {
    throw new Error(t('errors.teamRequired'));
  }
  if (!opts.machine) {
    throw new Error(t('errors.machineRequired'));
  }

  const teamName = opts.team;
  const machineName = opts.machine;
  const repositoryName = opts.repository;

  const vscodeInfo = await detectVSCode();
  debugLog(`Found VS Code: ${vscodeInfo.path}${vscodeInfo.isInsiders ? ' (Insiders)' : ''}`);

  const hasRemoteSSH = await isRemoteSSHExtensionInstalled();
  if (!hasRemoteSSH) {
    console.warn(t('commands.vscode.connect.extensionWarning'));
  }

  const connectionDetails = await withSpinner(t('commands.vscode.connect.fetchingDetails'), () =>
    getSSHConnectionDetails(teamName, machineName, repositoryName)
  );

  await verifySSHConnectivity(connectionDetails);

  const { connectionName, identityFile, knownHostsFile } = await setupSSHConfig(
    teamName,
    machineName,
    repositoryName,
    connectionDetails
  );

  debugLog(`Identity file: ${identityFile}`);
  debugLog(`Known hosts file: ${knownHostsFile}`);

  await configureVSCodeAndSettings(connectionName, connectionDetails, vscodeInfo, options.insiders);

  if (!options.skipEnvSetup && connectionDetails.environment) {
    await setupRemoteEnvironment(connectionDetails);
  }

  const remotePath =
    options.folder ?? connectionDetails.workingDirectory ?? connectionDetails.datastore;
  const vscodeUri = generateRemoteUri(connectionName, remotePath);

  if (options.urlOnly) {
    // eslint-disable-next-line no-console
    console.log(vscodeUri);
    return;
  }

  // eslint-disable-next-line no-console
  console.log(
    t('commands.vscode.connect.opening', { connection: connectionName, path: remotePath })
  );

  await launchVSCode(vscodeInfo, vscodeUri, { newWindow: options.newWindow });

  // eslint-disable-next-line no-console
  console.log(t('commands.vscode.connect.success'));
}

/**
 * Lists configured VS Code SSH connections
 */
function listVSCodeConnections(): void {
  const entries = listSSHConfigEntries();
  const keys = listPersistedKeys();

  if (entries.length === 0) {
    // eslint-disable-next-line no-console
    console.log(t('commands.vscode.list.noConnections'));
    // eslint-disable-next-line no-console
    console.log(t('commands.vscode.list.configFile', { path: getSSHConfigPath() }));
    return;
  }

  // eslint-disable-next-line no-console
  console.log(t('commands.vscode.list.header'));

  for (const entry of entries) {
    // Check if key exists for this entry
    const hasKey = keys.some((k: string) => entry.includes(k.replaceAll('_', '-')));
    const keyIndicator = hasKey ? t('commands.vscode.list.keyPersisted') : '';
    // eslint-disable-next-line no-console
    console.log(`  ${entry}${keyIndicator}`);
  }

  // eslint-disable-next-line no-console
  console.log(t('commands.vscode.list.total', { count: entries.length }));
  // eslint-disable-next-line no-console
  console.log(t('commands.vscode.list.configFile', { path: getSSHConfigPath() }));
}

/**
 * Cleans up VS Code SSH configurations
 */
function cleanupVSCodeConnections(options: VSCodeCleanupOptions): void {
  if (options.all) {
    const entries = listSSHConfigEntries();
    const count = entries.length;

    for (const entry of entries) {
      removeSSHConfigEntry(entry);
    }
    cleanupAllPersistedKeys();

    // eslint-disable-next-line no-console
    console.log(t('commands.vscode.cleanup.cleanedAll', { count }));
    // eslint-disable-next-line no-console
    console.log(t('commands.vscode.cleanup.removedKeys'));
  } else if (options.connection) {
    const connectionName = options.connection;

    // Remove SSH config entry
    removeSSHConfigEntry(connectionName);

    // Parse connection name to extract team/machine/repository
    // Format: rediacc-team-machine or rediacc-team-machine-repository
    const parts = connectionName.replace(/^rediacc-/, '').split('-');
    if (parts.length >= 2) {
      const [team, machine, ...repositoryParts] = parts;
      const repository = repositoryParts.length > 0 ? repositoryParts.join('-') : undefined;
      removePersistedKeys(team, machine, repository);
    }

    // eslint-disable-next-line no-console
    console.log(t('commands.vscode.cleanup.cleaned', { connection: connectionName }));
  } else {
    throw new Error(t('errors.vscode.cleanupRequired'));
  }
}

/**
 * Checks VS Code installation and configuration
 */
async function checkVSCodeSetup(isInsiders = false): Promise<void> {
  // eslint-disable-next-line no-console
  console.log(t('commands.vscode.check.title'));

  const vscode = await findVSCode();
  displayVSCodeInstallation(vscode);

  const hasExtension = await isRemoteSSHExtensionInstalled();
  const extensionStatus = hasExtension
    ? t('commands.vscode.check.installed')
    : t('commands.vscode.check.notDetected');
  // eslint-disable-next-line no-console
  console.log(t('commands.vscode.check.remoteSSH', { status: extensionStatus }));

  // eslint-disable-next-line no-console
  console.log(t('commands.vscode.check.configuration'));
  const configCheck = checkVSCodeConfiguration(isInsiders);
  displayConfigurationStatus(configCheck);

  const configPath = getSSHConfigPath();
  // eslint-disable-next-line no-console
  console.log(t('commands.vscode.check.sshConfig', { path: configPath }));

  const connections = listSSHConfigEntries();
  displayActiveConnections(connections);
}

/**
 * Registers the VS Code commands
 */
export function registerVSCodeCommands(program: Command): void {
  const vscode = program.command('vscode').description(t('commands.vscode.description'));

  // Connect subcommand
  vscode
    .command('connect')
    .description(t('commands.vscode.connect.description'))
    .option('-t, --team <name>', t('options.team'))
    .option('-m, --machine <name>', t('options.machine'))
    .option('-r, --repository <name>', t('options.repository'))
    .option('-f, --folder <path>', t('options.folder'))
    .option('--url-only', t('options.urlOnly'))
    .option('-n, --new-window', t('options.newWindow'))
    .option('--skip-env-setup', t('options.skipEnvSetup'))
    .option('--insiders', t('options.insiders'))
    .action(async (options: VSCodeConnectOptions) => {
      try {
        await authService.requireAuth();
        await connectVSCode(options);
      } catch (error) {
        handleError(error);
      }
    });

  // List subcommand
  vscode
    .command('list')
    .description(t('commands.vscode.list.description'))
    .action(() => {
      try {
        listVSCodeConnections();
      } catch (error) {
        handleError(error);
      }
    });

  // Cleanup subcommand
  vscode
    .command('cleanup')
    .description(t('commands.vscode.cleanup.description'))
    .option('--all', t('options.cleanupAll'))
    .option('-c, --connection <name>', t('options.connectionName'))
    .action((options: VSCodeCleanupOptions) => {
      try {
        cleanupVSCodeConnections(options);
      } catch (error) {
        handleError(error);
      }
    });

  // Check subcommand
  vscode
    .command('check')
    .description(t('commands.vscode.check.description'))
    .option('--insiders', t('options.insiders'))
    .action(async (options: { insiders?: boolean }) => {
      try {
        await checkVSCodeSetup(options.insiders);
      } catch (error) {
        handleError(error);
      }
    });

  // Shorthand: rdc vscode <machine> [repository]
  vscode
    .argument('[machine]', t('options.machineShorthand'))
    .argument('[repository]', t('options.repositoryShorthand'))
    .option('-t, --team <name>', t('options.team'))
    .option('-f, --folder <path>', t('options.folder'))
    .option('--url-only', t('options.urlOnly'))
    .option('-n, --new-window', t('options.newWindow'))
    .option('--skip-env-setup', t('options.skipEnvSetup'))
    .option('--insiders', t('options.insiders'))
    .action(
      async (
        machine: string | undefined,
        repository: string | undefined,
        options: VSCodeConnectOptions
      ) => {
        try {
          // If positional arguments provided, use connect flow
          if (machine) {
            await authService.requireAuth();
            await connectVSCode({
              ...options,
              machine,
              repository,
            });
          }
          // If no arguments, show help (handled by commander)
        } catch (error) {
          handleError(error);
        }
      }
    );
}
