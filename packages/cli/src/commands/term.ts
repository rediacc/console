import { generateSetupCommand, generateSourceCommand } from '@rediacc/shared-desktop/repository';
import { SSHConnection, spawnSSH, testSSHConnectivity } from '@rediacc/shared-desktop/ssh';
import { getDefaultTerminalType, launchTerminal } from '@rediacc/shared-desktop/terminal';
import { Command } from 'commander';
import { DEFAULTS, NETWORK_DEFAULTS } from '@rediacc/shared/config';
import { t } from '../i18n/index.js';
import { getStateProvider } from '../providers/index.js';
import { authService } from '../services/auth.js';
import { contextService } from '../services/context.js';
import { handleError } from '../utils/errors.js';
import { withSpinner } from '../utils/spinner.js';

interface TermConnectOptions {
  team?: string;
  machine?: string;
  repository?: string;
  command?: string;
  container?: string;
  /** Container action: 'terminal' (default), 'logs', 'stats', 'exec' */
  containerAction?: 'terminal' | 'logs' | 'stats' | 'exec';
  /** Number of log lines to show (default: 50) */
  logLines?: string;
  /** Follow logs output */
  follow?: boolean;
  external?: boolean;
  [key: string]: unknown;
}

interface ConnectionDetails {
  host: string;
  user: string;
  port: number;
  privateKey: string;
  known_hosts: string;
  environment?: Record<string, string>;
  workingDirectory?: string;
}

/**
 * Debug logging helper - outputs when REDIACC_DEBUG or DEBUG env var is set
 */
function debugLog(message: string): void {
  if (process.env.REDIACC_DEBUG || process.env.DEBUG) {
    // eslint-disable-next-line no-console
    console.log(`[DEBUG] ${message}`);
  }
}

function extractBaseConnectionInfo(
  machineVault: Record<string, unknown>,
  teamVault: Record<string, unknown>,
  machineName: string,
  teamName: string
) {
  const host = (machineVault.ip ?? machineVault.host) as string | undefined;
  const port = (machineVault.port ?? DEFAULTS.SSH.PORT) as number;
  const privateKey = (teamVault.SSH_PRIVATE_KEY ?? teamVault.sshPrivateKey) as string | undefined;
  const knownHosts = (machineVault.known_hosts ?? '') as string;
  const datastore = (machineVault.datastore ?? NETWORK_DEFAULTS.DATASTORE_PATH) as string;
  const universalUser = (machineVault.universalUser ??
    DEFAULTS.REPOSITORY.UNIVERSAL_USER) as string;

  if (!host) {
    throw new Error(t('errors.term.noIpAddress', { machine: machineName }));
  }
  if (!privateKey) {
    throw new Error(t('errors.term.noPrivateKey', { team: teamName }));
  }
  if (!knownHosts) {
    throw new Error(t('errors.term.noHostKey', { machine: machineName }));
  }

  return { host, port, privateKey, knownHosts, datastore, universalUser };
}

