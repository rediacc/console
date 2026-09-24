/**
 * Shared renet execution utilities.
 * Extracted from local-executor.ts for reuse across the CLI's executors.
 */

import { execFileSync, execSync } from 'node:child_process';
import * as fsSync from 'node:fs';
import * as path from 'node:path';
import { DEFAULTS, NETWORK_DEFAULTS, PROCESS_DEFAULTS } from '@rediacc/shared/config';
import { STATUS_DEFAULTS } from '@rediacc/shared/config/defaults';
import type { RenetFunctionName } from '@rediacc/shared/renet-contract/data/functions.generated';
import { FUNCTION_REQUIREMENTS } from '@rediacc/shared/renet-contract/data/functions.generated';
import type { SFTPClient } from '../../remote/sftp/index.js';
import type { MachineConfig } from '../../types/index.js';
import { isSEA } from '../core/embedded-assets.js';
import { outputService } from '../core/output.js';
import { sftpConfigForMachine, withSharedOrPooledSftp } from '../machine/machine-connection.js';
import type { RenetDrift } from './renet-inspect.js';
import { renetProvisioner } from './renet-provisioner.js';
import { isSetupVerifiedFresh, recordSetupVerified } from './provision-state.js';

// The SSH key helpers moved to services/machine/ssh-key.ts so the connection pool can read a team key without importing renet. Re-exported here: this module is where the rest of the CLI has always imported them from.
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
  // Absolute path, verify it exists before using it
  if (path.isAbsolute(configuredPath)) {
    try {
      fsSync.accessSync(configuredPath);
      return configuredPath;
    } catch {
      // Fall through to PATH lookup
    }
  }

  // Bare name or missing absolute, resolve via PATH (handles .exe on Windows)
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
 * What a caller is allowed to do to the machine's renet.
 *
 * - `'read-only'`: inspect the remote binary and run it as-is. Never uploads,
 *   never repoints `current` or `/usr/bin/renet`, never restarts a service.
 *   Drift is a warning; only a missing binary fails.
 * - `'provision'`: upload the local binary when it differs, activate it and
 *   restart `rediacc-router` (unless opted out).
 *
 * Required at every call site: a default is how every read-only verb once came
 * to replace the production binary.
 */
export type RenetAccess = 'read-only' | 'provision';

export interface RenetAcquireResult {
  remotePath: string;
  uploaded: boolean;
  /** Drift seen by a read-only probe; null for provision, which removes it. */
  drift: RenetDrift | null;
}

/** Hosts already warned about drift in this process (one line per host). */
const driftWarned = new Set<string>();

/** Maximum dirty paths named in the refusal. */
const DIRTY_PATHS_SHOWN = 10;

/**
 * Refuse to upload a renet binary built from a dirty source tree, unless
 * REDIACC_ALLOW_DIRTY_RENET=1. A binary outside a git work tree (a release
 * binary on PATH) is allowed. Untracked files count: Go compiles untracked .go
 * files, and `bin/` is gitignored so the binary itself never shows up.
 */
export function assertRenetSourceClean(localBinaryPath: string, machine: MachineConfig): void {
  if (process.env.REDIACC_ALLOW_DIRTY_RENET === '1') return;
  let top: string;
  try {
    top = execFileSync(
      'git',
      ['-C', path.dirname(localBinaryPath), 'rev-parse', '--show-toplevel'],
      { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'ignore'] }
    ).trim();
  } catch {
    return;
  }
  if (!top) return;
  const porcelain = execFileSync('git', ['-C', top, 'status', '--porcelain'], {
    encoding: 'utf-8',
    stdio: ['ignore', 'pipe', 'ignore'],
  });
  const dirty = porcelain.split('\n').filter((line) => line.trim() !== '');
  if (dirty.length === 0) return;
  const shown = dirty.slice(0, DIRTY_PATHS_SHOWN).map((line) => `  ${line}`);
  if (dirty.length > DIRTY_PATHS_SHOWN) {
    shown.push(`  ... and ${dirty.length - DIRTY_PATHS_SHOWN} more`);
  }
  throw new Error(
    `Refusing to upload renet to ${machine.ip}: the binary was built from a dirty tree at ${top}.\n` +
      `${shown.join('\n')}\n` +
      'Commit the renet change first, or set REDIACC_ALLOW_DIRTY_RENET=1 to upload it anyway.'
  );
}

