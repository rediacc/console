/**
 * Unified SSH connection details service.
 * Consolidates vault extraction and environment building for term, vscode, and sync commands.
 */

import { DEFAULTS, NETWORK_DEFAULTS } from '@rediacc/shared/config';
import { t } from '../i18n/index.js';
import { getStateProvider } from '../providers/index.js';
import { debugLog } from '../utils/debug.js';

export interface ConnectionDetails {
  host: string;
  user: string;
  port: number;
  privateKey: string;
  known_hosts: string;
  datastore: string;
  universalUser: string;
  environment?: Record<string, string>;
  workingDirectory?: string;
  repositoryPath?: string;
  networkId?: string;
}

interface BaseConnectionInfo {
  host: string;
  port: number;
  privateKey: string;
  knownHosts: string;
  datastore: string;
  universalUser: string;
  sshUser: string;
}

function extractBaseConnectionInfo(
  machineVault: Record<string, unknown>,
  teamVault: Record<string, unknown>,
  machineName: string,
  teamName: string
): BaseConnectionInfo {
  const host = (machineVault.ip ?? machineVault.host) as string | undefined;
  const port = (machineVault.port ?? DEFAULTS.SSH.PORT) as number;
  const privateKey = (teamVault.SSH_PRIVATE_KEY ?? teamVault.sshPrivateKey) as string | undefined;
  const knownHosts = (machineVault.known_hosts ?? '') as string;
  const datastore = (machineVault.datastore ?? NETWORK_DEFAULTS.DATASTORE_PATH) as string;
  const universalUser = (machineVault.universalUser ??
    DEFAULTS.REPOSITORY.UNIVERSAL_USER) as string;
  const sshUser = (machineVault.user ?? universalUser) as string;

  if (!host) {
    throw new Error(t('errors.ssh.noIpAddress', { machine: machineName }));
  }
  if (!privateKey) {
    throw new Error(t('errors.ssh.noPrivateKey', { team: teamName }));
  }
  if (!knownHosts) {
    throw new Error(t('errors.ssh.noHostKey', { machine: machineName }));
  }

  return { host, port, privateKey, knownHosts, datastore, universalUser, sshUser };
}

function buildRepositoryEnvFromVault(
  teamName: string,
  machineName: string,
  repositoryName: string,
  machineVault: Record<string, unknown>,
  repoVault: Record<string, unknown>,
  datastore: string,
  universalUser: string
): {
  environment: Record<string, string>;
  workingDirectory: string;
  repositoryPath: string;
  networkId: string;
} {
  const repositoryPath = (repoVault.path ?? `/home/${repositoryName}`) as string;
  const networkId = (repoVault.networkId ?? '') as string;
  const networkMode = (repoVault.networkMode ??
    machineVault.networkMode ??
    DEFAULTS.REPOSITORY.NETWORK_MODE) as string;
  const tag = (repoVault.tag ?? DEFAULTS.REPOSITORY.TAG) as string;
  const immovable = repoVault.immovable ? 'true' : 'false';
  const workingDirectory = (repoVault.workingDirectory ?? repositoryPath) as string;

  const dockerSocket = (machineVault.dockerSocket ??
    (networkId
      ? `/var/run/rediacc/docker-${networkId}.sock`
      : DEFAULTS.DOCKER.SOCKET_PATH)) as string;
  const dockerHost = (machineVault.dockerHost ?? `unix://${dockerSocket}`) as string;

  const environment: Record<string, string> = {
    REDIACC_TEAM: teamName,
    REDIACC_MACHINE: machineName,
    REDIACC_REPOSITORY: repositoryName,
    DOCKER_DATA: `${datastore}${repositoryPath}`,
    DOCKER_EXEC: `${datastore}${repositoryPath}/.docker-exec`,
    DOCKER_FOLDER: `${datastore}${repositoryPath}`,
    DOCKER_HOST: dockerHost,
    DOCKER_SOCKET: dockerSocket,
    REDIACC_DATASTORE: datastore,
    REDIACC_DATASTORE_USER: universalUser,
    REDIACC_IMMOVABLE: immovable,
    REPOSITORY_NETWORK_ID: networkId,
    REPOSITORY_NETWORK_MODE: networkMode,
    REPOSITORY_PATH: repositoryPath,
    REPOSITORY_TAG: tag,
    UNIVERSAL_USER_NAME: universalUser,
    UNIVERSAL_USER_ID: (machineVault.universalUserId ??
      DEFAULTS.REPOSITORY.UNIVERSAL_USER_ID) as string,
    REDIACC_WORKING_DIR: workingDirectory,
    ...(typeof repoVault.environment === 'object' && repoVault.environment !== null
      ? (repoVault.environment as Record<string, string>)
      : {}),
  };

  return { environment, workingDirectory, repositoryPath, networkId };
}

function buildMachineEnvFromVault(
  teamName: string,
  machineName: string,
  datastore: string,
  universalUser: string
): { environment: Record<string, string>; workingDirectory: string } {
  return {
    environment: {
      REDIACC_TEAM: teamName,
      REDIACC_MACHINE: machineName,
      REDIACC_DATASTORE: datastore,
      REDIACC_DATASTORE_USER: universalUser,
      UNIVERSAL_USER_NAME: universalUser,
    },
    workingDirectory: datastore,
  };
}

export async function getSSHConnectionDetails(
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

  let envData: {
    environment: Record<string, string>;
    workingDirectory: string;
    repositoryPath?: string;
    networkId?: string;
  };

  if (repositoryName) {
    debugLog(`Using repository vault for: ${repositoryName}`);
    const repoVault = vaults.repositoryVault ?? {};
    debugLog(`Repository vault fields: ${Object.keys(repoVault).join(', ') || '(empty)'}`);

    envData = buildRepositoryEnvFromVault(
      teamName,
      machineName,
      repositoryName,
      machineVault,
      repoVault,
      baseInfo.datastore,
      baseInfo.universalUser
    );
    debugLog(`Working directory: ${envData.workingDirectory}`);
  } else {
    debugLog('Machine-only connection (no repository specified)');
    envData = buildMachineEnvFromVault(
      teamName,
      machineName,
      baseInfo.datastore,
      baseInfo.universalUser
    );
    debugLog(`Working directory set to datastore: ${envData.workingDirectory}`);
  }

  debugLog(
    `Final connection: ${baseInfo.sshUser}@${baseInfo.host}:${baseInfo.port}, workingDirectory=${envData.workingDirectory}`
  );
  debugLog(`Environment variables count: ${Object.keys(envData.environment).length}`);

  return {
    host: baseInfo.host,
    user: baseInfo.sshUser,
    port: baseInfo.port,
    privateKey: baseInfo.privateKey,
    known_hosts: baseInfo.knownHosts,
    datastore: baseInfo.datastore,
    universalUser: baseInfo.universalUser,
    environment: envData.environment,
    workingDirectory: envData.workingDirectory,
    repositoryPath: envData.repositoryPath,
    networkId: envData.networkId,
  };
}