function buildRepositoryEnvironment(
  teamName: string,
  machineName: string,
  repositoryName: string,
  machineVault: Record<string, unknown>,
  repoVault: Record<string, unknown>,
  datastore: string,
  universalUser: string
): { environment: Record<string, string>; workingDirectory: string; user: string } {
  const repositoryPath = (repoVault.path ?? `/home/${repositoryName}`) as string;
  const networkId = (repoVault.networkId ?? '') as string;
  const networkMode = (repoVault.networkMode ??
    machineVault.networkMode ??
    DEFAULTS.REPOSITORY.NETWORK_MODE) as string;
  const tag = (repoVault.tag ?? DEFAULTS.REPOSITORY.TAG) as string;
  const immovable = repoVault.immovable ? 'true' : 'false';
  const workingDirectory = (repoVault.workingDirectory ?? repositoryPath) as string;

  const environment: Record<string, string> = {
    REDIACC_TEAM: teamName,
    REDIACC_MACHINE: machineName,
    REDIACC_REPOSITORY: repositoryName,
    DOCKER_DATA: `${datastore}${repositoryPath}`,
    DOCKER_EXEC: `${datastore}${repositoryPath}/.docker-exec`,
    DOCKER_FOLDER: `${datastore}${repositoryPath}`,
    DOCKER_HOST: (machineVault.dockerHost ?? DEFAULTS.DOCKER.HOST_URI) as string,
    DOCKER_SOCKET: (machineVault.dockerSocket ?? DEFAULTS.DOCKER.SOCKET_PATH) as string,
    REDIACC_DATASTORE: datastore,
    REDIACC_DATASTORE_USER: universalUser,
    REDIACC_NETWORK_ID: networkId,
    REDIACC_IMMOVABLE: immovable,
    REPOSITORY_NETWORK_ID: networkId,
    REPOSITORY_NETWORK_MODE: networkMode,
    REPOSITORY_PATH: repositoryPath,
    REPOSITORY_TAG: tag,
    UNIVERSAL_USER_NAME: universalUser,
    UNIVERSAL_USER_ID: (machineVault.universalUserId ??
      DEFAULTS.REPOSITORY.UNIVERSAL_USER_ID) as string,
    ...(typeof repoVault.environment === 'object' && repoVault.environment !== null
      ? (repoVault.environment as Record<string, string>)
      : {}),
  };

  return { environment, workingDirectory, user: repositoryName };
}

function buildMachineEnvironment(
  teamName: string,
  machineName: string,
  datastore: string,
  universalUser: string
): { environment: Record<string, string>; workingDirectory: string; user: string } {
  return {
    environment: {
      REDIACC_TEAM: teamName,
      REDIACC_MACHINE: machineName,
      REDIACC_DATASTORE: datastore,
      REDIACC_DATASTORE_USER: universalUser,
      UNIVERSAL_USER_NAME: universalUser,
    },
    workingDirectory: datastore,
    user: universalUser,
  };
}

/**
 * Gets SSH connection details using the mode-aware state provider
 */
async function getSSHConnectionDetails(
  teamName: string,
  machineName: string,
  repositoryName?: string
): Promise<ConnectionDetails> {
  debugLog(
    `Getting SSH connection details for team=${teamName}, machine=${machineName}, repository=${repositoryName ?? '(none)'}`
  );

  const provider = await getStateProvider();
  const vaults = await provider.vaults.getConnectionVaults(teamName, machineName, repositoryName);
  const { machineVault, teamVault } = vaults;

  debugLog(`Machine vault fields: ${Object.keys(machineVault).join(', ') || '(empty)'}`);
  debugLog(`Team vault fields: ${Object.keys(teamVault).join(', ') || '(empty)'}`);

  const baseInfo = extractBaseConnectionInfo(machineVault, teamVault, machineName, teamName);

  let envData: { environment: Record<string, string>; workingDirectory: string; user: string };

  if (repositoryName) {
    debugLog(`Using repository vault for: ${repositoryName}`);
    const repoVault = vaults.repositoryVault ?? {};
    debugLog(`Repository vault fields: ${Object.keys(repoVault).join(', ') || '(empty)'}`);

    envData = buildRepositoryEnvironment(
      teamName,
      machineName,
      repositoryName,
      machineVault,
      repoVault,
      baseInfo.datastore,
      baseInfo.universalUser
    );
    debugLog(`User set to repository name: ${envData.user}`);
    debugLog(`Working directory: ${envData.workingDirectory}`);
  } else {
    debugLog('Machine-only mode (no repository specified)');
    envData = buildMachineEnvironment(
      teamName,
      machineName,
      baseInfo.datastore,
      baseInfo.universalUser
    );
    debugLog(`User set to universal user: ${envData.user}`);
    debugLog(`Working directory set to datastore: ${envData.workingDirectory}`);
  }

  debugLog(
    `Final connection: ${envData.user}@${baseInfo.host}:${baseInfo.port}, workingDirectory=${envData.workingDirectory}`
  );
  debugLog(`Environment variables count: ${Object.keys(envData.environment).length}`);

  return {
    host: baseInfo.host,
    user: envData.user,
    port: baseInfo.port,
    privateKey: baseInfo.privateKey,
    known_hosts: baseInfo.knownHosts,
    environment: envData.environment,
    workingDirectory: envData.workingDirectory,
  };
}

