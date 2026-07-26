/**
 * Shared renet execution utilities.
 * Extracted from local-executor.ts for reuse across the CLI's executors.
 */

import { execSync } from 'node:child_process';
import * as fsSync from 'node:fs';
import * as path from 'node:path';
import { DEFAULTS, NETWORK_DEFAULTS, PROCESS_DEFAULTS } from '@rediacc/shared/config';
import type { RenetFunctionName } from '@rediacc/shared/renet-contract/data/functions.generated';
import { FUNCTION_REQUIREMENTS } from '@rediacc/shared/renet-contract/data/functions.generated';
import type { SFTPClient } from '../../remote/sftp/index.js';
import type { MachineConfig } from '../../types/index.js';
import { extractRenetToLocal, isSEA } from '../core/embedded-assets.js';
import { outputService } from '../core/output.js';
import { sftpConfigForMachine, withSharedOrPooledSftp } from '../machine/machine-connection.js';
import { renetProvisioner } from './renet-provisioner.js';
import { isSetupVerifiedFresh, recordSetupVerified } from './provision-state.js';

// The SSH key helpers moved to services/machine/ssh-key.ts so the connection pool
// can read a team key without importing renet. Re-exported here: this module is
// where the rest of the CLI has always imported them from.
export { readOptionalSSHKey, readSSHKey } from '../machine/ssh-key.js';

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
  /** Skip restarting machine-managed services after binary update */
  skipRouterRestart?: boolean;
}

/**
 * Resolve a renet binary path, falling back to PATH lookup if the configured
 * path doesn't exist (e.g. stale config from another OS or worktree).
 */
function resolveRenetPath(configuredPath: string): string {
  // Absolute path — verify it exists before using it
  if (path.isAbsolute(configuredPath)) {
    try {
      fsSync.accessSync(configuredPath);
      return configuredPath;
    } catch {
      // Fall through to PATH lookup
    }
  }

  // Bare name or missing absolute — resolve via PATH (handles .exe on Windows)
  const cmd = process.platform === 'win32' ? 'where' : 'which';
  const name = path.isAbsolute(configuredPath) ? 'renet' : configuredPath;
  try {
    return execSync(`${cmd} ${name}`, { encoding: 'utf-8' }).trim().split(/\r?\n/)[0];
  } catch {
    throw new Error(
      `Renet binary not found at "${configuredPath}" and not in PATH. ` +
        'Run ./rdc.sh to ensure renet is built, or update config with: rdc config init --renet-path <path>'
    );
  }
}

/**
 * Get the local path to the renet binary for spawning.
 * In dev mode, uses the configured renetPath. In SEA mode, extracts the
 * embedded binary to a local temp file.
 */
export async function getLocalRenetPath(config: { renetPath: string }): Promise<string> {
  if (!isSEA()) return resolveRenetPath(config.renetPath);
  return extractRenetToLocal();
}

export interface RenetProvisionResult {
  remotePath: string;
  uploaded: boolean;
}

/**
 * Provision renet binary to the remote machine.
 */
export async function provisionRenetToRemote(
  config: { renetPath: string },
  machine: MachineConfig,
  sshPrivateKey: string,
  options: Pick<RenetSpawnOptions, 'debug' | 'skipRouterRestart'> & { restartServices?: boolean },
  sftp?: SFTPClient
): Promise<RenetProvisionResult> {
  let localBinaryPath: string | undefined;
  if (!isSEA()) {
    localBinaryPath = resolveRenetPath(config.renetPath);
  }

  // Auto-restart rediacc-router after a binary update so the
  // long-running router daemon picks up new code without manual
  // `systemctl restart`. systemctl try-restart is a no-op when the
  // unit is not running, so this is safe on machines without the
  // router daemon. Opt out via skipRouterRestart=true or
  // REDIACC_SKIP_ROUTER_RESTART=1.
  const skipRestart = options.skipRouterRestart ?? !!process.env.REDIACC_SKIP_ROUTER_RESTART;
  const restartServices = skipRestart ? false : (options.restartServices ?? true);

  const start = Date.now();
  const result = await renetProvisioner.provision(
    sftpConfigForMachine(machine, sshPrivateKey),
    { localBinaryPath, restartServices, debug: options.debug },
    sftp
  );
  const elapsed = ((Date.now() - start) / 1000).toFixed(1);

  if (!result.success) {
    throw new Error(result.error ?? PROCESS_DEFAULTS.RENET_PROVISION_ERROR);
  }

  if (result.action === 'uploaded') {
    outputService.info(`Renet updated on ${machine.ip} (${result.arch}) in ${elapsed}s`);
    if (result.servicesRestarted) {
      outputService.info(`Restarted rediacc-router on ${machine.ip}`);
    }
  } else if (options.debug) {
    outputService.info(`Renet verified on ${machine.ip} (${elapsed}s)`);
  }

  return { remotePath: result.remotePath, uploaded: result.action === 'uploaded' };
}

/** Check whether a bridge function requires the BTRFS datastore. */
function functionRequiresDatastore(functionName: string): boolean {
  if (!(functionName in FUNCTION_REQUIREMENTS)) return false;
  const reqs = FUNCTION_REQUIREMENTS[functionName as RenetFunctionName];
  return reqs.requirements.repository === true;
}

