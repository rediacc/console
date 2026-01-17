import { SSHConnection, type SSHSetupResult, testSSHConnectivity } from '../ssh/connection.js';
// RepositoryConnectionOptions - future use for enhanced connection handling

/**
 * Folder name constants (must match bridge/cli/scripts/internal.sh)
 */
export const FOLDER_NAMES = {
  INTERIM: 'interim',
  MOUNTS: 'mounts',
  REPOSITORIES: 'repositories',
  IMMOVABLE: 'immovable',
} as const;

/**
 * Repository paths calculated from datastore and repo GUID
 */
export interface RepositoryPaths {
  /** Mount path for repository files */
  mountPath: string;
  /** Image path for repository */
  imagePath: string;
  /** Immovable path for repository */
  immovablePath: string;
  /** Docker folder path */
  dockerFolder: string;
  /** Docker socket path */
  dockerSocket: string;
  /** Docker data path */
  dockerData: string;
  /** Docker exec path */
  dockerExec: string;
  /** Plugin socket directory */
  pluginSocketDir: string;
  /** Runtime base path */
  runtimeBase: string;
}

/**
 * Calculates repository paths from datastore and repository GUID
 *
 * @param repositoryGuid - Repository GUID
 * @param datastore - Datastore base path
 * @returns Repository paths object
 */
export function getRepositoryPaths(repositoryGuid: string, datastore: string): RepositoryPaths {
  const basePath = datastore;
  const dockerBase = `${basePath}/${FOLDER_NAMES.INTERIM}/${repositoryGuid}/docker`;

  // Runtime paths are flattened: /var/run/rediacc/{repository_guid}
  const runtimeBase = `/var/run/rediacc/${repositoryGuid}`;

  return {
    mountPath: `${basePath}/${FOLDER_NAMES.MOUNTS}/${repositoryGuid}`,
    imagePath: `${basePath}/${FOLDER_NAMES.REPOSITORIES}/${repositoryGuid}`,
    immovablePath: `${basePath}/${FOLDER_NAMES.IMMOVABLE}/${repositoryGuid}`,
    dockerFolder: dockerBase,
    dockerSocket: `${runtimeBase}/docker.sock`,
    dockerData: `${dockerBase}/data`,
    dockerExec: `${runtimeBase}/exec`,
    pluginSocketDir: `${runtimeBase}/plugins`,
    runtimeBase,
  };
}

/**
 * Machine connection info extracted from vault
 */
export interface MachineConnectionInfo {
  ip: string;
  user: string;
  port: number;
  datastore: string;
  known_hosts?: string;
  teamName?: string;
  universalUser?: string;
  universalUserId?: string;
}

/**
 * Repository connection class for managing SSH connections to repositories
 */
export class RepositoryConnection {
  private readonly teamName: string;
  private readonly machineName: string;
  private readonly repositoryName: string;

  private machineInfo: Record<string, unknown> | null = null;
  private repoInfo: Record<string, unknown> | null = null;
  private connectionInfo: MachineConnectionInfo | null = null;
  private repositoryPaths: RepositoryPaths | null = null;
  private sshKey: string | null = null;
  private sshConnection: SSHConnection | null = null;

  /**
   * Creates a new repository connection
   *
   * @param teamName - Team name
   * @param machineName - Machine name
   * @param repositoryName - Repository name
   */
  constructor(teamName: string, machineName: string, repositoryName: string) {
    this.teamName = teamName;
    this.machineName = machineName;
    this.repositoryName = repositoryName;
  }