type ContainerAction = 'terminal' | 'logs' | 'stats' | 'exec';

const containerCommandBuilders: Record<
  ContainerAction,
  (options: TermConnectOptions, containerId: string) => string
> = {
  logs: (options, containerId) => {
    const lines = options.logLines ?? DEFAULTS.REPOSITORY.LOG_LINES;
    const followFlag = options.follow ? '-f' : '';
    return `docker logs --tail ${lines} ${followFlag} ${containerId}`.trim();
  },
  stats: (_, containerId) => `docker stats ${containerId}`,
  exec: (options, containerId) =>
    `docker exec -it ${containerId} ${options.command ?? DEFAULTS.SHELL.BASH}`,
  terminal: (options, containerId) =>
    `docker exec -it ${containerId} ${options.command ?? DEFAULTS.SHELL.BASH}`,
};

function buildRemoteCommand(options: TermConnectOptions): string | undefined {
  if (options.container) {
    const containerId = options.container;
    const containerAction = (options.containerAction ??
      DEFAULTS.REPOSITORY.CONTAINER_ACTION) as ContainerAction;
    const builder = containerCommandBuilders[containerAction];
    return builder(options, containerId);
  }

  const ensureBashFunctions = `[ -f ~/.bashrc-rediacc ] || { ${generateSetupCommand()}; }; ${generateSourceCommand()}`;

  if (options.command) {
    return `${ensureBashFunctions} && ${options.command}`;
  }

  return `${ensureBashFunctions} && exec bash`;
}

async function validateAndGetConnectionDetails(opts: {
  team?: string;
  machine?: string;
  repository?: string;
}) {
  if (!opts.team) {
    throw new Error(t('errors.teamRequired'));
  }
  if (!opts.machine) {
    throw new Error(t('errors.machineRequired'));
  }

  const connectionDetails = await withSpinner(t('commands.term.fetchingDetails'), () =>
    getSSHConnectionDetails(opts.team!, opts.machine!, opts.repository)
  );

  const connectivityResult = await withSpinner(
    t('commands.term.testingConnectivity', {
      host: connectionDetails.host,
      port: connectionDetails.port,
    }),
    () => testSSHConnectivity(connectionDetails.host, connectionDetails.port, 10000)
  );

  if (!connectivityResult.success) {
    throw new Error(
      t('errors.term.connectivityFailed', {
        host: connectionDetails.host,
        port: connectionDetails.port,
        error: connectivityResult.error,
      })
    );
  }

  return {
    connectionDetails,
    teamName: opts.team,
    machineName: opts.machine,
    repositoryName: opts.repository,
  };
}

/**
 * Connects to a machine or repository via SSH
 */
async function connectTerminal(options: TermConnectOptions): Promise<void> {
  const opts = await contextService.applyDefaults(options);
  const { connectionDetails, teamName, machineName, repositoryName } =
    await validateAndGetConnectionDetails(opts);

  const sshConnection = new SSHConnection(
    connectionDetails.privateKey,
    connectionDetails.known_hosts,
    { port: connectionDetails.port, forceTTY: true }
  );

  try {
    await sshConnection.setup();

    const title = repositoryName
      ? `Rediacc - ${teamName}/${machineName}/${repositoryName}`
      : `Rediacc - ${teamName}/${machineName}`;

    const destination = `${connectionDetails.user}@${connectionDetails.host}`;
    const remoteCommand = buildRemoteCommand(options);

    const isTTY = process.stdin.isTTY && process.stdout.isTTY;
    const useExternal = options.external ?? !isTTY;

    if (useExternal) {
      launchExternalTerminal(sshConnection, destination, remoteCommand, title, connectionDetails);
    } else {
      await runInlineSSH(sshConnection, destination, remoteCommand, title, connectionDetails);
    }
  } finally {
    await sshConnection.cleanup();
  }
}

