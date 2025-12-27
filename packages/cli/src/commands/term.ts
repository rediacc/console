import { generateSourceCommand, generateSetupCommand } from '@rediacc/shared-desktop/repository';
import { SSHConnection, spawnSSH, testSSHConnectivity } from '@rediacc/shared-desktop/ssh';
import { launchTerminal, getDefaultTerminalType } from '@rediacc/shared-desktop/terminal';
import { Command } from 'commander';
import { apiClient } from '../services/api.js';
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
  hostEntry: string;
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

/**
 * Gets SSH connection details from the API
 */
async function getSSHConnectionDetails(
  teamName: string,
  machineName: string,
  repositoryName?: string
): Promise<ConnectionDetails> {
  debugLog(
    `Getting SSH connection details for team=${teamName}, machine=${machineName}, repository=${repositoryName ?? '(none)'}`
  );

  // Get machine details
  const machineResponse = (await apiClient.post('GetMachineDetails', {
    teamName,
    machineName,
  })) as { machineVault?: Record<string, unknown>; teamVault?: Record<string, unknown> };

  const machineVault = machineResponse.machineVault ?? {};
  const teamVault = machineResponse.teamVault ?? {};

  // Log available vault fields for debugging
  debugLog(`Machine vault fields: ${Object.keys(machineVault).join(', ') || '(empty)'}`);
  debugLog(`Team vault fields: ${Object.keys(teamVault).join(', ') || '(empty)'}`);

  // Select host field with fallback (ip preferred, then host)
  const host = (machineVault.ip ?? machineVault.host) as string | undefined;
  debugLog(
    `Host selection: ip=${machineVault.ip ? 'set' : 'unset'}, host=${machineVault.host ? 'set' : 'unset'} -> using '${host}'`
  );

  const port = (machineVault.sshPort ?? 22) as number;
  debugLog(`Port: sshPort=${machineVault.sshPort ?? '(default 22)'}`);

  // Select private key field with fallback
  const privateKey = (teamVault.SSH_PRIVATE_KEY ?? teamVault.sshPrivateKey) as string | undefined;
  debugLog(
    `Private key: SSH_PRIVATE_KEY=${teamVault.SSH_PRIVATE_KEY ? 'set' : 'unset'}, sshPrivateKey=${teamVault.sshPrivateKey ? 'set' : 'unset'}`
  );

  // Select host entry field with fallback
  const hostEntry = (machineVault.hostEntry ?? machineVault.SSH_HOST_KEY ?? '') as string;
  debugLog(
    `Host entry: hostEntry=${machineVault.hostEntry ? 'set' : 'unset'}, SSH_HOST_KEY=${machineVault.SSH_HOST_KEY ? 'set' : 'unset'}`
  );

  if (!host) {
    throw new Error(`Machine '${machineName}' does not have an IP address configured`);
  }

  if (!privateKey) {
    throw new Error(`Team '${teamName}' does not have an SSH private key configured`);
  }

  if (!hostEntry) {
    throw new Error(`Machine '${machineName}' does not have a host key configured in the vault`);
  }

  const datastorePath = (machineVault.datastorePath ?? '/mnt/datastore') as string;
  debugLog(`Datastore path: ${datastorePath}`);

  const universalUser = (machineVault.universalUser ?? 'rediacc') as string;
  debugLog(`Universal user: ${universalUser}`);

  let user = (machineVault.sshUser ?? machineVault.user ?? 'root') as string;
  debugLog(
    `Initial user selection: sshUser=${machineVault.sshUser ? 'set' : 'unset'}, user=${machineVault.user ? 'set' : 'unset'} -> '${user}'`
  );

  let environment: Record<string, string> = {};
  let workingDirectory: string | undefined;

  // If repository is specified, get repository details and build full environment
  if (repositoryName) {
    debugLog(`Fetching repository details for: ${repositoryName}`);

    const repoResponse = (await apiClient.post('GetRepositoryDetails', {
      teamName,
      machineName,
      repositoryName,
    })) as { repositoryVault?: Record<string, unknown> };

    const repoVault = repoResponse.repositoryVault ?? {};
    debugLog(`Repository vault fields: ${Object.keys(repoVault).join(', ') || '(empty)'}`);

    const repoPath = (repoVault.path ?? `/home/${repositoryName}`) as string;
    const networkId = (repoVault.networkId ?? '') as string;
    const networkMode = (repoVault.networkMode ?? machineVault.networkMode ?? 'bridge') as string;
    const tag = (repoVault.tag ?? 'latest') as string;
    const immovable = repoVault.immovable ? 'true' : 'false';

    debugLog(
      `Repository config: path=${repoPath}, networkId=${networkId || '(none)'}, networkMode=${networkMode}, tag=${tag}, immovable=${immovable}`
    );

    // Repository user (typically the repository name)
    user = repositoryName;
    debugLog(`User overridden to repository name: ${user}`);

    // Working directory inside the repository
    workingDirectory = (repoVault.workingDirectory ?? repoPath) as string;
    debugLog(`Working directory: ${workingDirectory}`);

    // Build comprehensive environment variables (matching Python's 18+ vars)
    environment = {
      // Core identifiers
      REDIACC_TEAM: teamName,
      REDIACC_MACHINE: machineName,
      REDIACC_REPOSITORY: repositoryName,

      // Docker-related
      DOCKER_DATA: `${datastorePath}${repoPath}`,
      DOCKER_EXEC: `${datastorePath}${repoPath}/.docker-exec`,
      DOCKER_FOLDER: `${datastorePath}${repoPath}`,
      DOCKER_HOST: (machineVault.dockerHost ?? 'unix:///var/run/docker.sock') as string,
      DOCKER_SOCKET: (machineVault.dockerSocket ?? '/var/run/docker.sock') as string,

      // Network and datastore
      REDIACC_DATASTORE: datastorePath,
      REDIACC_DATASTORE_USER: universalUser,
      REDIACC_NETWORK_ID: networkId,
      REDIACC_IMMOVABLE: immovable,

      // Repository-specific
      REPOSITORY_NETWORK_ID: networkId,
      REPOSITORY_NETWORK_MODE: networkMode,
      REPOSITORY_PATH: repoPath,
      REPOSITORY_TAG: tag,

      // System
      UNIVERSAL_USER_NAME: universalUser,
      UNIVERSAL_USER_ID: (machineVault.universalUserId ?? '1000') as string,

      // Custom environment variables merge:
      // If the repository vault contains an 'environment' object, its key-value pairs
      // are merged last, allowing per-repository custom environment overrides.
      // This matches Python CLI's custom env merge behavior from repository_env.py
      // Example vault format: { "environment": { "MY_VAR": "value", "DEBUG": "true" } }
      ...(typeof repoVault.environment === 'object' && repoVault.environment !== null
        ? (repoVault.environment as Record<string, string>)
        : {}),
    };
  } else {
    // Machine-only mode - minimal environment
    debugLog('Machine-only mode (no repository specified)');
    user = universalUser;
    workingDirectory = datastorePath;
    environment = {
      REDIACC_TEAM: teamName,
      REDIACC_MACHINE: machineName,
      REDIACC_DATASTORE: datastorePath,
      REDIACC_DATASTORE_USER: universalUser,
      UNIVERSAL_USER_NAME: universalUser,
    };
    debugLog(`User set to universal user: ${user}`);
    debugLog(`Working directory set to datastore: ${workingDirectory}`);
  }

  debugLog(`Final connection: ${user}@${host}:${port}, workingDirectory=${workingDirectory}`);
  debugLog(`Environment variables count: ${Object.keys(environment).length}`);

  return {
    host,
    user,
    port,
    privateKey,
    hostEntry,
    environment,
    workingDirectory,
  };
}

