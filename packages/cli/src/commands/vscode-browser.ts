/**
 * `vscode connect --browser` flow: serve a web VS Code from INSIDE the repo
 * sandbox and tunnel it to localhost. No local VS Code install needed.
 */

import { testSSHConnectivity } from '@rediacc/shared-desktop/ssh';
import {
  getServerProvider,
  type VSCodeServerProvider,
} from '@rediacc/shared-desktop/vscode-server';
import { t } from '../i18n/index.js';
import { outputService } from '../services/output.js';
import {
  findFreeLocalPort,
  openRepoTunnel,
  type TunnelHandle,
} from '../services/repo-ssh-tunnel.js';
import {
  detectServerPlatform,
  ensureServerInstalled,
  launchServer,
  type ServerLaunchResult,
  waitForHttpReady,
} from '../services/vscode-server-remote.js';
import { ValidationError } from '../types/errors.js';
import { openBrowser } from '../utils/open-browser.js';
import { configService } from '../services/config-resources.js';
import { provisionRenetToRemote, readSSHKey } from '../services/renet-execution.js';
import { deployRepoKeyIfNeeded } from '../services/repo-key-deployment.js';
import { assertRepoMountedOnMachine } from '../services/repo-mount-check.js';
import { type ConnectionDetails, getSSHConnectionDetails } from '../services/ssh-connection.js';
import { withSpinner } from '../utils/spinner.js';

export interface VSCodeBrowserOptions {
  urlOnly?: boolean;
  open?: boolean;
  local?: string;
  serverProvider?: string;
  serverArchive?: string;
}

export async function verifySSHConnectivity(connectionDetails: ConnectionDetails): Promise<void> {
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

/**
 * Resolve connection details and prepare the remote side: connectivity
 * check, mount check, per-repo key deployment, and renet provisioning.
 */
async function prepareBrowserConnection(
  teamName: string,
  machineName: string,
  repositoryName: string
): Promise<{ connectionDetails: ConnectionDetails; teamKey: string }> {
  const connectionDetails = await getSSHConnectionDetails(teamName, machineName, repositoryName);
  await verifySSHConnectivity(connectionDetails);

  const repoConfig = await configService.getRepository(repositoryName);
  if (repoConfig) {
    await assertRepoMountedOnMachine(repositoryName, repoConfig.repositoryGuid, machineName);
  }
  await deployRepoKeyIfNeeded(repositoryName, machineName);

  const localConfig = await configService.getLocalConfig();
  const machine = localConfig.machines[machineName];
  const teamKey = localConfig.sshPrivateKey ?? (await readSSHKey(localConfig.ssh.privateKeyPath));
  if (machine) {
    outputService.info(t('commands.vscode.connect.provisioningRenet'));
    await provisionRenetToRemote(localConfig, machine, teamKey, {});
  }

  return { connectionDetails, teamKey };
}

/**
 * Report the ready tunnel. `--url-only` contract (consumed by the tutorial
 * video pipeline): exactly one line — the tokenized URL — is written to
 * stdout; all progress goes to stderr.
 */
function reportBrowserTunnel(
  serverProvider: VSCodeServerProvider,
  launch: ServerLaunchResult,
  url: string,
  localPort: number,
  options: VSCodeBrowserOptions
): void {
  if (options.urlOnly) {
    // Single machine-readable line on stdout; hold the tunnel.
    outputService.print(url);
    return;
  }

  outputService.info(t('commands.vscode.connect.tunnelReady', { port: String(localPort) }));
  outputService.print(t('commands.vscode.connect.browserUrl', { url }));
  if (serverProvider.auth.kind === 'password-env' && launch.secret) {
    outputService.print(t('commands.vscode.connect.passwordNote', { password: launch.secret }));
  }
  if (options.open !== false) {
    outputService.info(t('commands.vscode.connect.openingBrowser'));
    openBrowser(url);
  }
  outputService.info(t('commands.repo.tunnel.hint'));
}

/** Hold the tunnel open until the ssh child exits; forward SIGINT/SIGTERM. */
async function holdTunnelOpen(tunnel: TunnelHandle): Promise<void> {
  const cleanup = () => {
    tunnel.child.kill('SIGTERM');
  };
  process.on('SIGINT', cleanup);
  process.on('SIGTERM', cleanup);
  try {
    await tunnel.waitUntilExit();
  } finally {
    process.removeListener('SIGINT', cleanup);
    process.removeListener('SIGTERM', cleanup);
  }
}

/**
 * Serve a web VS Code from inside the repo sandbox and tunnel it to
 * localhost. The process holds the tunnel until SIGINT/SIGTERM.
 */
export async function connectVSCodeBrowser(
  options: VSCodeBrowserOptions,
  parsed: { teamName: string; machineName: string; repositoryName?: string }
): Promise<void> {
  const { teamName, machineName, repositoryName } = parsed;
  if (!repositoryName) {
    throw new ValidationError(t('errors.vscode.browserNeedsRepo'));
  }

  const serverProvider = getServerProvider(options.serverProvider);
  const { connectionDetails, teamKey } = await prepareBrowserConnection(
    teamName,
    machineName,
    repositoryName
  );

  // Install the server release into the shared read-only path (idempotent).
  const platform = await detectServerPlatform(connectionDetails, teamKey);
  outputService.info(
    t('commands.vscode.connect.installingServer', {
      provider: serverProvider.id,
      version: serverProvider.version,
    })
  );
  await ensureServerInstalled(serverProvider, connectionDetails, teamKey, {
    platform,
    archive: options.serverArchive,
  });

  // Launch (or reuse) the server inside the sandbox over the repo key.
  outputService.info(t('commands.vscode.connect.startingServer', { provider: serverProvider.id }));
  const launch = await launchServer(serverProvider, connectionDetails, {
    repoName: repositoryName,
  });
  if (launch.reused) {
    outputService.info(t('commands.vscode.connect.serverReused'));
  }

  // Tunnel localhost -> in-sandbox server port over the repo gateway key.
  const localPort = options.local ? Number.parseInt(options.local, 10) : await findFreeLocalPort();
  const tunnel = await openRepoTunnel({
    connectionDetails,
    localPort,
    remoteIP: '127.0.0.1',
    remotePort: launch.remotePort,
  });

  try {
    const httpReady = await waitForHttpReady(serverProvider, localPort, 30000);
    if (!httpReady) {
      throw new ValidationError(
        t('errors.vscode.serverStartFailed', {
          provider: serverProvider.id,
          error: 'HTTP ready check timed out',
        })
      );
    }

    const url = serverProvider.buildUrl({
      base: `http://localhost:${localPort}`,
      folder: connectionDetails.workingDirectory ?? connectionDetails.datastore,
      token: serverProvider.auth.kind === 'url-token' ? launch.secret : undefined,
    });

    reportBrowserTunnel(serverProvider, launch, url, localPort, options);
    await holdTunnelOpen(tunnel);
    outputService.info(t('commands.repo.tunnel.closed'));
  } finally {
    await tunnel.close();
  }
}
