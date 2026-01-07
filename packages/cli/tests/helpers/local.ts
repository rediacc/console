/* eslint-disable no-console */
/**
 * Test helpers for local mode testing.
 *
 * Provides utilities for creating test contexts, managing SSH keys,
 * and cleaning up after tests.
 */
import * as fs from 'fs/promises';
import * as os from 'os';
import * as path from 'path';
import { runCli, type CliResult } from './cli.js';

/**
 * Configuration for local mode E2E testing.
 * These values are read from environment variables.
 */
export interface E2EConfig {
  /** IP address of test VM 1 */
  vm1Ip: string;
  /** IP address of test VM 2 */
  vm2Ip: string;
  /** SSH username */
  sshUser: string;
  /** Path to SSH private key */
  sshKeyPath: string;
  /** Whether E2E tests are enabled */
  enabled: boolean;
}

/**
 * Get E2E configuration from environment variables.
 * Returns { enabled: false } if not configured.
 */
export function getE2EConfig(): E2EConfig {
  const vm1Ip = process.env.E2E_VM1_IP;
  const vm2Ip = process.env.E2E_VM2_IP;
  const sshUser = process.env.E2E_SSH_USER;
  const sshKeyPath = process.env.E2E_SSH_KEY ?? '~/.ssh/id_rsa';

  const enabled = !!(vm1Ip && sshUser);

  return {
    vm1Ip: vm1Ip ?? '192.168.111.11',
    vm2Ip: vm2Ip ?? '192.168.111.12',
    sshUser: sshUser ?? 'root',
    sshKeyPath,
    enabled,
  };
}

/**
 * Skip test if E2E config is not available.
 * Use in beforeAll or test body.
 */
export function skipIfNoE2E(): void {
  const config = getE2EConfig();
  if (!config.enabled) {
    console.log('Skipping E2E test: E2E_VM1_IP and E2E_SSH_USER not set');
  }
}

/**
 * Create a test local context with standard configuration.
 */
export async function createTestLocalContext(
  name: string,
  options?: {
    sshKeyPath?: string;
    renetPath?: string;
    autoSwitch?: boolean;
  }
): Promise<CliResult> {
  const sshKey = options?.sshKeyPath ?? '~/.ssh/id_rsa';
  const args = ['context', 'create-local', name, '--ssh-key', sshKey];

  if (options?.renetPath) {
    args.push('--renet-path', options.renetPath);
  }

  if (options?.autoSwitch) {
    args.push('--switch');
  }

  return runCli(args, { skipJsonParse: true });
}

/**
 * Add a test machine to the current local context.
 */
export async function addTestMachine(
  name: string,
  ip: string,
  user: string,
  options?: {
    port?: number;
    datastore?: string;
  }
): Promise<CliResult> {
  const args = ['context', 'add-machine', name, '--ip', ip, '--user', user];

  if (options?.port) {
    args.push('--port', String(options.port));
  }

  if (options?.datastore) {
    args.push('--datastore', options.datastore);
  }

  return runCli(args, { skipJsonParse: true });
}

/**
 * Set up a complete test environment with local context and machines.
 * Returns cleanup function.
 */
export async function setupLocalTestEnvironment(
  contextName: string,
  machines: { name: string; ip: string; user: string }[]
): Promise<() => Promise<void>> {
  // Create local context
  await createTestLocalContext(contextName, { autoSwitch: true });

  // Add machines
  for (const machine of machines) {
    await addTestMachine(machine.name, machine.ip, machine.user);
  }

  // Return cleanup function
  return async () => {
    await runCli(['context', 'delete', contextName], { skipJsonParse: true });
  };
}

/**
 * Set up E2E test environment with real VMs.
 * Returns cleanup function or null if E2E not configured.
 */
export async function setupE2EEnvironment(
  contextName: string
): Promise<(() => Promise<void>) | null> {
  const config = getE2EConfig();

  if (!config.enabled) {
    return null;
  }

  // Create local context with real SSH key
  await createTestLocalContext(contextName, {
    sshKeyPath: config.sshKeyPath,
    autoSwitch: true,
  });

  // Add real VMs
  await addTestMachine('vm1', config.vm1Ip, config.sshUser);

  if (config.vm2Ip) {
    await addTestMachine('vm2', config.vm2Ip, config.sshUser);
  }

  return async () => {
    await runCli(['context', 'delete', contextName], { skipJsonParse: true });
  };
}

/**
 * Execute a function in local mode and return the result.
 */
export async function runLocalFunction(
  functionName: string,
  machineName: string,
  options?: {
    params?: Record<string, string>;
    debug?: boolean;
    timeout?: number;
  }
): Promise<CliResult> {
  const args = ['run', functionName, '--machine', machineName];

  if (options?.params) {
    for (const [key, value] of Object.entries(options.params)) {
      args.push('--param', `${key}=${value}`);
    }
  }

  if (options?.debug) {
    args.push('--debug');
  }

  return runCli(args, {
    skipJsonParse: true,
    timeout: options?.timeout,
  });
}

/**
 * Wait for condition to be true with timeout.
 */
export async function waitFor(
  condition: () => Promise<boolean>,
  timeoutMs = 30000,
  intervalMs = 1000
): Promise<boolean> {
  const startTime = Date.now();

  while (Date.now() - startTime < timeoutMs) {
    if (await condition()) {
      return true;
    }
    await sleep(intervalMs);
  }

  return false;
}

/**
 * Sleep for specified milliseconds.
 */
export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Check if SSH key exists and is readable.
 */
export async function checkSSHKeyExists(keyPath: string): Promise<boolean> {
  const expandedPath = keyPath.startsWith('~')
    ? path.join(os.homedir(), keyPath.slice(1))
    : keyPath;

  try {
    await fs.access(expandedPath);
    return true;
  } catch {
    return false;
  }
}

/**
 * Generate a unique test context name.
 */
export function generateTestContextName(prefix = 'test'): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

/**
 * Type guard for checking if a result is successful.
 */
export function isSuccessfulResult(result: CliResult): boolean {
  return result.success && result.exitCode === 0;
}

/**
 * Extract error message from CLI result.
 */
export function getErrorFromResult(result: CliResult): string {
  if (result.json && typeof result.json === 'object') {
    const json = result.json as { error?: { message?: string } };
    if (json.error?.message) {
      return json.error.message;
    }
  }
  return result.stderr || result.stdout || 'Unknown error';
}

/**
 * Assert that a CLI result was successful.
 * Throws with detailed error message if not.
 */
export function assertSuccess(result: CliResult, message?: string): void {
  if (!isSuccessfulResult(result)) {
    const errorMsg = message ?? 'CLI command failed';
    const details = getErrorFromResult(result);
    throw new Error(`${errorMsg}: ${details}`);
  }
}

/**
 * Clean up multiple test contexts.
 */
export async function cleanupContexts(...contextNames: string[]): Promise<void> {
  for (const name of contextNames) {
    try {
      await runCli(['context', 'delete', name], { skipJsonParse: true });
    } catch {
      // Ignore errors during cleanup
    }
  }
}
