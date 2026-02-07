/**
 * Test helpers for local mode testing in Playwright.
 *
 * Provides utilities for creating test contexts, managing SSH keys,
 * and cleaning up after tests.
 */
import * as fs from 'node:fs/promises';
import * as os from 'node:os';
import * as path from 'node:path';
import { DEFAULTS, VM_NETWORK } from '@rediacc/shared/config';
import { type CliResult, CliTestRunner } from './CliTestRunner';

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
  /** Path to renet binary (for local execution) */
  renetPath: string;
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
  const sshKeyPath = process.env.E2E_SSH_KEY ?? DEFAULTS.CLI_TEST.SSH_KEY_PATH;
  const renetPath = process.env.E2E_RENET_PATH ?? process.env.RENET_BINARY ?? 'renet';

  const enabled = !!(vm1Ip && sshUser);

  return {
    vm1Ip: vm1Ip ?? VM_NETWORK.WORKER_IPS[0],
    vm2Ip: vm2Ip ?? VM_NETWORK.WORKER_IPS[1],
    sshUser: sshUser ?? DEFAULTS.CLI_TEST.VM_USER,
    sshKeyPath,
    renetPath,
    enabled,
  };
}

/**
 * Create a test local context with standard configuration.
 */
export function createTestLocalContext(
  name: string,
  options?: {
    sshKeyPath?: string;
    renetPath?: string;
  }
): Promise<CliResult> {
  const runner = new CliTestRunner();
  const sshKey = options?.sshKeyPath ?? DEFAULTS.CLI_TEST.SSH_KEY_PATH;
  const args = ['context', 'create-local', name, '--ssh-key', sshKey];

  if (options?.renetPath) {
    args.push('--renet-path', options.renetPath);
  }

  return runner.run(args);
}

/**
 * Add a test machine to a local context.
 */
export function addTestMachine(
  contextName: string,
  name: string,
  ip: string,
  user: string,
  options?: {
    port?: number;
    datastore?: string;
  }
): Promise<CliResult> {
  const runner = CliTestRunner.withContext(contextName);
  const args = ['context', 'add-machine', name, '--ip', ip, '--user', user];

  if (options?.port) {
    args.push('--port', String(options.port));
  }

  if (options?.datastore) {
    args.push('--datastore', options.datastore);
  }

  return runner.run(args);
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

  // Create local context with real SSH key and renet path
  await createTestLocalContext(contextName, {
    sshKeyPath: config.sshKeyPath,
    renetPath: config.renetPath,
  });

  // Add real VMs
  await addTestMachine(contextName, 'vm1', config.vm1Ip, config.sshUser);

  if (config.vm2Ip) {
    await addTestMachine(contextName, 'vm2', config.vm2Ip, config.sshUser);
  }

  return async () => {
    const runner = new CliTestRunner();
    await runner.run(['context', 'delete', contextName]);
  };
}

/** Set of repository_* functions that take <name> as a positional argument. */
const REPO_POSITIONAL_FUNCTIONS = new Set([
  'repository_create',
  'repository_delete',
  'repository_down',
  'repository_expand',
  'repository_fork',
  'repository_info',
  'repository_mount',
  'repository_ownership',
  'repository_resize',
  'repository_status',
  'repository_template_apply',
  'repository_unmount',
  'repository_up',
  'repository_validate',
]);

/** Convert a camelCase key to kebab-case for CLI flags, consistent with production camelToKebab. */
function toKebabCase(key: string): string {
  return key.replaceAll(/([A-Z])/g, '-$1').toLowerCase();
}

/** Build the base command args from a function name and optional positional repository param. */
function buildCommandArgs(
  functionName: string,
  machineName: string,
  params?: Record<string, string>
): { args: string[]; usedPositional: boolean } {
  const args = [...functionName.split('_')];
  const usePositional = REPO_POSITIONAL_FUNCTIONS.has(functionName) && params?.repository;

  if (usePositional) {
    args.push(params.repository);
  }

  args.push('--machine', machineName);
  return { args, usedPositional: !!usePositional };
}

/** Append --kebab-case param flags to args, skipping positional repository. */
function appendParamFlags(
  args: string[],
  params: Record<string, string>,
  usedPositional: boolean
): void {
  for (const [key, value] of Object.entries(params)) {
    if (key === 'repository' && usedPositional) continue;
    args.push(`--${toKebabCase(key)}`, value);
  }
}

/**
 * Execute a function in local mode and return the result.
 * Builds native CLI command args (e.g. `rdc repository create x --size 4G --machine vm1`)
 * instead of the `rdc run` escape hatch.
 */
export function runLocalFunction(
  functionName: string,
  machineName: string,
  options?: {
    contextName?: string;
    params?: Record<string, string>;
    extraMachines?: string[];
    debug?: boolean;
    timeout?: number;
  }
): Promise<CliResult> {
  const runner = options?.contextName
    ? CliTestRunner.withContext(options.contextName)
    : new CliTestRunner();

  const { args, usedPositional } = buildCommandArgs(functionName, machineName, options?.params);

  if (options?.params) {
    appendParamFlags(args, options.params, usedPositional);
  }

  for (const entry of options?.extraMachines ?? []) {
    args.push('--extra-machine', entry);
  }

  if (options?.debug) {
    args.push('--debug');
  }

  return runner.run(args, { timeout: options?.timeout });
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
  return result.stderr ?? result.stdout ?? 'Unknown error';
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
  const runner = new CliTestRunner();
  for (const name of contextNames) {
    try {
      await runner.run(['context', 'delete', name]);
    } catch {
      // Ignore errors during cleanup
    }
  }
}
