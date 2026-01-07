/**
 * VS Code Remote SSH CLI Command
 * Opens VS Code with Remote SSH connection to machines and repositories
 */

import { SSHConnection, testSSHConnectivity } from '@rediacc/shared-desktop/ssh';
import {
  findVSCode,
  launchVSCode,
  generateRemoteUri,
  isRemoteSSHExtensionInstalled,
  generateConnectionName,
  buildVSCodeSSHConfigEntry,
  addSSHConfigEntry,
  removeSSHConfigEntry,
  listSSHConfigEntries,
  getSSHConfigPath,
  persistSSHKey,
  persistKnownHosts,
  removePersistedKeys,
  listPersistedKeys,
  cleanupAllPersistedKeys,
  configureVSCodeSettings,
  setHostServerInstallPath,
  removeHostFromRemotePlatform,
  checkVSCodeConfiguration,
  ensureVSCodeEnvSetup,
} from '@rediacc/shared-desktop/vscode';
import { Command } from 'commander';
import { t } from '../i18n/index.js';
import { authService } from '../services/auth.js';
import { contextService } from '../services/context.js';
import { getConnectionVaults } from '../utils/connectionDetails.js';
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

interface ConnectionDetails {
  host: string;
  user: string;
  port: number;
  privateKey: string;
  known_hosts: string;
  datastore: string;
  universalUser: string;
  repositoryPath?: string;
  networkId?: string;
  environment?: Record<string, string>;
  workingDirectory?: string;
}

/**
 * Debug logging helper
 */
function debugLog(message: string): void {
  if (process.env.REDIACC_DEBUG || process.env.DEBUG) {
    // eslint-disable-next-line no-console
    console.log(`[DEBUG] ${message}`);
  }
}

/**
 * Gets SSH connection details from the API using type-safe endpoints
 */
