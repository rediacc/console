/**
 * Shared renet execution utilities.
 * Extracted from local-executor.ts for reuse by both local and S3 mode.
 */

import { type ChildProcess, execSync, spawn } from 'node:child_process';
import * as fs from 'node:fs/promises';
import * as os from 'node:os';
import * as path from 'node:path';
import { DEFAULTS, NETWORK_DEFAULTS, PROCESS_DEFAULTS } from '@rediacc/shared/config';
import { extractRenetToLocal, isSEA } from './embedded-assets.js';
import { outputService } from './output.js';
import { renetProvisioner } from './renet-provisioner.js';
import type { LocalMachineConfig } from '../types/index.js';

/** Options for renet spawning */
export interface RenetSpawnOptions {
  /** Enable debug output */
  debug?: boolean;
  /** Output as JSON */
  json?: boolean;
  /** Timeout in milliseconds (default: 10 minutes) */
  timeout?: number;
}

/**
 * Read SSH key from filesystem.
 * Expands ~ to home directory.
 */
export async function readSSHKey(keyPath: string): Promise<string> {
  const expandedPath = keyPath.startsWith('~')
    ? path.join(os.homedir(), keyPath.slice(1))
    : keyPath;

  try {
    return await fs.readFile(expandedPath, 'utf-8');
  } catch (error) {
    throw new Error(`Failed to read SSH key from ${expandedPath}: ${error}`);
  }
}

/**
 * Read SSH public key, returning empty string on failure.
 */
export async function readOptionalSSHKey(keyPath: string | undefined): Promise<string> {
  if (!keyPath) return '';
  return readSSHKey(keyPath).catch(() => '');
}

/**
 * Get the local path to the renet binary for spawning.
 * In dev mode, uses the configured renetPath. In SEA mode, extracts the
 * embedded binary to a local temp file.
 */
export async function getLocalRenetPath(config: { renetPath: string }): Promise<string> {
  if (!isSEA()) return config.renetPath;
  return extractRenetToLocal();
}

/**
 * Provision renet binary to the remote machine.
 */
export async function provisionRenetToRemote(
  config: { renetPath: string },
  machine: LocalMachineConfig,
  sshPrivateKey: string,
  options: Pick<RenetSpawnOptions, 'debug'>
): Promise<void> {
  let localBinaryPath: string | undefined;
  if (!isSEA()) {
    localBinaryPath = config.renetPath.startsWith('/')
      ? config.renetPath
      : execSync(`which ${config.renetPath}`, { encoding: 'utf-8' }).trim();
  }

  const result = await renetProvisioner.provision(
    {
      host: machine.ip,
      port: machine.port ?? DEFAULTS.SSH.PORT,
      username: machine.user,
      privateKey: sshPrivateKey,
    },
    { localBinaryPath }
  );

  if (!result.success) {
    throw new Error(result.error ?? PROCESS_DEFAULTS.RENET_PROVISION_ERROR);
  }

  if (result.action === 'uploaded' && options.debug) {
    outputService.info(`[local] Provisioned renet (${result.arch}) to ${machine.ip}`);
  }
}

/**
 * Build QueueVaultV2 structure for local/s3 execution.
 */
export function buildLocalVault(opts: {
  functionName: string;
  machineName: string;
  machine: LocalMachineConfig;
  sshPrivateKey: string;
  sshPublicKey: string;
  sshKnownHosts: string;
  params: Record<string, unknown>;
}): string {
  const vault = {
    $schema: 'queue-vault-v2',
    version: '2.0',
    task: {
      function: opts.functionName,
      machine: opts.machineName,
      team: 'local',
      repository: (opts.params.repository ?? '') as string,
    },
    ssh: {
      private_key: opts.sshPrivateKey,
      public_key: opts.sshPublicKey,
      known_hosts: opts.sshKnownHosts,
      password: '',
    },
    machine: {
      ip: opts.machine.ip,
      user: opts.machine.user,
      port: opts.machine.port ?? DEFAULTS.SSH.PORT,
      datastore: opts.machine.datastore ?? NETWORK_DEFAULTS.DATASTORE_PATH,
      known_hosts: opts.sshKnownHosts,
    },
    params: opts.params,
    extra_machines: {},
    storage_systems: {},
    repository_credentials: {},
    repositories: {},
    context: {
      organization_id: '',
      api_url: '',
      universal_user_id: '7111',
      universal_user_name: 'rediacc',
    },
  };

  return JSON.stringify(vault);
}

/**
 * Spawn renet execute process and stream output.
 */
export async function spawnRenet(
  renetPath: string,
  vault: string,
  options: RenetSpawnOptions
): Promise<{ exitCode: number }> {
  return new Promise((resolve, reject) => {
    const args = ['execute', '--vault', vault];

    if (options.debug) args.push('--debug');
    if (options.json) args.push('--json');

    const timeout = options.timeout ?? 10 * 60 * 1000;

    if (options.debug) {
      outputService.info(`[local] Spawning: ${renetPath} execute ...`);
    }

    const child: ChildProcess = spawn(renetPath, args, {
      stdio: ['ignore', 'pipe', 'pipe'],
      env: { ...process.env },
    });

    const timeoutId = setTimeout(() => {
      child.kill('SIGTERM');
      reject(new Error(`Execution timed out after ${timeout}ms`));
    }, timeout);

    child.stdout?.on('data', (data: Buffer) => {
      data.toString().split('\n').forEach((line) => {
        if (line.trim()) process.stdout.write(`${line}\n`);
      });
    });

    child.stderr?.on('data', (data: Buffer) => {
      data.toString().split('\n').forEach((line) => {
        if (line.trim()) process.stderr.write(`${line}\n`);
      });
    });

    child.on('close', (code) => {
      clearTimeout(timeoutId);
      resolve({ exitCode: code ?? 1 });
    });

    child.on('error', (err) => {
      clearTimeout(timeoutId);
      reject(new Error(`Failed to spawn renet: ${err.message}`));
    });
  });
}
