/**
 * Shared renet execution utilities.
 * Extracted from local-executor.ts for reuse by both local and S3 mode.
 */

import { execSync } from 'node:child_process';
import * as fs from 'node:fs/promises';
import * as os from 'node:os';
import * as path from 'node:path';
import { DEFAULTS, NETWORK_DEFAULTS, PROCESS_DEFAULTS } from '@rediacc/shared/config';
import type { BridgeFunctionName } from '@rediacc/shared/queue-vault/data/functions.generated';
import { FUNCTION_REQUIREMENTS } from '@rediacc/shared/queue-vault/data/functions.generated';
import { SFTPClient } from '@rediacc/shared-desktop/sftp';
import type { MachineConfig } from '../types/index.js';
import { extractRenetToLocal, isSEA } from './embedded-assets.js';
import { outputService } from './output.js';
import { renetProvisioner } from './renet-provisioner.js';

/** Setup marker file created by `renet setup` on successful completion */
const SETUP_MARKER_PATH = '/var/lib/rediacc/setup_7111_completed';

/** Cache TTL for setup verification (1 hour) */
const SETUP_CACHE_TTL_MS = 60 * 60 * 1000;

/** In-memory cache: host:port -> timestamp of last successful verification */
const setupCache = new Map<string, number>();

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
  machine: MachineConfig,
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

/** Check whether a bridge function requires the BTRFS datastore. */
function functionRequiresDatastore(functionName: string): boolean {
  if (!(functionName in FUNCTION_REQUIREMENTS)) return false;
  const reqs = FUNCTION_REQUIREMENTS[functionName as BridgeFunctionName];
  return reqs.requirements.repository === true;
}

/**
 * Verify that a remote machine has completed `renet setup`.
 * Checks for the setup marker file and BTRFS datastore via SSH.
 * Only enforced for functions that require the `repository` requirement
 * (backup, snapshot, repo operations). System and admin functions
 * (machine_ping, setup_machine, machine_uninstall, etc.) skip verification
 * so they can operate on machines regardless of setup state.
 * Bypass with RDC_SKIP_SETUP_CHECK=1 environment variable.
 */
export async function verifyMachineSetup(
  machine: MachineConfig,
  sshPrivateKey: string,
  options: Pick<RenetSpawnOptions, 'debug'> & { functionName?: string }
): Promise<void> {
  if (process.env.RDC_SKIP_SETUP_CHECK) return;

  // Only verify setup for functions that require the BTRFS datastore.
  // System functions (machine_ping, machine_version, setup_machine,
  // machine_install, machine_uninstall, etc.) must work on machines
  // regardless of setup state.
  const needsDatastore = options.functionName
    ? functionRequiresDatastore(options.functionName)
    : true;
  if (!needsDatastore) return;

  const cacheKey = `${machine.ip}:${machine.port ?? DEFAULTS.SSH.PORT}`;
  const cached = setupCache.get(cacheKey);
  if (cached && Date.now() - cached < SETUP_CACHE_TTL_MS) return;

  const sftp = new SFTPClient({
    host: machine.ip,
    port: machine.port ?? DEFAULTS.SSH.PORT,
    username: machine.user,
    privateKey: sshPrivateKey,
  });

  try {
    await sftp.connect();
    const result = await sftp.exec(`test -f ${SETUP_MARKER_PATH} && echo OK || echo MISSING`);
    if (result.trim() !== 'OK') {
      throw new Error(
        `Machine '${machine.ip}' has not been set up. ` +
          `Run 'rdc context setup-machine <name>' or 'sudo renet setup --auto' directly on the machine.`
      );
    }

    const datastorePath = machine.datastore ?? NETWORK_DEFAULTS.DATASTORE_PATH;
    // Use multiple detection methods matching the Go bridge's approach:
    // 1. findmnt (preferred), 2. stat -f, 3. /proc/mounts grep
    const fsCheck = await sftp.exec(
      `findmnt -n -o FSTYPE -T '${datastorePath}' 2>/dev/null || ` +
        `stat -f -c '%T' '${datastorePath}' 2>/dev/null || ` +
        `awk '$2 == "${datastorePath}" { print $3 }' /proc/mounts 2>/dev/null || ` +
        `echo UNKNOWN`
    );
    if (fsCheck.trim() !== 'btrfs') {
      throw new Error(
        `Machine '${machine.ip}' datastore at ${datastorePath} is not BTRFS (found: ${fsCheck.trim()}). ` +
          `Run 'rdc context setup-machine <name>' to initialize the BTRFS datastore.`
      );
    }

    setupCache.set(cacheKey, Date.now());
    if (options.debug) {
      outputService.info(`[local] Setup verified on ${machine.ip}`);
    }
  } finally {
    sftp.close();
  }
}

