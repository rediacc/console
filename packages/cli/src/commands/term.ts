import { DEFAULTS } from '@rediacc/shared/config';
import { generateSetupCommand, generateSourceCommand } from '@rediacc/shared-desktop/repository';
import { SSHConnection, spawnSSH, testSSHConnectivity } from '@rediacc/shared-desktop/ssh';
import { getDefaultTerminalType, launchTerminal } from '@rediacc/shared-desktop/terminal';
import { Command } from 'commander';
import { t } from '../i18n/index.js';
import { getStateProvider } from '../providers/index.js';
import { authService } from '../services/auth.js';
import { configService } from '../services/config-resources.js';
import { provisionRenetToRemote, readSSHKey } from '../services/renet-execution.js';
import { getSSHConnectionDetails, type ConnectionDetails } from './term-connection.js';
import { assertAgentMachineAccess } from '../utils/agent-guard.js';
import { assertCommandPolicy, CMD } from '../utils/command-policy.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { detectRepoContextCommand } from '../utils/repo-context-guard.js';
import {
  buildSandboxPrefix,
  buildTermSandboxOptions,
  shellEscapeForBashC,
} from '../utils/sandbox.js';
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

/**
 * Debug logging helper - outputs when REDIACC_DEBUG or DEBUG env var is set
 */