/**
 * Connects to a machine or repository via SSH
 */
async function connectTerminal(options: TermConnectOptions): Promise<void> {
  const opts = await contextService.applyDefaults(options);

  if (!opts.machine) {
    throw new Error('Machine name is required. Use --machine <name> or set a default context.');
  }

  // eslint-disable-next-line @typescript-eslint/no-unnecessary-type-assertion -- opts index signature returns unknown
  const teamName = (opts.team as string | undefined) ?? 'Default';
  // eslint-disable-next-line @typescript-eslint/no-unnecessary-type-assertion -- opts index signature returns unknown
  const machineName = opts.machine as string;
  const repositoryName = opts.repository as string | undefined;

  // Get SSH connection details
  const connectionDetails = await withSpinner('Fetching connection details...', () =>
    getSSHConnectionDetails(teamName, machineName, repositoryName)
  );

  // Test SSH connectivity before attempting connection (matches Python CLI behavior)
  const connectivityResult = await withSpinner(
    `Testing connectivity to ${connectionDetails.host}:${connectionDetails.port}...`,
    () => testSSHConnectivity(connectionDetails.host, connectionDetails.port, 10000)
  );

  if (!connectivityResult.success) {
    throw new Error(
      `Cannot reach ${connectionDetails.host}:${connectionDetails.port}. ` +
        `${connectivityResult.error}\n\n` +
        `Troubleshooting:\n` +
        `  - Check if the machine is powered on and connected to the network\n` +
        `  - Verify the IP address is correct in the machine vault\n` +
        `  - Ensure port ${connectionDetails.port} is not blocked by a firewall\n` +
        `  - Try pinging the machine: ping ${connectionDetails.host}`
    );
  }

  // Create SSH connection with forceTTY for interactive terminals (matches Python CLI's -tt flag)
  const sshConnection = new SSHConnection(
    connectionDetails.privateKey,
    connectionDetails.hostEntry,
    {
      port: connectionDetails.port,
      forceTTY: true, // Force TTY allocation for interactive sessions
    }
  );

  try {
    // Set up the connection (creates temp key file, etc.)
    await sshConnection.setup();

    // Determine title for the terminal
    const title = repositoryName
      ? `Rediacc - ${teamName}/${machineName}/${repositoryName}`
      : `Rediacc - ${teamName}/${machineName}`;

    // Build destination string
    const destination = `${connectionDetails.user}@${connectionDetails.host}`;

    // Build command to execute on remote
    let remoteCommand: string | undefined;
    if (options.container) {
      const containerId = options.container;
      const containerAction = options.containerAction ?? 'terminal';

      switch (containerAction) {
        case 'logs': {
          // Docker logs with optional tail and follow
          const lines = options.logLines ?? '50';
          const followFlag = options.follow ? '-f' : '';
          remoteCommand = `docker logs --tail ${lines} ${followFlag} ${containerId}`.trim();
          break;
        }
        case 'stats':
          // Docker stats for the container
          remoteCommand = `docker stats ${containerId}`;
          break;
        case 'exec':
          // Docker exec with specified command
          remoteCommand = `docker exec -it ${containerId} ${options.command ?? '/bin/bash'}`;
          break;
        case 'terminal':
        default:
          // Interactive shell in container (default)
          remoteCommand = `docker exec -it ${containerId} ${options.command ?? '/bin/bash'}`;
          break;
      }
    } else if (options.command) {
      // User-specified command - ensure bash functions are installed and source them
      // Check if file exists, create if not (matches Python CLI behavior)
      const ensureBashFunctions = `[ -f ~/.bashrc-rediacc ] || { ${generateSetupCommand()}; }; ${generateSourceCommand()}`;
      remoteCommand = `${ensureBashFunctions} && ${options.command}`;
    } else {
      // Interactive shell - ensure bash functions are installed, source them, then start shell
      const ensureBashFunctions = `[ -f ~/.bashrc-rediacc ] || { ${generateSetupCommand()}; }; ${generateSourceCommand()}`;
      remoteCommand = `${ensureBashFunctions} && exec bash`;
    }

    // Check if we're in a TTY and should use inline mode
    const isTTY = process.stdin.isTTY && process.stdout.isTTY;
    const useExternal = options.external ?? !isTTY;

    if (useExternal) {
      // Build command string for external terminal
      const sshArgs = [...sshConnection.sshOptions, destination];
      if (remoteCommand) {
        sshArgs.push(remoteCommand);
      }
      const sshCommand = `ssh ${sshArgs.join(' ')}`;

      // Launch external terminal
      const terminalType = getDefaultTerminalType();

      // eslint-disable-next-line no-console
      console.log(`Launching ${terminalType} terminal...`);

      const result = launchTerminal(terminalType, {
        command: sshCommand,
        title,
        keepOpen: true,
        environmentVariables: connectionDetails.environment,
        workingDirectory: connectionDetails.workingDirectory,
      });

      if (!result.success) {
        throw new Error(`Failed to launch terminal: ${result.error}`);
      }

      // eslint-disable-next-line no-console
      console.log('Terminal launched successfully.');
    } else {
      // Inline mode - spawn SSH with inherited stdio
      // eslint-disable-next-line no-console
      console.log(`Connecting to ${title}...`);

      // Spawn SSH process with inherited stdio
      // Pass agent socket path if using ssh-agent (matches Python CLI's SSH_AUTH_SOCK handling)
      const child = spawnSSH(destination, sshConnection.sshOptions, remoteCommand, {
        env: { ...process.env, ...connectionDetails.environment },
        stdio: 'inherit',
        agentSocketPath: sshConnection.agentSocketPath,
      });

      // Wait for the process to exit
      await new Promise<void>((resolve, reject) => {
        child.on('exit', (code: number | null) => {
          if (code === 0 || code === null) {
            resolve();
          } else {
            // Provide diagnostic messages for common SSH exit codes (matches Python CLI)
            let message = `SSH exited with code ${code}`;
            switch (code) {
              case 1:
                message += '\n  Generic error - check command syntax or remote permissions';
                break;
              case 126:
                message += '\n  Permission denied - cannot execute command on remote';
                break;
              case 127:
                message += '\n  Command not found on remote machine';
                break;
              case 130:
                message += '\n  Connection terminated by user (Ctrl+C)';
                break;
              case 255:
                message += '\n  SSH connection failed - possible causes:';
                message += '\n    - Authentication failed (check SSH key permissions)';
                message += '\n    - Host key verification failed';
                message += '\n    - Network connection dropped';
                message += '\n    - Remote SSH service not running';
                break;
            }
            reject(new Error(message));
          }
        });
        child.on('error', reject);
      });
    }
  } finally {
    // Cleanup temporary files
    await sshConnection.cleanup();
  }
}

