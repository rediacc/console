/**
 * VS Code Command Utilities
 * Helper functions for VS Code Remote SSH CLI commands
 */

import { t } from '../i18n/index.js';
import { getConnectionVaults } from '../utils/connectionDetails.js';

export interface ConnectionDetails {
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
export function debugLog(message: string): void {
  if (process.env.REDIACC_DEBUG || process.env.DEBUG) {
    // eslint-disable-next-line no-console
    console.log(`[DEBUG] ${message}`);
  }
}

/**
 * Extract base connection info from vault data
 */
function extractVaultBaseInfo(
  machineVault: Record<string, unknown>,
  teamVault: Record<string, unknown>,
  machineName: string,
  teamName: string
): {
  host: string;
  port: number;
  privateKey: string;
  knownHosts: string;
  datastore: string;
  universalUser: string;
} {
  const host = (machineVault.ip ?? machineVault.host) as string | undefined;
  const port = (machineVault.port ?? 22) as number;
  const privateKey = (teamVault.SSH_PRIVATE_KEY ?? teamVault.sshPrivateKey) as string | undefined;
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

  return { host, port, privateKey, knownHosts, datastore, universalUser };
}

/**
 * Build environment variables for repository connection
 */
function buildVSCodeRepoEnvironment(
  teamName: string,
  machineName: string,
  repositoryName: string,
  machineVault: Record<string, unknown>,
  repoVault: Record<string, unknown>,
  datastore: string,
  universalUser: string
): {
  user: string;
  environment: Record<string, string>;
  workingDirectory: string;
  repositoryPath: string;
  networkId: string;
} {
  const repositoryPath = (repoVault.path ?? `/home/${repositoryName}`) as string;
  const networkId = (repoVault.networkId ?? '') as string;
  const networkMode = (repoVault.networkMode ?? machineVault.networkMode ?? 'bridge') as string;
  const tag = (repoVault.tag ?? 'latest') as string;
  const immovable = repoVault.immovable ? 'true' : 'false';
  const workingDirectory = (repoVault.workingDirectory ?? repositoryPath) as string;

  const environment: Record<string, string> = {
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

  return { user: repositoryName, environment, workingDirectory, repositoryPath, networkId };
}

/**
 * Build environment variables for machine-only connection (no repository)
 */
function buildVSCodeMachineEnvironment(
  teamName: string,
  machineName: string,
  datastore: string,
  universalUser: string
): {
  user: string;
  environment: Record<string, string>;
  workingDirectory: string;
  repositoryPath: undefined;
  networkId: undefined;
} {
  return {
    user: universalUser,
    environment: {
      REDIACC_TEAM: teamName,
      REDIACC_MACHINE: machineName,
      REDIACC_DATASTORE: datastore,
      REDIACC_DATASTORE_USER: universalUser,
      UNIVERSAL_USER_NAME: universalUser,
    },
    workingDirectory: datastore,
    repositoryPath: undefined,
    networkId: undefined,
  };
}

export interface VSCodeInstallationInfo {
  path: string;
  version?: string;
  isInsiders?: boolean;
}

/**
 * Display VS Code installation information
 */
export function displayVSCodeInstallation(vscode: VSCodeInstallationInfo | null): void {
  // eslint-disable-next-line no-console
  console.log(t('commands.vscode.check.installation'));

  if (!vscode) {
    // eslint-disable-next-line no-console
    console.log(t('commands.vscode.check.vscodeNotFound'));
    return;
  }

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
}

/**
 * Display VS Code configuration status
 */
export function displayConfigurationStatus(configCheck: {
  configured: boolean;
  settingsPath: string;
  missing: string[];
}): void {
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
    configCheck.missing.forEach((setting) => {
      // eslint-disable-next-line no-console
      console.log(`    - ${setting}`);
    });
  }
}

/**
 * Display active SSH connections
 */
export function displayActiveConnections(connections: string[]): void {
  // eslint-disable-next-line no-console
  console.log(t('commands.vscode.check.activeConnections', { count: connections.length }));

  connections.forEach((conn) => {
    // eslint-disable-next-line no-console
    console.log(`  - ${conn}`);
  });
}

/**
 * Gets SSH connection details from the API using type-safe endpoints
 */
export async function getSSHConnectionDetails(
  teamName: string,
  machineName: string,
  repositoryName?: string
): Promise<ConnectionDetails> {
  debugLog(
    `Getting SSH connection details for team=${teamName}, machine=${machineName}, repository=${repositoryName ?? '(none)'}`
  );

  const vaults = await getConnectionVaults(teamName, machineName, repositoryName);
  const { machineVault, teamVault } = vaults;

  const baseInfo = extractVaultBaseInfo(machineVault, teamVault, machineName, teamName);

  const envData = repositoryName
    ? buildVSCodeRepoEnvironment(
        teamName,
        machineName,
        repositoryName,
        machineVault,
        vaults.repositoryVault ?? {},
        baseInfo.datastore,
        baseInfo.universalUser
      )
    : buildVSCodeMachineEnvironment(
        teamName,
        machineName,
        baseInfo.datastore,
        baseInfo.universalUser
      );

  return {
    host: baseInfo.host,
    user: envData.user,
    port: baseInfo.port,
    privateKey: baseInfo.privateKey,
    known_hosts: baseInfo.knownHosts,
    datastore: baseInfo.datastore,
    universalUser: baseInfo.universalUser,
    repositoryPath: envData.repositoryPath,
    networkId: envData.networkId,
    environment: envData.environment,
    workingDirectory: envData.workingDirectory,
  };
}
