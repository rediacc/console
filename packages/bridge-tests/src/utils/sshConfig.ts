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
 * renet/pkg/infra/config/config.go (lines 226-236, 432-442)
 *
 * SSH keys are stored at {OPS_HOME}/staging/.ssh/id_rsa
 */

// Path from this file to monorepo root
// packages/bridge-tests/src/utils -> packages/bridge-tests/src -> packages/bridge-tests -> packages -> console -> monorepo
const MONOREPO_ROOT = path.resolve(__dirname, '../../../../..');

/**
 * Get OPS_HOME directory.
 *
 * Resolution order (matches renet):
 * 1. OPS_HOME environment variable
 * 2. {RENET_ROOT}/../ops (relative to renet root)
 * 3. {monorepo}/ops (fallback)
 */
function getOpsHome(): string {
  // Check OPS_HOME env var first (highest priority)
  const envOpsHome = process.env.OPS_HOME;
  if (envOpsHome) {
    return envOpsHome;
  }

  // Try relative to RENET_ROOT if set
  const renetRoot = process.env.RENET_ROOT;
  if (renetRoot) {
    return path.join(renetRoot, '..', 'ops');
  }

  // Default: monorepo/ops
  return path.join(MONOREPO_ROOT, 'ops');
}

/**
 * Get the SSH private key path.
 */
export function getSSHPrivateKeyPath(): string {
  return path.join(getOpsHome(), 'staging', '.ssh', 'id_rsa');
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
  const opsHome = process.env.OPS_HOME ?? '(not set)';
  console.warn(
    `[sshConfig] SSH key not found at ${keyPath} (OPS_HOME=${opsHome}), using default SSH options`
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
