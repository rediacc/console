import * as fs from 'node:fs';
import * as path from 'node:path';

/**
 * Standardized SSH configuration constants.
 *
 * These values are used across all SSH operations to ensure consistency:
 * - SSHExecutor
 * - OpsVMExecutor
 * - BridgeTestRunner
 * - InfrastructureManager
 * - StorageTestHelper
 */
export const SSH_DEFAULTS = {
  /** Connection timeout in seconds. 10s is more lenient for CI environments. */
  CONNECT_TIMEOUT: 10,
  /** Command execution timeout in milliseconds. */
  EXEC_TIMEOUT: 60000,
  /** Enable batch mode by default (no password prompts). */
  BATCH_MODE: true,
  /** Suppress warnings by default. */
  QUIET: false,
} as const;

/**
 * SSH configuration for bridge tests.
 *
 * Mirrors renet's SSH path resolution logic from:
 * renet/pkg/infra/config/config.go (resolveDataDir function)
 *
 * SSH keys are stored at {RENET_DATA_DIR}/staging/.ssh/id_rsa
 */

/**
 * Get renet data directory.
 *
 * Resolution order (matches renet):
 * 1. RENET_DATA_DIR environment variable
 * 2. CI auto-detect: $RUNNER_TEMP/renet (GitHub Actions) or /tmp/renet
 * 3. ~/.renet (user home directory)
 */
function getRenetDataDir(): string {
  // Check RENET_DATA_DIR env var first (highest priority)
  if (process.env.RENET_DATA_DIR) {
    return process.env.RENET_DATA_DIR;
  }

  // CI auto-detect
  if (process.env.CI === 'true') {
    const runnerTemp = process.env.RUNNER_TEMP;
    return runnerTemp ? path.join(runnerTemp, 'renet') : '/tmp/renet';
  }

  // Default: ~/.renet
  return path.join(process.env.HOME || '', '.renet');
}

/**
 * Get the SSH private key path.
 */
export function getSSHPrivateKeyPath(): string {
  return path.join(getRenetDataDir(), 'staging', '.ssh', 'id_rsa');
}

/**
 * Check if SSH key exists and is readable.
 */
export function isSSHKeyAvailable(): boolean {
  const keyPath = getSSHPrivateKeyPath();
  try {
    fs.accessSync(keyPath, fs.constants.R_OK);
    return true;
  } catch {
    return false;
  }
}

/**
 * Get SSH options string for command building.
 *
 * Returns options including identity file if available.
 * Falls back to basic options if key is not found.
 */
export function getSSHOptions(): string {
  const baseOptions = '-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null';

  const keyPath = getSSHPrivateKeyPath();
  if (isSSHKeyAvailable()) {
    console.warn(`[sshConfig] SSH key found at ${keyPath}`);
    return `${baseOptions} -i "${keyPath}"`;
  }

  // Log warning but continue without key
  // In CI, the setup action should have created the key
  const dataDir = getRenetDataDir();
  console.warn(
    `[sshConfig] SSH key not found at ${keyPath} (DataDir=${dataDir}), using default SSH options`
  );
  return baseOptions;
}

/**
 * Get SCP options string for command building.
 */
export function getSCPOptions(): string {
  const baseOptions = '-o StrictHostKeyChecking=no';

  const keyPath = getSSHPrivateKeyPath();
  if (isSSHKeyAvailable()) {
    return `${baseOptions} -i "${keyPath}"`;
  }

  return baseOptions;
}