/**
 * Verify that a remote machine has completed `renet setup`.
 * Checks for the setup marker file and BTRFS datastore via SSH.
 * Only enforced for functions that require the `repository` requirement
 * (backup, snapshot, repo operations). System and admin functions
 * (machine_ping, setup_machine, machine_uninstall, etc.) skip verification
 * so they can operate on machines regardless of setup state.
 * Bypass with REDIACC_SKIP_SETUP_CHECK=1 environment variable.
 */
export async function verifyMachineSetup(
  machine: MachineConfig,
  sshPrivateKey: string,
  options: Pick<RenetSpawnOptions, 'debug'> & { functionName?: string },
  sharedSftp?: SFTPClient
): Promise<void> {
  if (process.env.REDIACC_SKIP_SETUP_CHECK) return;

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

  // Persistent-state second: a recent rdc process may have verified setup on
  // this machine already — skip both SSH round-trips (marker + btrfs check).
  if (await isSetupVerifiedFresh(cacheKey).catch(() => false)) {
    setupCache.set(cacheKey, Date.now());
    return;
  }

  await withSharedOrPooledSftp(
    sharedSftp,
    sftpConfigForMachine(machine, sshPrivateKey),
    async (sftp) => {
      const result = await sftp.exec(`test -f ${SETUP_MARKER_PATH} && echo OK || echo MISSING`);
      if (result.trim() !== 'OK') {
        throw new Error(
          `Machine '${machine.ip}' has not been set up. ` +
            `Run 'rdc machine setup <name>' or 'sudo renet setup --auto' directly on the machine.`
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
            `Run 'rdc machine setup <name>' to initialize the BTRFS datastore.`
        );
      }

      setupCache.set(cacheKey, Date.now());
      // Best-effort cross-process memo (annotates the provision entry only).
      await recordSetupVerified(cacheKey).catch(() => undefined);
      if (options.debug) {
        outputService.info(`Setup verified on ${machine.ip}`);
      }
    }
  );
}

interface RepoEntryConfig {
  guid: string;
  name: string;
  networkId?: number;
  /**
   * File-mode secrets to materialize on the host at deploy time. Renet's
   * repository_up reads these from the vault payload and writes them to
   * /var/run/rediacc/secrets/<networkID>/<NAME>. Tmpfs only; never enters
   * the LUKS image; never inherited by forks.
   */
  secretFiles?: { name: string; value: string }[];
}

interface BuildLocalVaultOptions {
  functionName: string;
  machineName: string;
  machine: MachineConfig;
  sshPrivateKey: string;
  sshPublicKey: string;
  sshKnownHosts: string;
  params: Record<string, unknown>;
  extraMachines?: Record<string, { ip: string; port?: number; user: string; datastore?: string }>;
  storages?: Record<string, { vaultContent: Record<string, unknown> }>;
  repositoryCredentials?: Record<string, string>;
  repositoryConfigs?: Record<string, RepoEntryConfig>;
}

function buildExtraMachines(
  machines:
    | Record<string, { ip: string; port?: number; user: string; datastore?: string }>
    | undefined,
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
      datastore: cfg.datastore ?? NETWORK_DEFAULTS.DATASTORE_PATH,
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

/** Build a single repository entry from config and params. */
function buildSingleRepoEntry(
  repoName: string,
  params: Record<string, unknown>,
  repositoryConfigs?: Record<string, RepoEntryConfig>
): Record<string, unknown> {
  const repoConfig = repositoryConfigs?.[repoName];
  const repoEntry: Record<string, unknown> = {
    guid: repoConfig?.guid ?? (typeof params.guid === 'string' ? params.guid : repoName),
    name: repoName,
  };
  const networkId = repoConfig?.networkId ?? params.network_id;
  if (networkId !== undefined && networkId !== '' && networkId !== 0) {
    repoEntry.network_id = typeof networkId === 'number' ? networkId : Number(networkId);
  }
  if (repoConfig?.secretFiles && repoConfig.secretFiles.length > 0) {
    repoEntry.secret_files = repoConfig.secretFiles;
  }
  return repoEntry;
}

/** Build repository entries for all repos in config (multi-repo mode). */
function buildAllRepoEntries(
  repositoryConfigs: Record<string, RepoEntryConfig>
): Record<string, unknown> {
  const repositories: Record<string, unknown> = {};
  for (const [name, config] of Object.entries(repositoryConfigs)) {
    const repoEntry: Record<string, unknown> = {
      guid: config.guid,
      name,
    };
    if (config.networkId !== undefined && config.networkId !== 0) {
      repoEntry.network_id = config.networkId;
    }
    if (config.secretFiles && config.secretFiles.length > 0) {
      repoEntry.secret_files = config.secretFiles;
    }
    repositories[name] = repoEntry;
  }
  return repositories;
}

function buildRepositories(
  params: Record<string, unknown>,
  repositoryConfigs?: Record<string, RepoEntryConfig>
): { repoName: string; repositories: Record<string, unknown> } {
  const repoName = (params.repository ?? '') as string;

  if (repoName) {
    return {
      repoName,
      repositories: { [repoName]: buildSingleRepoEntry(repoName, params, repositoryConfigs) },
    };
  }

  if (repositoryConfigs) {
    return { repoName, repositories: buildAllRepoEntries(repositoryConfigs) };
  }

  return { repoName, repositories: {} };
}

/**
 * Build RenetVault structure for local/s3 execution.
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