interface BuildLocalVaultOptions {
  functionName: string;
  machineName: string;
  machine: MachineConfig;
  sshPrivateKey: string;
  sshPublicKey: string;
  sshKnownHosts: string;
  params: Record<string, unknown>;
  extraMachines?: Record<string, { ip: string; port?: number; user: string }>;
  storages?: Record<string, { vaultContent: Record<string, unknown> }>;
  repositoryCredentials?: Record<string, string>;
  repositoryConfigs?: Record<string, { guid: string; name: string; networkId?: number }>;
}

function buildExtraMachines(
  machines: Record<string, { ip: string; port?: number; user: string }> | undefined,
  sshKnownHosts: string,
  sshPrivateKey: string,
  sshPublicKey: string
): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  if (!machines) return result;
  for (const [name, cfg] of Object.entries(machines)) {
    result[name] = {
      ip: cfg.ip,
      user: cfg.user,
      port: cfg.port ?? DEFAULTS.SSH.PORT,
      datastore: NETWORK_DEFAULTS.DATASTORE_PATH,
      known_hosts: sshKnownHosts,
      ssh: {
        private_key: sshPrivateKey,
        public_key: sshPublicKey,
      },
    };
  }
  return result;
}

function buildStorageSection(vault: Record<string, unknown>): Record<string, unknown> | null {
  const provider = String(vault.provider ?? '');
  if (!provider) return null;

  const section: Record<string, unknown> = { backend: provider };
  if (vault.bucket) section.bucket = String(vault.bucket);
  if (vault.region) section.region = String(vault.region);
  if (vault.folder !== undefined && vault.folder !== null) {
    section.folder = String(vault.folder);
  }

  const parameters: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(vault)) {
    if (['provider', 'bucket', 'region', 'folder'].includes(key)) continue;
    parameters[key] = value;
  }
  if (Object.keys(parameters).length > 0) {
    section.parameters = parameters;
  }

  return section;
}

function buildStorageSystems(
  storages: Record<string, { vaultContent: Record<string, unknown> }> | undefined
): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  if (!storages) return result;
  for (const [name, storage] of Object.entries(storages)) {
    const section = buildStorageSection(storage.vaultContent);
    if (section) result[name] = section;
  }
  return result;
}

function buildRepositories(
  params: Record<string, unknown>,
  repositoryConfigs?: Record<string, { guid: string; name: string; networkId?: number }>
): { repoName: string; repositories: Record<string, unknown> } {
  const repoName = (params.repository ?? '') as string;
  const repositories: Record<string, unknown> = {};

  if (repoName) {
    // Single-repo mode: build entry for just this repo
    const repoConfig = repositoryConfigs?.[repoName];
    const repoEntry: Record<string, unknown> = {
      guid: repoConfig?.guid ?? repoName,
      name: repoName,
    };
    const networkId = repoConfig?.networkId ?? params.network_id;
    if (networkId !== undefined && networkId !== '' && networkId !== 0) {
      repoEntry.network_id = typeof networkId === 'number' ? networkId : Number(networkId);
    }
    repositories[repoName] = repoEntry;
  } else if (repositoryConfigs) {
    // Multi-repo mode (e.g., up-all): include all repos from config
    for (const [name, config] of Object.entries(repositoryConfigs)) {
      const repoEntry: Record<string, unknown> = {
        guid: config.guid,
        name,
      };
      if (config.networkId !== undefined && config.networkId !== 0) {
        repoEntry.network_id = config.networkId;
      }
      repositories[name] = repoEntry;
    }
  }

  return { repoName, repositories };
}

/**
 * Build QueueVaultV2 structure for local/s3 execution.
 */
export function buildLocalVault(opts: BuildLocalVaultOptions): string {
  const extraMachines = buildExtraMachines(
    opts.extraMachines,
    opts.sshKnownHosts,
    opts.sshPrivateKey,
    opts.sshPublicKey
  );
  const storageSystems = buildStorageSystems(opts.storages);
  const { repoName, repositories } = buildRepositories(opts.params, opts.repositoryConfigs);

  const vault = {
    $schema: 'queue-vault-v2',
    version: '2.0',
    task: {
      function: opts.functionName,
      machine: opts.machineName,
      team: 'local',
      repository: repoName,
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
    extra_machines: extraMachines,
    storage_systems: storageSystems,
    repository_credentials: opts.repositoryCredentials ?? {},
    repositories,
    context: {
      organization_id: '',
      api_url: '',
      universal_user_id: '7111',
      universal_user_name: 'rediacc',
    },
  };

  return JSON.stringify(vault);
}
