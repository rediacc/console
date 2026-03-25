import type {
  ContainerInfo,
  ListResult,
} from '@rediacc/shared/queue-vault/data/list-types.generated';
import { getContainers } from '@rediacc/shared/queue-vault/data/list-types.generated';
import { SSHConnection, spawnSSH, testSSHConnectivity } from '@rediacc/shared-desktop/ssh';
import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { getStateProvider } from '../providers/index.js';
import { authService } from '../services/auth.js';
import { configService } from '../services/config-resources.js';
import { fetchMachineStatus } from '../services/machine-status.js';
import { provisionRenetToRemote, readSSHKey } from '../services/renet-execution.js';
import { deployRepoKeyIfNeeded } from '../services/repo-key-deployment.js';
import { getSSHConnectionDetails } from '../services/ssh-connection.js';
import { assertCommandPolicy, CMD } from '../utils/command-policy.js';
import { handleError } from '../utils/errors.js';
import { createGuidResolver, loadGuidMap } from '../utils/guid-resolver.js';
import { withSpinner } from '../utils/spinner.js';

interface TunnelOptions {
  team?: string;
  machine?: string;
  repository?: string;
  container?: string;
  port?: string;
  local?: string;
  [key: string]: unknown;
}

interface TunnelTarget {
  containerName: string;
  remoteIP: string;
  remotePort: number;
  localPort: number;
}

/**
 * Filter running containers belonging to the target repository.
 */
function filterRepoContainers(
  listResult: ListResult,
  repoName: string,
  guidMap: Record<string, string>,
  repoGuidOverride: string | undefined
): ContainerInfo[] {
  const allContainers = getContainers(listResult);
  const resolve = createGuidResolver(guidMap);

  // Build reverse map: friendly name → GUID
  const nameToGuid = new Map<string, string>();
  for (const [guid, name] of Object.entries(guidMap)) {
    const friendly = name.endsWith(':latest') ? name.slice(0, -7) : name;
    nameToGuid.set(friendly, guid);
    nameToGuid.set(guid, guid); // allow direct GUID lookup
  }
  const repoGuid = repoGuidOverride ?? nameToGuid.get(repoName);

  // The container's "repository" field may be a GUID, a resolved name, or
  // a name with duplicated tag (e.g. "repo:tag:tag" from renet fork labeling).
  return allContainers.filter((c) => {
    const repo = c.repository;
    const resolvedName = resolve(repo);
    return (
      (resolvedName === repoName ||
        repo === repoGuid ||
        repo === repoName ||
        repo.startsWith(`${repoName}:`)) &&
      c.state === 'running'
    );
  });
}

/**
 * Select a single container from the list by name, or auto-select if only one.
 */
function selectContainer(
  repoContainers: ContainerInfo[],
  repoName: string,
  containerName?: string
): ContainerInfo {
  if (containerName) {
    const found = repoContainers.find((c) => c.name === containerName);
    if (!found) {
      throw new Error(
        t('commands.repo.tunnel.containerNotFound', {
          name: containerName,
          repository: repoName,
        })
      );
    }
    return found;
  }
  if (repoContainers.length === 1) {
    return repoContainers[0];
  }
  const list = repoContainers.map((c) => `  - ${c.name}`).join('\n');
  throw new Error(t('commands.repo.tunnel.multipleContainers', { list }));
}

/**
 * Resolve the remote port from labels, exposed ports, or explicit option.
 */
function resolvePort(container: ContainerInfo, portOption?: string): number {
  if (portOption) {
    return Number.parseInt(portOption, 10);
  }
  const servicePort = container.labels?.['rediacc.service_port'];
  if (servicePort) {
    return Number.parseInt(servicePort, 10);
  }
  const exposedPorts = container.exposed_ports ?? [];
  if (exposedPorts.length === 1) {
    return Number.parseInt(exposedPorts[0].port, 10);
  }
  if (exposedPorts.length === 0) {
    throw new Error(t('commands.repo.tunnel.noPorts', { container: container.name }));
  }
  const list = exposedPorts.map((p) => `  - ${p.port}/${p.protocol}`).join('\n');
  throw new Error(t('commands.repo.tunnel.multiplePorts', { container: container.name, list }));
}

/**
 * Resolve which container and port to tunnel to.
 * Auto-detects container (if only one running) and port (if only one exposed).
 */
function resolveContainerTarget(
  listResult: ListResult,
  repoName: string,
  guidMap: Record<string, string>,
  repoGuidOverride: string | undefined,
  options: { container?: string; port?: string; local?: string }
): TunnelTarget {
  const repoContainers = filterRepoContainers(listResult, repoName, guidMap, repoGuidOverride);
  if (repoContainers.length === 0) {
    throw new Error(t('commands.repo.tunnel.noContainers', { repository: repoName }));
  }

  const container = selectContainer(repoContainers, repoName, options.container);

  const remoteIP = container.labels?.['rediacc.service_ip'];
  if (!remoteIP) {
    throw new Error(t('commands.repo.tunnel.noServiceIP', { container: container.name }));
  }

  const remotePort = resolvePort(container, options.port);
  const localPort = options.local ? Number.parseInt(options.local, 10) : remotePort;

  return { containerName: container.name, remoteIP, remotePort, localPort };
}

