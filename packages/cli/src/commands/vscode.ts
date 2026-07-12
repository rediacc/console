/**
 * VS Code Remote SSH CLI Command
 * Opens VS Code with Remote SSH connection to machines and repositories
 */

import { Command } from 'commander';
import { t } from '../i18n/index.js';
import { SSHConnection, spawnSSH } from '../remote/ssh/index.js';
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
  removePersistedKeys,
  removeSSHConfigEntry,
  setHostRemotePlatform,
  setHostServerInstallPath,
} from '../remote/vscode/index.js';
import { applyClusterConnectionContext } from '../services/cluster/cluster-target.js';
import { configService } from '../services/config/config-resources.js';
import {
  type ConnectionDetails,
  getSSHConnectionDetails,
} from '../services/machine/ssh-connection.js';
import { provisionRenetToRemote, readSSHKey } from '../services/renet/renet-execution.js';
import { deployRepoKeyIfNeeded } from '../services/repo/repo-key-deployment.js';
import { assertRepoMountedOnMachine } from '../services/repo/repo-mount-check.js';
import { assertAgentMachineAccess } from '../utils/agent-guard.js';
import { assertCommandPolicy, CMD } from '../utils/command-policy.js';
import { debugLog } from '../utils/debug.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { resolveRepoTarget } from '../utils/repo-target.js';
import { withSpinner } from '../utils/spinner.js';
import { connectVSCodeBrowser, verifySSHConnectivity } from './vscode-browser.js';
import { registerVSCodeServeCommands } from './vscode-serve.js';
import {
  displayActiveConnections,
  displayConfigurationStatus,
  displayVSCodeInstallation,
} from './vscode-utils.js';

interface VSCodeConnectOptions {
  team?: string;
  machine?: string;
  cluster?: string;
  repository?: string;
  folder?: string;
  urlOnly?: boolean;
  newWindow?: boolean;
  skipEnvSetup?: boolean;
  insiders?: boolean;
  browser?: boolean;
  open?: boolean;
  local?: string;
  serverProvider?: string;
  serverArchive?: string;
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
      workingDirectory: connectionDetails.workingDirectory,
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
  insidersOption?: boolean,
  repositoryName?: string
): Promise<void> {
  await withSpinner(t('commands.vscode.connect.configuringVSCode'), () => {
    const isInsiders = insidersOption ?? vscodeInfo.isInsiders;
    const result = configureVSCodeSettings(isInsiders);

    if (!result.success) {
      console.warn(t('commands.vscode.connect.settingsWarning', { error: result.error }));
    }

    if (connectionDetails.datastore) {
      // Per-repo server install path so VS Code runs separate server instances.
      // VS Code shares servers by resolved hostname — without separate paths,
      // the second repo would reuse the first repo's sandboxed server.
      // Uses the GUID-based mount path (colon-free) because VS Code rejects
      // serverInstallPath values containing ':' (parsed as PATH-style separator),
      // which breaks fork aliases like "<parent>:<tag>".
      const serverPath =
        repositoryName && connectionDetails.repositoryGuid
          ? `${connectionDetails.datastore}/mounts/${connectionDetails.repositoryGuid}`
          : connectionDetails.datastore;
      setHostServerInstallPath(connectionName, serverPath, isInsiders);
    }

    setHostRemotePlatform(connectionName, isInsiders);
    return Promise.resolve();
  });
}

async function provisionAndPrepare(
  machineName: string,
  repositoryName: string | undefined,
  connectionDetails: ConnectionDetails,
  kubeNamespace?: string
): Promise<void> {
  const localConfig = await configService.getLocalConfig();
  const machine = localConfig.machines[machineName];
  const teamKey = localConfig.sshPrivateKey ?? (await readSSHKey(localConfig.ssh.privateKeyPath));

  if (machine) {
    await withSpinner(t('commands.vscode.connect.provisioningRenet'), () =>
      provisionRenetToRemote(localConfig, machine, teamKey, {})
    );
  }

  if (repositoryName && connectionDetails.datastore && connectionDetails.repositoryGuid) {
    await preparePerRepoVSCodeServer(connectionDetails, teamKey);
  }

  // Pin the kubectl current-context to the repo's namespace on the control node
  // so the integrated terminal lands in the right namespace (design D14, the
  // k8s analog of the per-repo working directory for docker targets).
  if (kubeNamespace) {
    await pinClusterNamespace(connectionDetails, kubeNamespace);
  }
}

/**
 * Prepares a per-repo VS Code server directory on the remote machine.
 * Copies the shared server installation (if available) and sets ownership
 * to the universal user so the sandboxed VS Code server can write to it.
 */