/**
 * Registers the term commands
 */
export function registerTermCommands(program: Command): void {
  const term = program
    .command('term')
    .description('SSH terminal access to machines and repositories');

  term
    .command('connect')
    .description('Connect to a machine or repository via SSH')
    .option('-t, --team <name>', 'Team name')
    .option('-m, --machine <name>', 'Machine name')
    .option('-r, --repository <name>', 'Repository name (connects to repository environment)')
    .option('-c, --command <cmd>', 'Execute a command instead of interactive shell')
    .option('--container <id>', 'Connect to a specific Docker container')
    .option('--container-action <action>', 'Container action: terminal, logs, stats, exec')
    .option('--log-lines <lines>', 'Number of log lines to show (default: 50)')
    .option('--follow', 'Follow logs output')
    .option('--external', 'Force launching in external terminal window')
    .action(async (options: TermConnectOptions) => {
      try {
        await authService.requireAuth();
        await connectTerminal(options);
      } catch (error) {
        handleError(error);
      }
    });

  // Shorthand: rdc term <machine> [repository]
  term
    .argument('[machine]', 'Machine name (shorthand for --machine)')
    .argument('[repository]', 'Repository name (shorthand for --repository)')
    .option('-t, --team <name>', 'Team name')
    .option('-c, --command <cmd>', 'Execute a command instead of interactive shell')
    .option('--container <id>', 'Connect to a specific Docker container')
    .option('--container-action <action>', 'Container action: terminal, logs, stats, exec')
    .option('--log-lines <lines>', 'Number of log lines to show (default: 50)')
    .option('--follow', 'Follow logs output')
    .option('--external', 'Force launching in external terminal window')
    .action(
      async (
        machine: string | undefined,
        repository: string | undefined,
        options: TermConnectOptions
      ) => {
        try {
          await authService.requireAuth();
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