function shortHash(hash: string | null): string {
  return hash ? hash.slice(0, 12) : STATUS_DEFAULTS.UNKNOWN_PLACEHOLDER;
}

async function acquireReadOnly(
  machine: MachineConfig,
  machineName: string,
  sshPrivateKey: string,
  localBinaryPath: string | undefined,
  sftp?: SFTPClient
): Promise<RenetAcquireResult> {
  const inspected = await renetProvisioner.inspect(
    sftpConfigForMachine(machine, sshPrivateKey),
    { localBinaryPath },
    sftp
  );
  if (inspected.drift === 'missing' || inspected.remotePath === null) {
    throw new Error(
      `renet is not installed on ${machineName}; run 'rdc machine setup ${machineName}' to provision it`
    );
  }
  if (inspected.drift !== 'none') {
    const hostKey = `${machine.ip}:${machine.port ?? DEFAULTS.SSH.PORT}`;
    if (!driftWarned.has(hostKey)) {
      driftWarned.add(hostKey);
      outputService.warn(
        `renet on ${machineName} differs from this CLI (remote v${inspected.remoteVersion ?? STATUS_DEFAULTS.UNKNOWN_PLACEHOLDER} ${shortHash(inspected.remoteHash)}, ` +
          `local v${inspected.localVersion} ${shortHash(inspected.localHash)}); running the remote binary as-is. ` +
          `Run 'rdc machine setup ${machineName}' or any mutating command to update it.`
      );
    }
  }
  return { remotePath: inspected.remotePath, uploaded: false, drift: inspected.drift };
}

/**
 * Resolve the renet binary to run on a remote machine.
 *
 * `access` is required and positional on purpose: see {@link RenetAccess}.
 */
export async function acquireRemoteRenet(
  access: RenetAccess,
  config: { renetPath: string },
  machine: MachineConfig,
  sshPrivateKey: string,
  options: Pick<RenetSpawnOptions, 'debug' | 'skipRouterRestart'> & {
    restartServices?: boolean;
    /** Name used in operator-facing messages; defaults to the machine IP. */
    machineName?: string;
  },
  sftp?: SFTPClient
): Promise<RenetAcquireResult> {
  let localBinaryPath: string | undefined;
  if (!isSEA()) {
    localBinaryPath = resolveRenetPath(config.renetPath);
  }
  const machineName = options.machineName ?? machine.ip;

  if (access === 'read-only') {
    return acquireReadOnly(machine, machineName, sshPrivateKey, localBinaryPath, sftp);
  }

  // Auto-restart rediacc-router after a binary update so the long-running router daemon picks up new code without manual `systemctl restart`. systemctl try-restart is a no-op when the unit is not running, so this is safe on machines without the
  // router daemon. Opt out via skipRouterRestart=true or
  // REDIACC_SKIP_ROUTER_RESTART=1.
  const skipRestart = options.skipRouterRestart ?? !!process.env.REDIACC_SKIP_ROUTER_RESTART;
  const restartServices = skipRestart ? false : (options.restartServices ?? true);
  const guardPath = localBinaryPath;

  const start = Date.now();
  const result = await renetProvisioner.provision(
    sftpConfigForMachine(machine, sshPrivateKey),
    {
      localBinaryPath,
      restartServices,
      debug: options.debug,
      ...(guardPath !== undefined && {
        uploadGuard: () => assertRenetSourceClean(guardPath, machine),
      }),
    },
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

  return { remotePath: result.remotePath, uploaded: result.action === 'uploaded', drift: null };
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

  // Only verify setup for functions that require the BTRFS datastore. System functions (machine_ping, machine_version, setup_machine, machine_install, machine_uninstall, etc.) must work on machines regardless of setup state.
  const needsDatastore = options.functionName
    ? functionRequiresDatastore(options.functionName)
    : true;
  if (!needsDatastore) return;

  const cacheKey = `${machine.ip}:${machine.port ?? DEFAULTS.SSH.PORT}`;
  const cached = setupCache.get(cacheKey);
  if (cached && Date.now() - cached < SETUP_CACHE_TTL_MS) return;

  // Persistent-state second: a recent rdc process may have verified setup on this machine already, skip both SSH round-trips (marker + btrfs check).
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
      // Use multiple detection methods matching the Go bridge's approach: 1. findmnt (preferred), 2. stat -f, 3. /proc/mounts grep
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
