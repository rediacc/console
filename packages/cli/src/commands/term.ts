import { Command } from 'commander';
import { t } from '../i18n/index.js';
import { generateSetupCommand, generateSourceCommand } from '../remote/repository/index.js';
import { SSHConnection, spawnSSH, testSSHConnectivity } from '../remote/ssh/index.js';
import { getDefaultTerminalType, launchTerminal } from '../remote/terminal/index.js';
import { applyClusterConnectionContext } from '../services/cluster/cluster-target.js';
import { configService } from '../services/config/config-resources.js';
import { auditService } from '../services/core/audit.js';
import { outputService } from '../services/core/output.js';
import {
  type ConnectionDetails,
  getSSHConnectionDetails,
} from '../services/machine/ssh-connection.js';
import { provisionRenetToRemote, readSSHKey } from '../services/renet/renet-execution.js';
import { deployRepoKeyIfNeeded } from '../services/repo/repo-key-deployment.js';
import { assertRepoMountedOnMachine } from '../services/repo/repo-mount-check.js';
import {
  assertAgentMachineAccess,
  isAgentEnvironment,
  isLegitimateWildcardOverride,
} from '../utils/agent-guard.js';
import { assertCommandPolicy, CMD } from '../utils/command-policy.js';
import { debugLog } from '../utils/debug.js';
import { handleError, ValidationError } from '../utils/errors.js';
import {
  detectDirectRenetCommand,
  detectDockerComposeCommand,
  detectFileWriteCommand,
  detectRepoContextCommand,
} from '../utils/repo-context-guard.js';
import { type ConnectTarget, resolveConnectTarget } from '../utils/repo-target.js';
import { withSpinner } from '../utils/spinner.js';

/**
 * `term connect <target>` (spec/03 §5.8). The target is a place (machine shell)
 * or a repo ref (repo shell); everything else the command needs is derived from
 * it. The container side door (`--container`, `--container-action`,
 * `--log-lines`, `--follow`) is retired in favour of `repo logs` / `repo exec`,
 * and `-t/--team` is dead vocabulary.
 */
export interface TermConnectOptions {
  /** Run one command instead of an interactive shell; the exit code passes through. */
  command?: string;
  /** Force an external terminal window. */
  external?: boolean;
  /** Clear the per-repo home overlay for a fresh start. */
  resetHome?: boolean;
}

export function buildEnvPrefix(connectionDetails?: ConnectionDetails): string {
  const parts: string[] = [];

  if (connectionDetails?.environment) {
    for (const [key, value] of Object.entries(connectionDetails.environment)) {
      const escaped = String(value).replaceAll("'", "'\\''");
      parts.push(`export ${key}='${escaped}'`);
    }
  }

  // Pin the kubectl current-context to the repo's namespace for a cluster-placed
  // repo session (the k8s analog of the repo `cd` below). KUBECONFIG is already
  // exported by the loop, so this runs against the cluster's kubeconfig; the
  // `|| true` keeps a shell open even if kubectl is momentarily unavailable.
  if (connectionDetails?.kubeNamespace) {
    const ns = connectionDetails.kubeNamespace.replaceAll("'", "'\\''");
    parts.push(`kubectl config set-context --current --namespace='${ns}' >/dev/null 2>&1 || true`);
  }

  if (connectionDetails?.workingDirectory) {
    parts.push(`cd '${connectionDetails.workingDirectory}' 2>/dev/null`);
  }

  return parts.length > 0 ? `${parts.join('; ')}; ` : '';
}

// Sandbox is enforced server-side via ForceCommand in authorized_keys.
// The CLI just sends the raw command — sandbox-gateway on the remote
// reads REDIACC_REPOSITORY from env and applies Landlock + OverlayFS.

function buildRemoteCommand(
  options: TermConnectOptions,
  connectionDetails: ConnectionDetails
): string {
  const envPrefix = buildEnvPrefix(connectionDetails);
  const ensureBashSetup = generateSetupCommand();
  const sourceCmd = generateSourceCommand();
  const userCmd = options.command;

  // --rcfile sources ~/.bashrc first, then our functions, so PS1 isn't overridden
  const rcfile = `--rcfile <(echo "source ~/.bashrc 2>/dev/null; ${sourceCmd}")`;

  if (userCmd) {
    return `${envPrefix}${ensureBashSetup}; ${sourceCmd} && ${userCmd}`;
  }
  return `${envPrefix}${ensureBashSetup}; exec bash ${rcfile}`;
}