async function preparePerRepoVSCodeServer(
  connectionDetails: ConnectionDetails,
  teamKey: string
): Promise<void> {
  const sandboxServerPath = `${connectionDetails.datastore}/mounts/${connectionDetails.repositoryGuid}/.vscode-server`;
  const sharedServerPath = `${connectionDetails.datastore}/.vscode-server`;
  const sshConn = new SSHConnection(teamKey, connectionDetails.known_hosts, {
    port: connectionDetails.port,
  });

  try {
    await sshConn.setup();
    const dest = `${connectionDetails.user}@${connectionDetails.host}`;
    const universalUser = connectionDetails.universalUser;
    const cmd = [
      `sudo mkdir -p "${sandboxServerPath}"`,
      `sudo cp -a "${sharedServerPath}/." "${sandboxServerPath}/" 2>/dev/null || true`,
      `sudo chown -R ${universalUser}:${universalUser} "${sandboxServerPath}"`,
    ].join(' && ');

    const child = spawnSSH(dest, sshConn.sshOptions, cmd, {
      env: process.env,
      stdio: 'pipe',
      agentSocketPath: sshConn.agentSocketPath,
    });

    await new Promise<void>((resolve) => {
      child.on('exit', () => resolve());
      child.on('error', () => resolve());
    });
  } finally {
    await sshConn.cleanup();
  }
}

/**
 * Pins the kubectl current-context to a namespace on the cluster's control node
 * for a `vscode connect --cluster -r <repo>` session (design D14). The
 * KUBECONFIG path travels from connectionDetails.environment (set by
 * applyClusterConnectionContext). Best-effort: a failure must not abort the VS
 * Code launch, so errors are swallowed after a debug note.
 */
async function pinClusterNamespace(
  connectionDetails: ConnectionDetails,
  namespace: string
): Promise<void> {
  const kubeconfig = connectionDetails.environment?.KUBECONFIG;
  if (!kubeconfig) return;

  const sshConn = new SSHConnection(connectionDetails.privateKey, connectionDetails.known_hosts, {
    port: connectionDetails.port,
  });
  const ns = namespace.replaceAll("'", "'\\''");
  const kc = kubeconfig.replaceAll("'", "'\\''");
  const cmd = `KUBECONFIG='${kc}' kubectl config set-context --current --namespace='${ns}' >/dev/null 2>&1 || true`;

  try {
    await sshConn.setup();
    const dest = `${connectionDetails.user}@${connectionDetails.host}`;
    const child = spawnSSH(dest, sshConn.sshOptions, cmd, {
      env: process.env,
      stdio: 'pipe',
      agentSocketPath: sshConn.agentSocketPath,
    });

    await new Promise<void>((resolve) => {
      child.on('exit', () => resolve());
      child.on('error', () => resolve());
    });
  } catch (error) {
    debugLog(
      `Kube namespace pin skipped: ${error instanceof Error ? error.message : String(error)}`
    );
  } finally {
    await sshConn.cleanup();
  }
}

