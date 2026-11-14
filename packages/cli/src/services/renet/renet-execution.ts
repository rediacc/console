/**
 * Shared renet execution utilities.
 * Extracted from local-executor.ts for reuse across the CLI's executors.
 */

import { execSync } from 'node:child_process';
import * as fsSync from 'node:fs';
import * as path from 'node:path';
import { DEFAULTS, NETWORK_DEFAULTS, PROCESS_DEFAULTS } from '@rediacc/shared/config';
import { STATUS_DEFAULTS } from '@rediacc/shared/config/defaults';
import type { RenetFunctionName } from '@rediacc/shared/renet-contract/data/functions.generated';
import { FUNCTION_REQUIREMENTS } from '@rediacc/shared/renet-contract/data/functions.generated';
import type { SFTPClient } from '../../remote/sftp/index.js';
import { EXIT_CODES, type MachineConfig } from '../../types/index.js';
import { CliExitError } from '../../utils/cli-exit-error.js';
import { askConfirm } from '../../utils/prompt.js';
import { reportStateWriteRefused } from '../config/state-write-failure.js';
import { isSEA } from '../core/embedded-assets.js';
import { outputService } from '../core/output.js';
import type { ExtraMachine } from '../executor/types.js';
import { sftpConfigForMachine, withSharedOrPooledSftp } from '../machine/machine-connection.js';
import { isSetupVerifiedFresh, recordSetupVerified } from './provision-state.js';
import {
  assertRenetSourceClean,
  gitOut,
  renetSourceState,
  selectRenetUploadBinary,
} from './renet-clean-build.js';
import type { RenetDrift } from './renet-inspect.js';
import { renetProvisioner } from './renet-provisioner.js';
import {
  inExecutor,
  mayOfferReplacement,
  type RenetHold,
  renetHold,
  renetMayUpload,
} from './renet-upload-decision.js';
import { buildRepositories, type RepoEntryConfig } from './renet-vault-sections.js';

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
 * to replace the production binary. An executor gets `'read-only'` whatever it
 * asks for: {@link inExecutor}.
 */
export type RenetAccess = 'read-only' | 'provision';

export interface RenetAcquireResult {
  remotePath: string;
  uploaded: boolean;
  /** Drift seen by a read-only probe; null for provision, which removes it. */
  drift: RenetDrift | null;
  /** A router refresh the caller deferred (`deferRouterRefresh`) and still owes. */
  routerRefreshDue?: boolean;
}

/** Hosts already warned about drift in this process (one line per host). */
const driftWarned = new Set<string>();

function shortHash(hash: string | null): string {
  return hash ? hash.slice(0, 12) : STATUS_DEFAULTS.UNKNOWN_PLACEHOLDER;
}

/** The last sentence of the drift warning: who may replace the remote renet, and how. */
function driftRemedy(machineName: string, executor: boolean, held: RenetHold): string {
  if (executor) {
    return `An executor never replaces it: run 'rdc machine setup ${machineName}' without --proxy to update it.`;
  }
  if (held === 'env') {
    return `REDIACC_NO_PROVISION=1 holds it: run 'rdc machine setup ${machineName}' to update it.`;
  }
  if (held === 'dev') {
    return `A development build does not replace it as a side effect: run 'rdc machine setup ${machineName}' to update it.`;
  }
  return `Run 'rdc machine setup ${machineName}' or any mutating command to update it.`;
}