async function getSSHConnectionDetails(
  teamName: string,
  machineName: string,
  repositoryName?: string
): Promise<ConnectionDetails> {
  debugLog(
    `Getting SSH connection details for team=${teamName}, machine=${machineName}, repository=${repositoryName ?? '(none)'}`
  );

  // Fetch vault data using type-safe API
  const vaults = await getConnectionVaults(teamName, machineName, repositoryName);
  const machineVault = vaults.machineVault;
  const teamVault = vaults.teamVault;

  // Select host field with fallback
  const host = (machineVault.ip ?? machineVault.host) as string | undefined;
  const port = (machineVault.port ?? 22) as number;

  // Select private key field with fallback
  const privateKey = (teamVault.SSH_PRIVATE_KEY ?? teamVault.sshPrivateKey) as string | undefined;

  // Select host entry field with fallback
  const knownHosts = (machineVault.known_hosts ?? '') as string;

  if (!host) {
    throw new Error(t('errors.vscode.noIpAddress', { machine: machineName }));
  }

  if (!privateKey) {
    throw new Error(t('errors.vscode.noPrivateKey', { team: teamName }));
  }

  if (!knownHosts) {
    throw new Error(t('errors.vscode.noHostKey', { machine: machineName }));
  }

  const datastore = (machineVault.datastore ?? '/mnt/rediacc') as string;
  const universalUser = (machineVault.universalUser ?? 'rediacc') as string;

  let user = (machineVault.user ?? 'root') as string;
  let environment: Record<string, string> = {};
  let workingDirectory: string | undefined;
  let repositoryPath: string | undefined;
  let networkId: string | undefined;

  // If repository is specified, use repository vault from already-fetched data
  if (repositoryName) {
    debugLog(`Using repository vault for: ${repositoryName}`);

    const repoVault = vaults.repositoryVault ?? {};

    repositoryPath = (repoVault.path ?? `/home/${repositoryName}`) as string;
    networkId = (repoVault.networkId ?? '') as string;
    const networkMode = (repoVault.networkMode ?? machineVault.networkMode ?? 'bridge') as string;
    const tag = (repoVault.tag ?? 'latest') as string;
    const immovable = repoVault.immovable ? 'true' : 'false';

    // Repository user
    user = repositoryName;
    workingDirectory = (repoVault.workingDirectory ?? repositoryPath) as string;

    // Build comprehensive environment variables
    environment = {
      REDIACC_TEAM: teamName,
      REDIACC_MACHINE: machineName,
      REDIACC_REPOSITORY: repositoryName,
      DOCKER_DATA: `${datastore}${repositoryPath}`,
      DOCKER_EXEC: `${datastore}${repositoryPath}/.docker-exec`,
      DOCKER_FOLDER: `${datastore}${repositoryPath}`,
      DOCKER_HOST: (machineVault.dockerHost ?? 'unix:///var/run/docker.sock') as string,
      DOCKER_SOCKET: (machineVault.dockerSocket ?? '/var/run/docker.sock') as string,
      REDIACC_DATASTORE: datastore,
      REDIACC_DATASTORE_USER: universalUser,
      REDIACC_NETWORK_ID: networkId,
      REDIACC_IMMOVABLE: immovable,
      REPOSITORY_NETWORK_ID: networkId,
      REPOSITORY_NETWORK_MODE: networkMode,
      REPOSITORY_PATH: repositoryPath,
      REPOSITORY_TAG: tag,
      UNIVERSAL_USER_NAME: universalUser,
      UNIVERSAL_USER_ID: (machineVault.universalUserId ?? '1000') as string,
      ...(typeof repoVault.environment === 'object' && repoVault.environment !== null
        ? (repoVault.environment as Record<string, string>)
        : {}),
    };
  } else {
    // Machine-only mode
    user = universalUser;
    workingDirectory = datastore;
    environment = {
      REDIACC_TEAM: teamName,
      REDIACC_MACHINE: machineName,
      REDIACC_DATASTORE: datastore,
      REDIACC_DATASTORE_USER: universalUser,
      UNIVERSAL_USER_NAME: universalUser,
    };
  }

  return {
    host,
    user,
    port,
    privateKey,
    known_hosts: knownHosts,
    datastore,
    universalUser,
    repositoryPath,
    networkId,
    environment,
    workingDirectory,
  };
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

  // Find VS Code executable
  const vscodeInfo = await withSpinner(t('commands.vscode.connect.detecting'), async () => {
    const info = await findVSCode();
    if (!info) {
      throw new Error(t('errors.vscode.notFound'));
    }
    return info;
  });

  debugLog(`Found VS Code: ${vscodeInfo.path}${vscodeInfo.isInsiders ? ' (Insiders)' : ''}`);

  // Check Remote SSH extension (warning only)
  const hasRemoteSSH = await isRemoteSSHExtensionInstalled();
  if (!hasRemoteSSH) {
    console.warn(t('commands.vscode.connect.extensionWarning'));
  }

  // Get connection details
  const connectionDetails = await withSpinner(t('commands.vscode.connect.fetchingDetails'), () =>
    getSSHConnectionDetails(teamName, machineName, repositoryName)
  );

  // Test SSH connectivity
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

  // Persist SSH key for long-running VS Code sessions
  const identityFile = await withSpinner(t('commands.vscode.connect.persistingKey'), () => {
    return Promise.resolve(
      persistSSHKey(teamName, machineName, repositoryName, connectionDetails.privateKey)
    );
  });

  // Persist known hosts
  const knownHostsFile = persistKnownHosts(teamName, machineName, connectionDetails.known_hosts);

  debugLog(`Identity file: ${identityFile}`);
  debugLog(`Known hosts file: ${knownHostsFile}`);

  // Build and add SSH config entry
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

  // Configure VS Code settings
  await withSpinner(t('commands.vscode.connect.configuringVSCode'), () => {
    const isInsiders = options.insiders ?? vscodeInfo.isInsiders;
    const result = configureVSCodeSettings(isInsiders);

    if (!result.success) {
      console.warn(t('commands.vscode.connect.settingsWarning', { error: result.error }));
    }

    // Set per-host server install path
    if (connectionDetails.datastore) {
      setHostServerInstallPath(
        connectionName,
        `${connectionDetails.datastore}/.vscode-server`,
        isInsiders
      );
    }

    // Remove from remotePlatform to enable RemoteCommand
    removeHostFromRemotePlatform(connectionName, isInsiders);
    return Promise.resolve();
  });

  // Setup remote environment (optional)
  if (!options.skipEnvSetup && connectionDetails.environment) {
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

  // Build remote folder path
  const remotePath =
    options.folder ?? connectionDetails.workingDirectory ?? connectionDetails.datastore;

  // Generate URI
  const vscodeUri = generateRemoteUri(connectionName, remotePath);

  // Output URL or launch
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
    const hasKey = keys.some((k: string) => entry.includes(k.replace(/_/g, '-')));
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

  // Check VS Code installation
  // eslint-disable-next-line no-console
  console.log(t('commands.vscode.check.installation'));
  const vscode = await findVSCode();
  if (vscode) {
    // eslint-disable-next-line no-console
    console.log(t('commands.vscode.check.vscodeFound', { path: vscode.path }));
    if (vscode.version) {
      // eslint-disable-next-line no-console
      console.log(t('commands.vscode.check.version', { version: vscode.version }));
    }
    if (vscode.isInsiders) {
      // eslint-disable-next-line no-console
      console.log(t('commands.vscode.check.variant'));
    }
  } else {
    // eslint-disable-next-line no-console
    console.log(t('commands.vscode.check.vscodeNotFound'));
  }

  // Check Remote SSH extension
  const hasExtension = await isRemoteSSHExtensionInstalled();
  // eslint-disable-next-line no-console
  console.log(
    t('commands.vscode.check.remoteSSH', {
      status: hasExtension
        ? t('commands.vscode.check.installed')
        : t('commands.vscode.check.notDetected'),
    })
  );

  // Check VS Code settings
  // eslint-disable-next-line no-console
  console.log(t('commands.vscode.check.configuration'));
  const configCheck = checkVSCodeConfiguration(isInsiders);
  // eslint-disable-next-line no-console
  console.log(t('commands.vscode.check.settingsPath', { path: configCheck.settingsPath }));
  // eslint-disable-next-line no-console
  console.log(
    t('commands.vscode.check.configured', {
      status: configCheck.configured
        ? t('commands.vscode.check.yes')
        : t('commands.vscode.check.no'),
    })
  );
  if (configCheck.missing.length > 0) {
    // eslint-disable-next-line no-console
    console.log(t('commands.vscode.check.missingSettings'));
    for (const setting of configCheck.missing) {
      // eslint-disable-next-line no-console
      console.log(`    - ${setting}`);
    }
  }

  // Check SSH config file
  const configPath = getSSHConfigPath();
  // eslint-disable-next-line no-console
  console.log(t('commands.vscode.check.sshConfig', { path: configPath }));

  // List active connections
  const connections = listSSHConfigEntries();
  // eslint-disable-next-line no-console
  console.log(t('commands.vscode.check.activeConnections', { count: connections.length }));

  if (connections.length > 0) {
    for (const conn of connections) {
      // eslint-disable-next-line no-console
      console.log(`  - ${conn}`);
    }
  }
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