function debugLog(message: string): void {
  if (process.env.REDIACC_DEBUG || process.env.DEBUG) {
    // eslint-disable-next-line no-console
    console.log(`[DEBUG] ${message}`);
  }
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

function buildEnvPrefix(connectionDetails?: ConnectionDetails): string {
  const parts: string[] = [];

  if (connectionDetails?.environment) {
    for (const [key, value] of Object.entries(connectionDetails.environment)) {
      const escaped = String(value).replaceAll("'", "'\\''");
      parts.push(`export ${key}='${escaped}'`);
    }
  }

  if (connectionDetails?.workingDirectory) {
    parts.push(`cd '${connectionDetails.workingDirectory}' 2>/dev/null`);
  }

  return parts.length > 0 ? `${parts.join('; ')}; ` : '';
}

function buildContainerCommand(
  options: TermConnectOptions,
  envPrefix: string,
  sandbox: string
): string {
  const containerId = options.container!;
  const containerAction = (options.containerAction ??
    DEFAULTS.REPOSITORY.CONTAINER_ACTION) as ContainerAction;
  const builder = containerCommandBuilders[containerAction];
  const dockerCmd = builder(options, containerId);
  return sandbox ? `${envPrefix}${sandbox} ${dockerCmd}` : `${envPrefix}${dockerCmd}`;
}

function buildShellCommand(
  options: TermConnectOptions,
  envPrefix: string,
  sandbox: string
): string {
  const ensureBashSetup = `[ -f ~/.bashrc-rediacc ] || { ${generateSetupCommand()}; }`;
  const sourceCmd = generateSourceCommand();
  const userCmd = options.command;

  if (sandbox) {
    const setupPart = `${envPrefix}${ensureBashSetup}; `;
    const inner = userCmd ? `${sourceCmd} && ${userCmd}` : `${sourceCmd} && exec bash`;
    return `${setupPart}${sandbox} bash -c '${shellEscapeForBashC(inner)}'`;
  }

  const ensureBashFunctions = `${ensureBashSetup}; ${sourceCmd}`;
  return userCmd
    ? `${envPrefix}${ensureBashFunctions} && ${userCmd}`
    : `${envPrefix}${ensureBashFunctions} && exec bash`;
}

function buildRemoteCommand(
  options: TermConnectOptions,
  connectionDetails?: ConnectionDetails,
  remoteRenetPath?: string
): string | undefined {
  const envPrefix = buildEnvPrefix(connectionDetails);
  const sandboxOpts = buildTermSandboxOptions(connectionDetails);
  const sandbox =
    sandboxOpts && remoteRenetPath ? buildSandboxPrefix(sandboxOpts, remoteRenetPath) : '';

  if (options.container) {
    return buildContainerCommand(options, envPrefix, sandbox);
  }

  return buildShellCommand(options, envPrefix, sandbox);
}

async function validateAndGetConnectionDetails(opts: {
  team?: string;
  machine?: string;
  repository?: string;
}) {
  const provider = await getStateProvider();
  if (provider.isCloud && !opts.team) {
    throw new Error(t('errors.teamRequired'));
  }
  if (!opts.machine) {
    throw new Error(t('errors.machineRequired'));
  }

  const teamName = opts.team ?? '';
  const connectionDetails = await withSpinner(t('commands.term.fetchingDetails'), () =>
    getSSHConnectionDetails(teamName, opts.machine!, opts.repository)
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
    teamName,
    machineName: opts.machine,
    repositoryName: opts.repository,
  };
}

/**
 * Connects to a machine or repository via SSH
 */
async function enforceTermPolicy(opts: TermConnectOptions): Promise<void> {
  if (opts.command && !opts.repository) {
    const match = detectRepoContextCommand(opts.command);
    if (match) {
      throw new ValidationError(
        t('errors.term.repoContextRequired', {
          detected: match.label,
          machine: opts.machine ?? DEFAULTS.CLOUD.MACHINE_PLACEHOLDER,
          command: opts.command,
        })
      );
    }
  }

  if (opts.repository) {
    await assertCommandPolicy(CMD.TERM_REPO, opts.repository);
  } else {
    assertAgentMachineAccess(opts.machine ?? DEFAULTS.CLOUD.MACHINE_PLACEHOLDER);
  }
}

function shouldUseExternalTerminal(options: TermConnectOptions): boolean {
  const isTTY = process.stdin.isTTY && process.stdout.isTTY;
  const hasCommand = !!options.command || !!options.container;
  return hasCommand ? options.external === true : (options.external ?? !isTTY);
}

async function executeSSH(
  sshConnection: SSHConnection,
  destination: string,
  remoteCommand: string | undefined,
  title: string,
  connectionDetails: ConnectionDetails,
  useExternal: boolean
): Promise<void> {
  if (!useExternal) {
    await runInlineSSH(sshConnection, destination, remoteCommand, title, connectionDetails);
    return;
  }

  try {
    await launchExternalTerminal(
      sshConnection,
      destination,
      remoteCommand,
      title,
      connectionDetails
    );
  } catch (error) {
    debugLog(
      `External terminal failed: ${error instanceof Error ? error.message : String(error)}, falling back to inline SSH`
    );
    await runInlineSSH(sshConnection, destination, remoteCommand, title, connectionDetails);
  }
}

async function connectTerminal(options: TermConnectOptions): Promise<void> {
  const opts = await configService.applyDefaults(options);
  await enforceTermPolicy(opts);

  const { connectionDetails, teamName, machineName, repositoryName } =
    await validateAndGetConnectionDetails(opts);
  const localConfig = await configService.getLocalConfig();
  const machine = localConfig.machines[machineName];
  if (!machine) {
    throw new Error(`Machine "${machineName}" not found in local config`);
  }
  const sshPrivateKey =
    localConfig.sshPrivateKey ?? (await readSSHKey(localConfig.ssh.privateKeyPath));
  const remoteRenetPath = await provisionRenetToRemote(localConfig, machine, sshPrivateKey, {});

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
    const remoteCommand = buildRemoteCommand(options, connectionDetails, remoteRenetPath);

    await executeSSH(
      sshConnection,
      destination,
      remoteCommand,
      title,
      connectionDetails,
      shouldUseExternalTerminal(options)
    );
  } finally {
    await sshConnection.cleanup();
  }
}

async function launchExternalTerminal(
  sshConnection: SSHConnection,
  destination: string,
  remoteCommand: string | undefined,
  title: string,
  connectionDetails: ConnectionDetails
): Promise<void> {
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

  // Wait briefly for async spawn errors (e.g. ENOENT when terminal binary is missing)
  if (result.process) {
    await new Promise<void>((resolve, reject) => {
      const timer = setTimeout(resolve, 500);
      result.process!.once('error', (err: Error) => {
        clearTimeout(timer);
        reject(new Error(t('errors.term.launchFailed', { error: err.message })));
      });
    });
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

  term.addHelpText(
    'after',
    `
${t('help.examples')}
  $ rdc term server-1                  ${t('help.term.machine')}
  $ rdc term server-1 my-app           ${t('help.term.repo')}
  $ rdc term server-1 -c "uptime"      ${t('help.term.command')}
`
  );

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
        if (provider.isCloud) {
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
          if (provider.isCloud) {
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