async function acquireReadOnly(
  machine: MachineConfig,
  machineName: string,
  sshPrivateKey: string,
  localBinaryPath: string | undefined,
  sftp?: SFTPClient,
  held: RenetHold = null
): Promise<RenetAcquireResult> {
  const executor = inExecutor();
  const inspected = await renetProvisioner.inspect(
    sftpConfigForMachine(machine, sshPrivateKey),
    { localBinaryPath, ...(executor && { fresh: true }) },
    sftp
  );
  if (inspected.drift === 'missing' || inspected.remotePath === null) {
    if (executor) {
      throw new CliExitError(
        'RENET_NOT_ON_MACHINE',
        `renet is not installed on ${machineName}, and an executor never installs it. Run 'rdc machine setup ${machineName}' without --proxy to provision it.`,
        { exitCode: EXIT_CODES.STATE_MISMATCH }
      );
    }
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
          driftRemedy(machineName, executor, held)
      );
    }
  }
  return { remotePath: inspected.remotePath, uploaded: false, drift: inspected.drift };
}

/** Answers already given this process, per host: a verb that connects twice asks once. */
const replacementAnswers = new Map<string, boolean>();

/** The renet source commit behind a local binary, or null when it sits outside a git work tree. */
function localRenetCommit(localBinaryPath: string | undefined): string | null {
  if (localBinaryPath === undefined) return null;
  try {
    const state = renetSourceState(localBinaryPath);
    return state === null ? null : gitOut(['rev-parse', 'HEAD'], state.top);
  } catch {
    return null;
  }
}

/**
 * Ask whether a development build may replace the machine's renet, naming the remote build and the local
 * commit. No question when nothing differs or renet is absent (the read-only path reports that).
 */
async function confirmReplacement(
  machine: MachineConfig,
  machineName: string,
  sshPrivateKey: string,
  localBinaryPath: string | undefined,
  sftp?: SFTPClient
): Promise<boolean> {
  const hostKey = `${machine.ip}:${machine.port ?? DEFAULTS.SSH.PORT}`;
  const known = replacementAnswers.get(hostKey);
  if (known !== undefined) return known;
  const inspected = await renetProvisioner.inspect(
    sftpConfigForMachine(machine, sshPrivateKey),
    { localBinaryPath },
    sftp
  );
  if (
    inspected.drift === 'none' ||
    inspected.drift === 'missing' ||
    inspected.remotePath === null
  ) {
    return false;
  }
  const commit = localRenetCommit(localBinaryPath);
  const answer = await askConfirm(
    `renet on ${machineName} is v${inspected.remoteVersion ?? STATUS_DEFAULTS.UNKNOWN_PLACEHOLDER} build ${shortHash(inspected.remoteHash)}; this development build has renet commit ${commit === null ? STATUS_DEFAULTS.UNKNOWN_PLACEHOLDER : commit.slice(0, 12)} (build ${shortHash(inspected.localHash)}). Replace the remote renet with it?`,
    false
  );
  replacementAnswers.set(hostKey, answer);
  return answer;
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
    /** Report the owed router refresh as `routerRefreshDue` instead of running it. */
    deferRouterRefresh?: boolean;
    /** Name used in operator-facing messages; defaults to the machine IP. */
    machineName?: string;
    /** `rdc machine setup` itself: provisions even under REDIACC_NO_PROVISION=1 ({@link renetHold}). */
    explicitSetup?: boolean;
  },
  sftp?: SFTPClient
): Promise<RenetAcquireResult> {
  let localBinaryPath: string | undefined;
  if (!isSEA()) {
    localBinaryPath = resolveRenetPath(config.renetPath);
  }
  const machineName = options.machineName ?? machine.ip;

  const held = options.explicitSetup === true ? null : renetHold();
  let mayUpload = renetMayUpload(access, options.explicitSetup);
  if (!mayUpload && mayOfferReplacement(access, options.explicitSetup)) {
    mayUpload = await confirmReplacement(
      machine,
      machineName,
      sshPrivateKey,
      localBinaryPath,
      sftp
    );
  }
  if (!mayUpload) {
    return acquireReadOnly(machine, machineName, sshPrivateKey, localBinaryPath, sftp, held);
  }

  // After a binary update an active rediacc-router is re-installed from the new binary (`renet proxy install`, which re-renders its unit) and restarted, so it runs the new code under the new unit text; see RenetProvisionerService.restartRunningServices. A machine whose router is not running is left alone. Opt out via skipRouterRestart=true or
  // REDIACC_SKIP_ROUTER_RESTART=1.
  const skipRestart = options.skipRouterRestart ?? !!process.env.REDIACC_SKIP_ROUTER_RESTART;
  const restartServices = skipRestart ? false : (options.restartServices ?? true);
  const selection =
    localBinaryPath === undefined ? null : await selectRenetUploadBinary(localBinaryPath);
  const uploadPath = selection?.localBinaryPath ?? localBinaryPath;

  const start = Date.now();
  const result = await renetProvisioner.provision(
    sftpConfigForMachine(machine, sshPrivateKey),
    {
      localBinaryPath: uploadPath,
      restartServices,
      deferRouterRefresh: options.deferRouterRefresh,
      debug: options.debug,
      ...(selection?.guarded === true && {
        uploadGuard: () => assertRenetSourceClean(selection.localBinaryPath, machine),
      }),
    },
    sftp
  );
  const elapsed = ((Date.now() - start) / 1000).toFixed(1);

  if (!result.success) {
    const message = result.error ?? PROCESS_DEFAULTS.RENET_PROVISION_ERROR;
    if (result.code) {
      throw new CliExitError(result.code, message, { exitCode: EXIT_CODES.STATE_MISMATCH });
    }
    throw new Error(message);
  }

  if (result.action === 'uploaded') {
    outputService.info(`Renet updated on ${machine.ip} (${result.arch}) in ${elapsed}s`);
    if (selection?.cleanCommit) {
      outputService.info(
        `Uploaded renet built from committed HEAD ${selection.cleanCommit.slice(0, 12)}; ${selection.excludedPaths} uncommitted path(s) in the renet working tree were not included`
      );
    }
    if (result.servicesRestarted) {
      outputService.info(`Restarted rediacc-router on ${machine.ip}`);
    }
  } else if (options.debug) {
    outputService.info(`Renet verified on ${machine.ip} (${elapsed}s)`);
  }

  return {
    remotePath: result.remotePath,
    uploaded: result.action === 'uploaded',
    drift: null,
    routerRefreshDue: result.routerRefreshDue === true,
  };
}

