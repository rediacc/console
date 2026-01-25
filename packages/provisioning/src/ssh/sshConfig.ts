import * as fs from 'node:fs';
import * as path from 'node:path';

/**
 * Standardized SSH configuration constants.
 *
 * These values are used across all SSH operations to ensure consistency.
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
 * SSH configuration options for creating SSH config.
 */
export interface SSHConfigOptions {
  /** Override renet data directory */
  dataDir?: string;
  /** Override SSH private key path */
  privateKeyPath?: string;
}

// Cached data directory (can be overridden)
let cachedDataDir: string | undefined;

/**
 * Set the renet data directory for SSH key resolution.
 * Call this before using SSH operations if you need to override the default.
 */
export function setRenetDataDir(dataDir: string): void {
  cachedDataDir = dataDir;
}

/**
 * Get renet data directory.
 *
 * Resolution order (matches renet):
 * 1. Cached override (set via setRenetDataDir)
 * 2. RENET_DATA_DIR environment variable
 * 3. CI auto-detect: $RUNNER_TEMP/renet (GitHub Actions) or /tmp/renet
 * 4. ~/.renet (user home directory)
 */
export function getRenetDataDir(): string {
  // Check cached override first
  if (cachedDataDir) {
    return cachedDataDir;
  }

  // Check RENET_DATA_DIR env var
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
 *
 * @param options - Optional configuration overrides
 */
export function getSSHPrivateKeyPath(options?: SSHConfigOptions): string {
  if (options?.privateKeyPath) {
    return options.privateKeyPath;
  }
  const dataDir = options?.dataDir ?? getRenetDataDir();
  return path.join(dataDir, 'staging', '.ssh', 'id_rsa');
}

/**
 * Check if SSH key exists and is readable.
 *
 * @param options - Optional configuration overrides
 */
export function isSSHKeyAvailable(options?: SSHConfigOptions): boolean {
  const keyPath = getSSHPrivateKeyPath(options);
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
 *
 * @param options - Optional configuration overrides
 */
export function getSSHOptions(options?: SSHConfigOptions): string {
  const baseOptions = '-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null';

  const keyPath = getSSHPrivateKeyPath(options);
  if (isSSHKeyAvailable(options)) {
    return `${baseOptions} -i "${keyPath}"`;
  }

  return baseOptions;
}

/**
 * Get SCP options string for command building.
 *
 * @param options - Optional configuration overrides
 */
export function getSCPOptions(options?: SSHConfigOptions): string {
  const baseOptions = '-o StrictHostKeyChecking=no';

  const keyPath = getSSHPrivateKeyPath(options);
  if (isSSHKeyAvailable(options)) {
    return `${baseOptions} -i "${keyPath}"`;
  }

  return baseOptions;
}