async function tunnelConnect(options: TunnelOptions): Promise<void> {
  const opts = await configService.applyDefaults(options);

  if (!opts.machine) {
    throw new Error(t('errors.machineRequired'));
  }
  if (!opts.repository) {
    throw new Error(t('errors.repositoryNotFound', { name: '' }));
  }

  const provider = await getStateProvider();
  if (provider.isCloud && !opts.team) {
    throw new Error(t('errors.teamRequired'));
  }

  await assertCommandPolicy(CMD.REPO_TUNNEL, opts.repository);

  const machineName = opts.machine;
  const repoName = opts.repository;
  const teamName = opts.team ?? '';

  // Fetch container info from remote machine
  const listResult = await withSpinner(
    t('commands.repo.tunnel.fetching', { machine: machineName }),
    () => fetchMachineStatus(machineName, { sections: ['containers'] })
  );

  // Resolve repo name → GUID (configService handles fork name:tag correctly)
  const guidMap = await loadGuidMap();
  const repoConfig = await configService.getRepository(repoName);
  const repoGuidOverride = repoConfig?.repositoryGuid;

  // Find the target container, IP, and port
  const target = resolveContainerTarget(listResult, repoName, guidMap, repoGuidOverride, {
    container: opts.container,
    port: opts.port,
    local: opts.local,
  });

  // Get SSH connection details
  const connectionDetails = await withSpinner(t('commands.term.fetchingDetails'), () =>
    getSSHConnectionDetails(teamName, machineName, repoName)
  );

  // Verify SSH connectivity
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

  // Provision renet and deploy repo key
  const localConfig = await configService.getLocalConfig();
  const machine = localConfig.machines[machineName];
  if (!machine) {
    throw new Error(`Machine "${machineName}" not found in local config`);
  }
  const sshPrivateKey =
    localConfig.sshPrivateKey ?? (await readSSHKey(localConfig.ssh.privateKeyPath));
  await provisionRenetToRemote(localConfig, machine, sshPrivateKey, {});
  await deployRepoKeyIfNeeded(repoName, machineName);

  // Set up SSH connection
  const sshConnection = new SSHConnection(
    connectionDetails.privateKey,
    connectionDetails.known_hosts,
    {
      port: connectionDetails.port,
      forceTTY: false,
    }
  );

  try {
    await sshConnection.setup();

    const destination = `${connectionDetails.user}@${connectionDetails.host}`;
    const forwardSpec = `${target.localPort}:${target.remoteIP}:${target.remotePort}`;

    // Spawn SSH with -N (no remote command) and -L (local forward)
    const child = spawnSSH(
      destination,
      [...sshConnection.sshOptions, '-N', '-L', forwardSpec],
      undefined,
      {
        env: { ...process.env, ...connectionDetails.environment },
        stdio: 'inherit',
        agentSocketPath: sshConnection.agentSocketPath,
      }
    );

    // eslint-disable-next-line no-console
    console.log(
      t('commands.repo.tunnel.active', {
        localPort: String(target.localPort),
        container: target.containerName,
        remoteIP: target.remoteIP,
        remotePort: String(target.remotePort),
      })
    );
    // eslint-disable-next-line no-console
    console.log(t('commands.repo.tunnel.hint'));

    // Graceful shutdown on SIGINT/SIGTERM
    const cleanup = () => {
      child.kill('SIGTERM');
    };
    process.on('SIGINT', cleanup);
    process.on('SIGTERM', cleanup);

    await new Promise<void>((resolve, reject) => {
      child.on('exit', (code: number | null) => {
        process.removeListener('SIGINT', cleanup);
        process.removeListener('SIGTERM', cleanup);
        // Exit code 130 = SIGINT (128+2), treat as normal
        if (code === 0 || code === null || code === 130) {
          resolve();
        } else {
          reject(new Error(t('errors.term.sshExitCode', { code })));
        }
      });
      child.on('error', reject);
    });

    // eslint-disable-next-line no-console
    console.log(t('commands.repo.tunnel.closed'));
  } finally {
    await sshConnection.cleanup();
  }
}

export function registerRepoTunnelCommand(repoCommand: Command): void {
  const tunnel = repoCommand
    .command('tunnel')
    .summary(t('commands.repo.tunnel.descriptionShort'))
    .description(t('commands.repo.tunnel.description'));

  tunnel.addHelpText(
    'after',
    `
${t('help.examples')}
  $ rdc repo tunnel hostinger sonarqube -c sonarqube-database --port 5432
  $ rdc repo tunnel hostinger sonarqube                    # auto-detect container & port
  $ rdc repo tunnel -m hostinger -r sonarqube --port 5432 --local 15432
`
  );

  // Shorthand: rdc repo tunnel <machine> <repo>
  tunnel
    .argument('[machine]', t('options.machineShorthand'))
    .argument('[repository]', t('options.repositoryShorthand'))
    .option('-c, --container <name>', t('commands.repo.tunnel.containerOption'))
    .option('--port <port>', t('commands.repo.tunnel.portOption'))
    .option('--local <port>', t('commands.repo.tunnel.localOption'))
    .action(
      async (
        machine: string | undefined,
        repository: string | undefined,
        options: TunnelOptions,
        cmd: Command
      ) => {
        try {
          const resolvedMachine = machine ?? options.machine;
          if (!resolvedMachine) {
            cmd.help();
            return;
          }
          const provider = await getStateProvider();
          if (provider.isCloud) {
            await authService.requireAuth();
          }
          await tunnelConnect({
            ...options,
            machine: resolvedMachine,
            repository: repository ?? options.repository,
          });
        } catch (error) {
          handleError(error);
        }
      }
    );
}