async function setupRemoteEnvironment(
  connectionDetails: ConnectionDetails,
  repositoryName?: string
): Promise<void> {
  const sshConnection = new SSHConnection(
    connectionDetails.privateKey,
    connectionDetails.known_hosts,
    { port: connectionDetails.port }
  );

  const serverInstallPath =
    repositoryName && connectionDetails.repositoryGuid
      ? `${connectionDetails.datastore}/mounts/${connectionDetails.repositoryGuid}`
      : connectionDetails.datastore;

  try {
    await sshConnection.setup();

    await withSpinner(t('commands.vscode.connect.settingUpEnv'), async () => {
      // For per-repo connections, sandbox-gateway already runs as universalUser
      // (via --run-as). Telling ensureVSCodeEnvSetup that sshUser == universalUser
      // skips the sudo wrapper that would fail inside the Landlock sandbox.
      const effectiveSshUser = repositoryName
        ? connectionDetails.universalUser
        : connectionDetails.user;

      const setupResult = await ensureVSCodeEnvSetup({
        sshDestination: `${connectionDetails.user}@${connectionDetails.host}`,
        sshOptions: sshConnection.sshOptions,
        envVars: connectionDetails.environment ?? {},
        universalUser: connectionDetails.universalUser,
        sshUser: effectiveSshUser,
        serverInstallPath,
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
async function validateVSCodeOptions(options: VSCodeConnectOptions) {
  const opts = await configService.applyDefaults(options);

  // Resolve -m/--cluster to a concrete SSH target. A cluster resolves to its
  // control node; KUBECONFIG + a namespace pin are layered on downstream (D14).
  const { machineName, kubeCluster } = await resolveRepoTarget({
    machine: opts.machine,
    cluster: opts.cluster,
  });
  const isCluster = Boolean(kubeCluster);

  // `-r` is a docker repo for a machine target but a namespace for a cluster
  // target; keep the roles separate so docker-repo machinery (mount check, key
  // deploy, per-repo server) never runs against a k8s namespace.
  const repositoryName = isCluster ? undefined : opts.repository;
  const kubeNamespace = isCluster ? opts.repository : undefined;

  // The in-browser code-server path has no cluster wiring in v1; refuse rather
  // than open a machine-level browser session that ignores KUBECONFIG.
  if (isCluster && opts.browser) {
    throw new ValidationError(
      t('errors.cluster.featureUnsupportedV1', {
        feature: '--browser',
        hint: 'use the desktop VS Code flow (omit --browser)',
      })
    );
  }

  // Agent guard: enforce fork-only mode for docker-repo access; a cluster's `-r`
  // is a namespace, so gate on control-node access instead.
  if (repositoryName) {
    await assertCommandPolicy(CMD.VSCODE_REPO, repositoryName);
  } else {
    assertAgentMachineAccess(machineName);
  }

  return {
    teamName: opts.team ?? '',
    machineName,
    repositoryName,
    kubeCluster,
    kubeNamespace,
    opts,
  };
}

async function connectVSCode(options: VSCodeConnectOptions): Promise<void> {
  const { teamName, machineName, repositoryName, kubeCluster, kubeNamespace } =
    await validateVSCodeOptions(options);

  if (options.browser) {
    await connectVSCodeBrowser(options, { teamName, machineName, repositoryName });
    return;
  }

  const vscodeInfo = await detectVSCode();
  debugLog(`Found VS Code: ${vscodeInfo.path}${vscodeInfo.isInsiders ? ' (Insiders)' : ''}`);

  const hasRemoteSSH = await isRemoteSSHExtensionInstalled();
  if (!hasRemoteSSH) {
    console.warn(t('commands.vscode.connect.extensionWarning'));
  }

  const connectionDetails = await withSpinner(t('commands.vscode.connect.fetchingDetails'), () =>
    getSSHConnectionDetails(teamName, machineName, repositoryName)
  );

  // For a cluster target, layer KUBECONFIG onto the control-node connection so
  // the integrated terminal has kubectl ready (design D14). The namespace is
  // pinned on the control node in provisionAndPrepare below.
  if (kubeCluster) {
    applyClusterConnectionContext(connectionDetails, kubeCluster, kubeNamespace);
  }

  await verifySSHConnectivity(connectionDetails);

  // Deploy per-repo SSH public key to remote authorized_keys (uses team key)
  if (repositoryName) {
    const repoConfig = await configService.getRepository(repositoryName);
    if (repoConfig) {
      await assertRepoMountedOnMachine(repositoryName, repoConfig.repositoryGuid, machineName);
    }
    await deployRepoKeyIfNeeded(repositoryName, machineName);
  }

  // Provision renet, prepare the per-repo VS Code server, and (for a cluster
  // target) pin the kubectl namespace on the control node.
  await provisionAndPrepare(machineName, repositoryName, connectionDetails, kubeNamespace);

  const { connectionName, identityFile, knownHostsFile } = await setupSSHConfig(
    teamName,
    machineName,
    repositoryName,
    connectionDetails
  );

  debugLog(`Identity file: ${identityFile}`);
  debugLog(`Known hosts file: ${knownHostsFile}`);

  await configureVSCodeAndSettings(
    connectionName,
    connectionDetails,
    vscodeInfo,
    options.insiders,
    repositoryName
  );

  if (!options.skipEnvSetup && connectionDetails.environment) {
    await setupRemoteEnvironment(connectionDetails, repositoryName);
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
  const vscode = program
    .command('vscode')
    .summary(t('commands.vscode.descriptionShort'))
    .description(t('commands.vscode.description'));

  vscode.addHelpText(
    'after',
    `
${t('help.examples')}
  $ rdc vscode connect -m server-1              ${t('help.vscode.machine')}
  $ rdc vscode connect -m server-1 -r my-app    ${t('help.vscode.repo')}
  $ rdc vscode connect --cluster prod -r shop   ${t('help.vscode.cluster')}
`
  );

  // Connect subcommand
  vscode
    .command('connect')
    .description(t('commands.vscode.connect.description'))
    .option('-t, --team <name>', t('options.team'))
    .option('-m, --machine <name>', t('options.machine'))
    .option('--cluster <name>', t('commands.repo.clusterOption'))
    .option('-r, --repository <name>', t('options.repository'))
    .option('-f, --folder <path>', t('options.folder'))
    .option('--url-only', t('options.urlOnly'))
    .option('-n, --new-window', t('options.newWindow'))
    .option('--skip-env-setup', t('options.skipEnvSetup'))
    .option('--insiders', t('options.insiders'))
    .option('--browser', t('options.vscodeBrowser'))
    .option('--no-open', t('options.vscodeNoOpen'))
    .option('--local <port>', t('commands.repo.tunnel.localOption'))
    .option('--server-provider <id>', t('options.vscodeServerProvider'))
    .option('--server-archive <file>', t('options.vscodeServerArchive'))
    .action(async (options: VSCodeConnectOptions) => {
      try {
        await connectVSCode(options);
      } catch (error) {
        handleError(error);
      }
    });

  registerVSCodeServeCommands(vscode);

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
}