/** Check whether a renet function requires the BTRFS datastore. */
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
      await recordSetupVerified(cacheKey).catch(reportStateWriteRefused);
      if (options.debug) {
        outputService.info(`Setup verified on ${machine.ip}`);
      }
    }
  );
}

interface BuildLocalVaultOptions {
  functionName: string;
  machineName: string;
  machine: MachineConfig;
  sshPrivateKey: string;
  sshPublicKey: string;
  sshKnownHosts: string;
  params: Record<string, unknown>;
  extraMachines?: Record<string, ExtraMachine>;
  repositoryCredentials?: Record<string, string>;
  repositoryConfigs?: Record<string, RepoEntryConfig>;
}

function buildExtraMachines(
  machines: Record<string, ExtraMachine> | undefined,
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
      known_hosts: cfg.knownHosts ?? '',
      ssh: {
        private_key: sshPrivateKey,
        public_key: sshPublicKey,
      },
    };
  }
  return result;
}

/**
 * Build RenetVault structure for local/s3 execution.
 */
export function buildLocalVault(opts: BuildLocalVaultOptions): string {
  const extraMachines = buildExtraMachines(
    opts.extraMachines,
    opts.sshPrivateKey,
    opts.sshPublicKey
  );
  const { repoGuid, repoName, repositories } = buildRepositories(
    opts.params,
    opts.repositoryConfigs
  );

  const vault = {
    $schema: 'queue-vault-v2',
    version: '2.0',
    task: {
      function: opts.functionName,
      machine: opts.machineName,
      team: 'local',
      repository: repoGuid,
      ...(repoName ? { repo_name: repoName } : {}),
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
