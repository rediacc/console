/**
 * Repository Environment Variables Module
 * Ported from desktop/src/cli/core/repository_env.py
 *
 * Provides comprehensive environment variable setup for repository terminal sessions,
 * matching Python desktop CLI feature parity.
 */

import { DEFAULTS, NETWORK_DEFAULTS } from '@rediacc/shared/config';

/**
 * Full repository environment matching Python's 18+ variables
 */
export interface RepositoryEnvironment {
  // Core identifiers
  REDIACC_TEAM: string;
  REDIACC_MACHINE: string;
  REDIACC_REPOSITORY: string;

  // Docker-related
  DOCKER_DATA: string;
  DOCKER_EXEC: string;
  DOCKER_FOLDER: string;
  DOCKER_HOST: string;
  DOCKER_SOCKET: string;
  DOCKER_PLUGIN_DIR: string;

  // Network and datastore
  REDIACC_DATASTORE: string;
  REDIACC_DATASTORE_USER: string;
  REDIACC_NETWORK_ID: string;
  REDIACC_IMMOVABLE: string;

  // Repository-specific
  REPOSITORY_NETWORK_ID: string;
  REPOSITORY_NETWORK_MODE: string;
  REPOSITORY_PATH: string;
  REPOSITORY_TAG: string;

  // System
  SYSTEM_API_URL: string;
  UNIVERSAL_USER_ID: string;
  UNIVERSAL_USER_NAME: string;

  // Desktop context indicator
  REDIACC_DESKTOP: string;
}

/**
 * Machine vault data structure
 */
export interface MachineVaultData {
  ip?: string;
  host?: string;
  sshPort?: number;
  sshUser?: string;
  user?: string;
  datastore?: string;
  universalUser?: string;
  universalUserId?: string;
  networkMode?: string;
  dockerHost?: string;
  dockerSocket?: string;
}

/**
 * Repository vault data structure
 */
export interface RepositoryVaultData {
  path?: string;
  workingDirectory?: string;
  networkId?: string;
  networkMode?: string;
  tag?: string;
  containerName?: string;
  immovable?: boolean;
  environment?: Record<string, string>;
}

/**
 * Options for building repository environment
 */
export interface BuildEnvironmentOptions {
  teamName: string;
  machineName: string;
  repositoryName: string;
  machineVault: MachineVaultData;
  repositoryVault: RepositoryVaultData;
  apiUrl?: string;
}

/**
 * Generates Docker socket path from network ID
 * Uses networkId directly for backward compatibility with Python CLI
 *
 * @param networkId - Network ID
 * @returns Socket suffix for path generation
 */
function getDockerSocketSuffix(networkId: string): string {
  // Python uses networkId directly: /var/run/docker-{network_id}.sock
  // Do NOT hash - must match Python for backward compatibility
  return networkId || '';
}

/**
 * Builds the full repository environment matching Python's 18+ variables
 *
 * @param options - Environment building options
 * @returns Complete repository environment object
 */
export function buildRepositoryEnvironment(
  options: BuildEnvironmentOptions
): Partial<RepositoryEnvironment> {
  const { teamName, machineName, repositoryName, machineVault, repositoryVault, apiUrl } = options;

  const datastore = machineVault.datastore ?? NETWORK_DEFAULTS.DATASTORE_PATH;
  const universalUser = machineVault.universalUser ?? DEFAULTS.REPOSITORY.UNIVERSAL_USER;
  const universalUserId = machineVault.universalUserId ?? DEFAULTS.REPOSITORY.UNIVERSAL_USER_ID;
  const repositoryPath = repositoryVault.path ?? `/home/${repositoryName}`;
  const networkId = repositoryVault.networkId ?? '';
  const networkMode =
    repositoryVault.networkMode ?? machineVault.networkMode ?? DEFAULTS.REPOSITORY.NETWORK_MODE;
  const tag = repositoryVault.tag ?? DEFAULTS.REPOSITORY.TAG;
  const immovable = repositoryVault.immovable ? 'true' : 'false';

  // Docker socket handling - uses networkId directly for Python compatibility
  // Python uses /var/run/rediacc/docker-{networkId}.sock format
  const socketSuffix = getDockerSocketSuffix(networkId);
  const dockerSocket =
    machineVault.dockerSocket ??
    (socketSuffix ? `/var/run/rediacc/docker-${socketSuffix}.sock` : '/var/run/docker.sock');
  const dockerHost = machineVault.dockerHost ?? `unix://${dockerSocket}`;
  const dockerPluginDir = `${datastore}/docker/plugins`;

  // Build the full environment
  const env: Partial<RepositoryEnvironment> = {
    // Core identifiers
    REDIACC_TEAM: teamName,
    REDIACC_MACHINE: machineName,
    REDIACC_REPOSITORY: repositoryName,

    // Docker-related
    DOCKER_DATA: `${datastore}${repositoryPath}`,
    DOCKER_EXEC: `${datastore}${repositoryPath}/.docker-exec`,
    DOCKER_FOLDER: `${datastore}${repositoryPath}`,
    DOCKER_HOST: dockerHost,
    DOCKER_SOCKET: dockerSocket,
    DOCKER_PLUGIN_DIR: dockerPluginDir,

    // Network and datastore
    REDIACC_DATASTORE: datastore,
    REDIACC_DATASTORE_USER: universalUser,
    REDIACC_NETWORK_ID: networkId,
    REDIACC_IMMOVABLE: immovable,

    // Repository-specific
    REPOSITORY_NETWORK_ID: networkId,
    REPOSITORY_NETWORK_MODE: networkMode,
    REPOSITORY_PATH: repositoryPath,
    REPOSITORY_TAG: tag,

    // System
    UNIVERSAL_USER_ID: universalUserId,
    UNIVERSAL_USER_NAME: universalUser,

    // Desktop context indicator - allows scripts to detect desktop vs CLI context
    REDIACC_DESKTOP: '1',
  };

  // Add API URL if provided
  if (apiUrl) {
    env.SYSTEM_API_URL = apiUrl;
  }

  return env;
}

/**
 * Builds minimal environment for machine-only connections (no repository)
 *
 * @param teamName - Team name
 * @param machineName - Machine name
 * @param machineVault - Machine vault data
 * @returns Minimal environment for machine connection
 */
export function buildMachineEnvironment(
  teamName: string,
  machineName: string,
  machineVault: MachineVaultData
): Record<string, string> {
  const datastore = machineVault.datastore ?? NETWORK_DEFAULTS.DATASTORE_PATH;
  const universalUser = machineVault.universalUser ?? DEFAULTS.REPOSITORY.UNIVERSAL_USER;

  return {
    REDIACC_TEAM: teamName,
    REDIACC_MACHINE: machineName,
    REDIACC_DATASTORE: datastore,
    REDIACC_DATASTORE_USER: universalUser,
    UNIVERSAL_USER_NAME: universalUser,
  };
}

/**
 * Merges environment with any vault-provided custom environment variables
 *
 * @param baseEnv - Base environment from buildRepositoryEnvironment
 * @param vaultEnv - Custom environment from vault
 * @returns Merged environment
 */
export function mergeWithVaultEnvironment(
  baseEnv: Partial<RepositoryEnvironment>,
  vaultEnv?: Record<string, string>
): Record<string, string> {
  const result: Record<string, string> = {};

  // Add base environment
  for (const [key, value] of Object.entries(baseEnv)) {
    result[key] = String(value);
  }

  // Merge vault environment (vault overrides base)
  if (vaultEnv) {
    for (const [key, value] of Object.entries(vaultEnv)) {
      result[key] = String(value);
    }
  }

  return result;
}
