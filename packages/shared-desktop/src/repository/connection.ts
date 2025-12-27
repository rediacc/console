import { SSHConnection, testSSHConnectivity, type SSHSetupResult } from '../ssh/connection.js';
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
 * @param repoGuid - Repository GUID
 * @param datastore - Datastore base path
 * @returns Repository paths object
 */
export function getRepositoryPaths(repoGuid: string, datastore: string): RepositoryPaths {
  const basePath = datastore;
  const dockerBase = `${basePath}/${FOLDER_NAMES.INTERIM}/${repoGuid}/docker`;

  // Runtime paths are flattened: /var/run/rediacc/{repo_guid}
  const runtimeBase = `/var/run/rediacc/${repoGuid}`;

  return {
    mountPath: `${basePath}/${FOLDER_NAMES.MOUNTS}/${repoGuid}`,
    imagePath: `${basePath}/${FOLDER_NAMES.REPOSITORIES}/${repoGuid}`,
    immovablePath: `${basePath}/${FOLDER_NAMES.IMMOVABLE}/${repoGuid}`,
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
  hostEntry?: string;
  teamName?: string;
  universalUser?: string;
  universalUserId?: string;
}

/**
 * Repository connection class for managing SSH connections to repositories
 */
export class RepositoryConnection {
  private teamName: string;
  private machineName: string;
  private repoName: string;

  private machineInfo: Record<string, unknown> | null = null;
  private repoInfo: Record<string, unknown> | null = null;
  private connectionInfo: MachineConnectionInfo | null = null;
  private repoPaths: RepositoryPaths | null = null;
  private sshKey: string | null = null;
  private sshConnection: SSHConnection | null = null;

  /**
   * Creates a new repository connection
   *
   * @param teamName - Team name
   * @param machineName - Machine name
   * @param repoName - Repository name
   */
  constructor(teamName: string, machineName: string, repoName: string) {
    this.teamName = teamName;
    this.machineName = machineName;
    this.repoName = repoName;
  }

  /**
   * Initializes the connection with provided data
   * This is used when you already have the machine/repo info from an API call
   *
   * @param options - Connection options including credentials and paths
   */
  async initialize(options: {
    machineInfo: Record<string, unknown>;
    repoInfo: Record<string, unknown>;
    connectionInfo: MachineConnectionInfo;
    repoGuid: string;
    sshKey: string;
  }): Promise<void> {
    this.machineInfo = options.machineInfo;
    this.repoInfo = options.repoInfo;
    this.connectionInfo = options.connectionInfo;
    this.sshKey = options.sshKey;

    // Calculate repository paths
    this.repoPaths = getRepositoryPaths(options.repoGuid, options.connectionInfo.datastore);

    // Create SSH connection (but don't set it up yet)
    this.sshConnection = new SSHConnection(
      this.sshKey,
      this.connectionInfo.hostEntry ?? '',
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
    return this.repoPaths;
  }

  /**
   * Gets the repository GUID
   */
  get repoGuid(): string | null {
    if (!this.repoInfo) return null;
    return (
      (this.repoInfo.repositoryGuid as string) ||
      (this.repoInfo.repoGuid as string) ||
      (this.repoInfo.grandGuid as string) ||
      null
    );
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
 * @param repoName - Repository name
 * @returns Environment variables object
 */
export function getRepositoryEnvironment(
  paths: RepositoryPaths,
  repoName: string
): Record<string, string> {
  return {
    DOCKER_HOST: `unix://${paths.dockerSocket}`,
    REDIACC_REPO: repoName,
    REDIACC_MOUNT_PATH: paths.mountPath,
    REDIACC_IMAGE_PATH: paths.imagePath,
  };
}