  /**
   * Initializes the connection with provided data
   * This is used when you already have the machine/repo info from an API call
   *
   * @param options - Connection options including credentials and paths
   */
  initialize(options: {
    machineInfo: Record<string, unknown>;
    repoInfo: Record<string, unknown>;
    connectionInfo: MachineConnectionInfo;
    repositoryGuid: string;
    sshKey: string;
  }): void {
    this.machineInfo = options.machineInfo;
    this.repoInfo = options.repoInfo;
    this.connectionInfo = options.connectionInfo;
    this.sshKey = options.sshKey;

    // Calculate repository paths
    this.repositoryPaths = getRepositoryPaths(
      options.repositoryGuid,
      options.connectionInfo.datastore
    );

    // Create SSH connection (but don't set it up yet)
    this.sshConnection = new SSHConnection(
      this.sshKey,
      this.connectionInfo.known_hosts ?? '',
      this.connectionInfo.port
    );
  }

  /**
   * Tests connectivity to the machine
   *
   * @param timeout - Timeout in milliseconds (default: 5000)
   * @returns Object with success status and optional error
   */
  async testConnectivity(timeout = 5000): Promise<{ success: boolean; error?: string }> {
    if (!this.connectionInfo) {
      return { success: false, error: 'Connection not initialized' };
    }

    return testSSHConnectivity(this.connectionInfo.ip, this.connectionInfo.port, timeout);
  }

  /**
   * Sets up the SSH connection
   *
   * @returns SSH setup result with options
   */
  async setupSSH(): Promise<SSHSetupResult> {
    if (!this.sshConnection) {
      throw new Error('Connection not initialized. Call initialize() first.');
    }

    return this.sshConnection.setup();
  }

  /**
   * Cleans up SSH resources
   */
  async cleanupSSH(): Promise<void> {
    if (this.sshConnection) {
      await this.sshConnection.cleanup();
    }
  }

  /**
   * Gets the SSH destination string (user@host)
   */
  get sshDestination(): string {
    if (!this.connectionInfo) {
      throw new Error('Connection not initialized');
    }
    return `${this.connectionInfo.user}@${this.connectionInfo.ip}`;
  }

  /**
   * Gets the SSH options for command construction
   */
  get sshOptions(): string[] {
    if (!this.sshConnection) {
      throw new Error('Connection not initialized');
    }
    return this.sshConnection.sshOptions;
  }

  /**
   * Gets the underlying SSH connection
   */
  get ssh(): SSHConnection | null {
    return this.sshConnection;
  }

  /**
   * Gets the machine information
   */
  get machine(): Record<string, unknown> | null {
    return this.machineInfo;
  }

  /**
   * Gets the repository information
   */
  get repository(): Record<string, unknown> | null {
    return this.repoInfo;
  }

  /**
   * Gets the connection information
   */
  get connection(): MachineConnectionInfo | null {
    return this.connectionInfo;
  }

  /**
   * Gets the repository paths
   */
  get paths(): RepositoryPaths | null {
    return this.repositoryPaths;
  }

  /**
   * Gets the repository GUID
   */
  get repositoryGuid(): string | null {
    if (!this.repoInfo) return null;
    return (this.repoInfo.repositoryGuid as string) || null;
  }

  /**
   * Executes a callback with automatic SSH cleanup
   *
   * @param callback - Function to execute with SSH options
   * @returns Result of the callback
   */
  async withSSH<T>(
    callback: (sshOptions: string[], destination: string) => Promise<T>
  ): Promise<T> {
    if (!this.sshConnection) {
      throw new Error('Connection not initialized');
    }

    return this.sshConnection.withConnection(async (sshOptions) => {
      return callback(sshOptions, this.sshDestination);
    });
  }
}

/**
 * Environment variables to set for repository container access
 *
 * @param paths - Repository paths
 * @param repositoryName - Repository name
 * @returns Environment variables object
 */
export function getRepositoryEnvironment(
  paths: RepositoryPaths,
  repositoryName: string
): Record<string, string> {
  return {
    DOCKER_HOST: `unix://${paths.dockerSocket}`,
    REDIACC_REPOSITORY: repositoryName,
    REDIACC_MOUNT_PATH: paths.mountPath,
    REDIACC_IMAGE_PATH: paths.imagePath,
  };
}
