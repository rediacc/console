/**
 * VM Network Configuration
 * Matches ops/scripts/init.sh configuration pattern
 */
export interface VMNetworkConfig {
  /** Network prefix (e.g., "192.168.111") */
  netBase: string;
  /** Offset added to VM ID */
  netOffset: number;
  /** Bridge VM ID */
  bridgeId: number;
  /** Worker VM IDs */
  workerIds: number[];
  /** Ceph node IDs (optional) */
  cephIds: number[];
}

/**
 * Renet binary configuration
 */
export interface RenetConfig {
  /** Path to renet binary */
  binaryPath: string;
  /** Renet root directory (for ops commands) */
  rootPath: string;
}

/**
 * SSH configuration for provisioning
 */
export interface SSHProvisioningConfig {
  /** Renet data directory (for SSH keys) */
  dataDir?: string;
  /** Path to SSH private key */
  privateKeyPath?: string;
}

/**
 * Complete provisioning configuration
 * Used to initialize OpsManager with injectable config instead of env vars
 */
export interface ProvisioningConfig {
  /** VM network configuration */
  network: VMNetworkConfig;
  /** Renet binary configuration */
  renet: RenetConfig;
  /** SSH configuration (optional) */
  ssh?: SSHProvisioningConfig;
}

/**
 * Result from command execution
 */
export interface CommandResult {
  stdout: string;
  stderr: string;
  code: number;
}

/**
 * Result from command execution with success flag
 */
export interface ExecutionResult extends CommandResult {
  success: boolean;
}