async function validateAndGetConnectionDetails(opts: {
  machine: string;
  repository?: string;
  quiet?: boolean;
}): Promise<ConnectionDetails> {
  const connectionDetails = opts.quiet
    ? await getSSHConnectionDetails('', opts.machine, opts.repository)
    : await withSpinner(t('commands.term.fetchingDetails'), () =>
        getSSHConnectionDetails('', opts.machine, opts.repository)
      );

  const connectivityResult = opts.quiet
    ? await testSSHConnectivity(connectionDetails.host, connectionDetails.port, 10000)
    : await withSpinner(
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

  return connectionDetails;
}

function enforceDirectRenetGuard(command: string): void {
  const match = detectDirectRenetCommand(command);
  if (!match) return;
  if (isAgentEnvironment() && !isLegitimateWildcardOverride()) {
    throw new ValidationError(
      `Direct "${match.renetCommand}" is not allowed in agent mode.\n\nRun "${match.cliHelpCommand}" to see available CLI commands.`
    );
  }
  process.stderr.write(
    `\x1b[33mWarning:\x1b[0m Running "${match.renetCommand}" directly bypasses CLI orchestration.\nRun "${match.cliHelpCommand}" to see available CLI commands.\n`
  );
}

function enforceFileWriteGuard(command: string): void {
  const match = detectFileWriteCommand(command);
  if (!match) return;
  if (isAgentEnvironment()) {
    throw new ValidationError(t('errors.term.fileWriteDetected', { detected: match.label }));
  }
  process.stderr.write(
    `\x1b[33mHint:\x1b[0m Detected file write pattern (${match.label}). ` +
      `For file transfer, consider: rdc repo sync upload <ref> --local FILE --remote PATH\n`
  );
}

/**
 * The gate (spec §4.7): the repo form is class B (grandGuard on the addressed
 * repo), the machine form is class A plus the agent machine-access check. A
 * cluster-placed repo is now a repo like any other, because the target resolver
 * derives it from config; the retired `--cluster -r <namespace>` form could not
 * be repo-gated, since its `-r` was a bare namespace string.
 */
async function enforceTermPolicy(
  options: TermConnectOptions,
  target: ConnectTarget
): Promise<void> {
  if (options.command && detectDockerComposeCommand(options.command)) {
    throw new ValidationError(t('errors.term.dockerComposeForbidden'));
  }

  if (options.command && target.kind === 'place') {
    const match = detectRepoContextCommand(options.command);
    if (match) {
      throw new ValidationError(
        t('errors.term.repoContextRequired', {
          detected: match.label,
          machine: target.machineName,
          command: options.command,
        })
      );
    }
  }

  if (options.command) {
    enforceDirectRenetGuard(options.command);
    enforceFileWriteGuard(options.command);
  }

  if (target.kind === 'repo') {
    // Gate B on the repo arm only; the place arm below is a machine shell (class A).
    await assertCommandPolicy(CMD.TERM_CONNECT, target.repoKey);
  } else {
    assertAgentMachineAccess(target.machineName);
  }
}

function shouldUseExternalTerminal(options: TermConnectOptions): boolean {
  const isTTY = process.stdin.isTTY && process.stdout.isTTY;
  return options.command ? options.external === true : (options.external ?? !isTTY);
}

async function executeSSH(
  sshConnection: SSHConnection,
  destination: string,
  remoteCommand: string | undefined,
  title: string,
  connectionDetails: ConnectionDetails,
  useExternal: boolean,
  quiet: boolean
): Promise<void> {
  if (!useExternal) {
    await runInlineSSH(sshConnection, destination, remoteCommand, title, connectionDetails, quiet);
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
    await runInlineSSH(sshConnection, destination, remoteCommand, title, connectionDetails, quiet);
  }
}

// Determines client-side output suppression and remote-TTY allocation for a
// connectTerminal invocation.
//
// - quietOutput: skip the spinners and the "Connecting to..." stderr line so
//   `term connect <target> -c "..."` keeps stdout clean for the command's own
//   output.
// - noTTY: disable ssh -tt. The remote sandbox banner is gated by `[ -t 1 ]`,
//   and ssh prints "Connection to HOST closed." only when -t allocated a PTY,
//   so a one-shot command must not allocate one. The container side door was
//   the only case that needed a PTY for a `-c` invocation (docker exec -it);
//   it is retired, so one-shot and no-TTY now coincide exactly.
export function resolveTermOutputMode(opts: TermConnectOptions): {
  quietOutput: boolean;
  noTTY: boolean;
} {
  const oneShot = !!opts.command;
  return { quietOutput: oneShot, noTTY: oneShot };
}

/**
 * Split a resolved target into the two roles the connection layer keeps apart:
 * a docker repo (mount check, per-repo key, DOCKER_HOST + working dir) and a
 * kubernetes namespace (KUBECONFIG + a kubectl context pin). A repo has exactly
 * one of them, decided by whether its datastore lives in a cluster.
 */
function splitTargetRoles(target: ConnectTarget): {
  dockerRepo?: string;
  kubeNamespace?: string;
  sessionScope?: string;
} {
  if (target.kind !== 'repo') return {};
  return {
    ...(target.kubeCluster === undefined && { dockerRepo: target.repoKey }),
    ...(target.kubeCluster !== undefined && { kubeNamespace: target.repoKey }),
    sessionScope: target.repoKey,
  };
}

async function connectTerminal(targetRef: string, options: TermConnectOptions): Promise<void> {
  const startTime = Date.now();

  const target = await resolveConnectTarget(targetRef, { readOnly: true });
  await enforceTermPolicy(options, target);

  const { dockerRepo, kubeNamespace, sessionScope } = splitTargetRoles(target);
  const { quietOutput, noTTY } = resolveTermOutputMode(options);
  const machineName = target.machineName;

  const connectionDetails = await validateAndGetConnectionDetails({
    machine: machineName,
    repository: dockerRepo,
    quiet: quietOutput,
  });

  if (target.kubeCluster) {
    applyClusterConnectionContext(connectionDetails, target.kubeCluster, kubeNamespace);
  }

  const localConfig = await configService.getLocalConfig();
  const machine = localConfig.machines[machineName];
  if (!machine) {
    throw new Error(`Machine "${machineName}" not found in local config`);
  }
  const sshPrivateKey =
    localConfig.sshPrivateKey ?? (await readSSHKey(localConfig.ssh.privateKeyPath));
  await provisionRenetToRemote(localConfig, machine, sshPrivateKey, {});

  if (dockerRepo) {
    const repoConfig = await configService.getRepository(dockerRepo);
    if (repoConfig) {
      await assertRepoMountedOnMachine(dockerRepo, repoConfig.repositoryGuid, machineName);
    }
    await deployRepoKeyIfNeeded(dockerRepo, machineName);
  }

  const sshConnection = new SSHConnection(
    connectionDetails.privateKey,
    connectionDetails.known_hosts,
    { port: connectionDetails.port, forceTTY: !noTTY }
  );

  let success = true;
  let error: string | undefined;
  try {
    await sshConnection.setup();

    // The label is the cluster for a k8s target and the machine otherwise; the
    // scope is the repo key, absent for a plain machine shell.
    const title = sessionScope
      ? `Rediacc - ${target.label}/${sessionScope}`
      : `Rediacc - ${target.label}`;

    const destination = `${connectionDetails.user}@${connectionDetails.host}`;
    const remoteCommand = buildRemoteCommand(options, connectionDetails);

    await executeSSH(
      sshConnection,
      destination,
      remoteCommand,
      title,
      connectionDetails,
      shouldUseExternalTerminal(options),
      quietOutput
    );
  } catch (err) {
    success = false;
    error = err instanceof Error ? err.message : String(err);
    throw err;
  } finally {
    await sshConnection.cleanup();
    auditService.recordOperation({
      functionName: 'term_connect',
      machineName,
      repoName: sessionScope,
      success,
      exitCode: success ? 0 : 1,
      durationMs: Date.now() - startTime,
      error,
    });
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

  outputService.info(t('commands.term.launchingTerminal', { type: terminalType }));

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

  outputService.info(t('commands.term.launchSuccess'));
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
  connectionDetails: ConnectionDetails,
  quiet: boolean
): Promise<void> {
  if (!quiet) {
    // Progress message on stderr — keeps stdout reserved for command output
    // when -c piping is in play, matching the Unix convention used by ssh's
    // own progress / banner messages.
    process.stderr.write(`${t('commands.term.connectingTo', { title })}\n`);
  }

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
  const term = program
    .command('term')
    .summary(t('commands.term.descriptionShort'))
    .description(t('commands.term.description'));

  term.addHelpText(
    'after',
    `
${t('help.examples')}
  $ rdc term connect server-1                     ${t('help.term.machine')}
  $ rdc term connect my-app                       ${t('help.term.repo')}
  $ rdc term connect my-app:test                  ${t('help.term.fork')}
  $ rdc term connect server-1 -c "uptime"         ${t('help.term.command')}
  $ rdc term connect prod                         ${t('help.term.cluster')}

  ${t('help.term.collisionHint')}
  ${t('help.term.syncHint')}
`
  );

  term
    .command('connect')
    .description(t('commands.term.connect.description'))
    .argument('<target>', t('options.connectTarget'))
    .option('-c, --command <cmd>', t('options.command'))
    .option('--external', t('options.external'))
    .option('--reset-home', t('options.resetHome'))
    .action(async (target: string, options: TermConnectOptions) => {
      try {
        await connectTerminal(target, options);
      } catch (error) {
        handleError(error);
      }
    });
}
