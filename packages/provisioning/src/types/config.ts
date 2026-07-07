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
  /**
   * libvirt network / host-bridge name for this VM group (renet VM_NET).
   * Distinct groups must use distinct networks (e.g. "renet11" vs "renet12").
   * Optional: single-group callers inherit renet's default from ambient env.
   */
  netName?: string;
  /**
   * In-VM Docker registry endpoint for this group (renet DOCKER_REGISTRY),
   * e.g. "192.168.112.5:5000". Optional: when unset, renet derives it from the
   * group's bridge IP, so a second group reaches its own registry automatically.
   */
  dockerRegistry?: string;
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
  /**
   * Per-group environment overrides threaded into every `renet ops` subprocess
   * this manager spawns (VM_NET, VM_NET_BASE, VM_WORKERS, DOCKER_REGISTRY, ...).
   *
   * This is what lets one harness process drive two concurrent KVM groups
   * without env-bleed: each group's OpsManager carries its own env, so a
   * group-B command never inherits group-A's ambient VM_NET. When omitted, the
   * subprocess inherits ambient env unchanged (single-group behavior).
   */
  groupEnv?: Record<string, string>;
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