function launchExternalTerminal(
  sshConnection: SSHConnection,
  destination: string,
  remoteCommand: string | undefined,
  title: string,
  connectionDetails: ConnectionDetails
): void {
  const sshArgs = [...sshConnection.sshOptions, destination];
  if (remoteCommand) {
    sshArgs.push(remoteCommand);
  }
  const sshCommand = `ssh ${sshArgs.join(' ')}`;
  const terminalType = getDefaultTerminalType();

  // eslint-disable-next-line no-console
  console.log(t('commands.term.launchingTerminal', { type: terminalType }));

  const result = launchTerminal(terminalType, {
    command: sshCommand,
    title,
    keepOpen: true,
    environmentVariables: connectionDetails.environment,
    workingDirectory: connectionDetails.workingDirectory,
  });

  if (!result.success) {
    throw new Error(t('errors.term.launchFailed', { error: result.error }));
  }

  // eslint-disable-next-line no-console
  console.log(t('commands.term.launchSuccess'));
}

const sshExitCodeMessages: Record<number, string> = {
  1: 'sshCode1',
  126: 'sshCode126',
  127: 'sshCode127',
  130: 'sshCode130',
  255: 'sshCode255',
};

function buildSSHExitErrorMessage(code: number): string {
  let message = t('errors.term.sshExitCode', { code });
  const codeKey = sshExitCodeMessages[code];
  if (codeKey) {
    message += `\n  ${t(`errors.term.${codeKey}`)}`;
  }
  return message;
}

async function runInlineSSH(
  sshConnection: SSHConnection,
  destination: string,
  remoteCommand: string | undefined,
  title: string,
  connectionDetails: ConnectionDetails
): Promise<void> {
  // eslint-disable-next-line no-console
  console.log(t('commands.term.connectingTo', { title }));

  const child = spawnSSH(destination, sshConnection.sshOptions, remoteCommand, {
    env: { ...process.env, ...connectionDetails.environment },
    stdio: 'inherit',
    agentSocketPath: sshConnection.agentSocketPath,
  });

  await new Promise<void>((resolve, reject) => {
    child.on('exit', (code: number | null) => {
      if (code === 0 || code === null) {
        resolve();
      } else {
        reject(new Error(buildSSHExitErrorMessage(code)));
      }
    });
    child.on('error', reject);
  });
}

/**
 * Registers the term commands
 */
export function registerTermCommands(program: Command): void {
  const term = program.command('term').description(t('commands.term.description'));

  term
    .command('connect')
    .description(t('commands.term.connect.description'))
    .option('-t, --team <name>', t('options.team'))
    .option('-m, --machine <name>', t('options.machine'))
    .option('-r, --repository <name>', t('options.repository'))
    .option('-c, --command <cmd>', t('options.command'))
    .option('--container <id>', t('options.container'))
    .option('--container-action <action>', t('options.containerAction'))
    .option('--log-lines <lines>', t('options.logLines'))
    .option('--follow', t('options.follow'))
    .option('--external', t('options.external'))
    .action(async (options: TermConnectOptions) => {
      try {
        const provider = await getStateProvider();
        if (provider.mode === 'cloud') {
          await authService.requireAuth();
        }
        await connectTerminal(options);
      } catch (error) {
        handleError(error);
      }
    });

  // Shorthand: rdc term <machine> [repository]
  term
    .argument('[machine]', t('options.machineShorthand'))
    .argument('[repository]', t('options.repositoryShorthand'))
    .option('-t, --team <name>', t('options.team'))
    .option('-c, --command <cmd>', t('options.command'))
    .option('--container <id>', t('options.container'))
    .option('--container-action <action>', t('options.containerAction'))
    .option('--log-lines <lines>', t('options.logLines'))
    .option('--follow', t('options.follow'))
    .option('--external', t('options.external'))
    .action(
      async (
        machine: string | undefined,
        repository: string | undefined,
        options: TermConnectOptions
      ) => {
        try {
          const provider = await getStateProvider();
          if (provider.mode === 'cloud') {
            await authService.requireAuth();
          }
          await connectTerminal({
            ...options,
            machine: machine ?? options.machine,
            repository: repository ?? options.repository,
          });
        } catch (error) {
          handleError(error);
        }
      }
    );
}
