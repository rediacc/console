/**
 * Shared renet execution utilities.
 * Extracted from local-executor.ts for reuse across the CLI's executors.
 */

import { execFileSync, execSync, spawn } from 'node:child_process';
import * as fsSync from 'node:fs';
import * as path from 'node:path';
import { DEFAULTS, NETWORK_DEFAULTS, PROCESS_DEFAULTS } from '@rediacc/shared/config';
import { STATUS_DEFAULTS } from '@rediacc/shared/config/defaults';
import type { RenetFunctionName } from '@rediacc/shared/renet-contract/data/functions.generated';
import { FUNCTION_REQUIREMENTS } from '@rediacc/shared/renet-contract/data/functions.generated';
import type { SFTPClient } from '../../remote/sftp/index.js';
import type { MachineConfig } from '../../types/index.js';
import { reportStateWriteRefused } from '../config/state-write-failure.js';
import { isSEA } from '../core/embedded-assets.js';
import { outputService } from '../core/output.js';
import { sftpConfigForMachine, withSharedOrPooledSftp } from '../machine/machine-connection.js';
import { isSetupVerifiedFresh, recordSetupVerified } from './provision-state.js';
import {
  CLEAN_BUILD_MARKER,
  cleanBuildEnv,
  cleanBuildFiles,
  cleanBuildMarker,
  cleanBuildRoot,
  copyEmbeddedAssets,
  isCompleteCleanBuild,
  pinCommittedEbpfObjects,
  pruneOtherCleanBuilds,
} from './renet-clean-build-fs.js';
import type { RenetDrift } from './renet-inspect.js';
import { renetProvisioner } from './renet-provisioner.js';
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
 * to replace the production binary.
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

/** Maximum dirty paths named in the refusal. */
const DIRTY_PATHS_SHOWN = 10;

/**
 * Refuse to upload a renet binary built from a dirty source tree, unless
 * REDIACC_ALLOW_DIRTY_RENET=1. A binary outside a git work tree (a release
 * binary on PATH) is allowed. Untracked files count: Go compiles untracked .go
 * files, and `bin/` is gitignored so the binary itself never shows up.
 *
 * A tree already dirty when provisioning starts never reaches this guard:
 * {@link selectRenetUploadBinary} swaps in a build of the committed HEAD. The guard
 * catches a tree that turned dirty after that choice, and binds callers that pass
 * the working-tree binary directly.
 */
export function assertRenetSourceClean(localBinaryPath: string, machine: MachineConfig): void {
  if (process.env.REDIACC_ALLOW_DIRTY_RENET === '1') return;
  const state = renetSourceState(localBinaryPath);
  if (state === null || state.dirty.length === 0) return;
  const { top, dirty } = state;
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

/**
 * The git work tree a local renet binary sits in and its `status --porcelain` lines, or null for
 * a binary outside any git work tree (a release binary on PATH).
 */
export function renetSourceState(localBinaryPath: string): { top: string; dirty: string[] } | null {
  let top: string;
  try {
    top = gitOut(['rev-parse', '--show-toplevel'], path.dirname(localBinaryPath));
  } catch {
    return null;
  }
  if (!top) return null;
  const porcelain = gitOut(['status', '--porcelain'], top);
  return { top, dirty: porcelain.split('\n').filter((line) => line.trim() !== '') };
}

function gitOut(args: string[], cwd: string): string {
  return execFileSync('git', ['-C', cwd, ...args], {
    encoding: 'utf-8',
    stdio: ['ignore', 'pipe', 'ignore'],
  }).trim();
}

/** The renet binary a provisioning call hands to the provisioner. */
export interface RenetUploadSelection {
  /** Host binary; the provisioner picks `renet-linux-<arch>` beside it for a foreign arch. */
  localBinaryPath: string;
  /** The committed renet HEAD this binary was built from instead of a dirty tree; null otherwise. */
  cleanCommit: string | null;
  /** Uncommitted paths left out of that build. */
  excludedPaths: number;
  /** Whether the dirty-tree upload guard applies (only to the working-tree binary). */
  guarded: boolean;
}

/** Process seams of the clean build; tests replace them, production uses the real tools. */
export interface RenetCleanBuildDeps {
  git: (args: string[], cwd: string) => string;
  /** Run renet's own `./build.sh dev` in `cwd`; build output goes to stderr. */
  build: (cwd: string, env: NodeJS.ProcessEnv) => Promise<void>;
  /** `go version -m <binary>` output. */
  goVersionM: (binary: string) => string;
}

const realCleanBuildDeps: RenetCleanBuildDeps = {
  git: gitOut,
  build: (cwd, env) =>
    new Promise((resolve, reject) => {
      // stdout is the CLI command's; build progress goes to stderr.
      // build.sh resolves against the child's cwd: a cwd-joined path would be resolved against cwd a second time when cwd is relative.
      const child = spawn('bash', ['build.sh', 'dev'], {
        cwd,
        env,
        stdio: ['ignore', 2, 2],
      });
      child.on('error', reject);
      child.on('close', (code) =>
        code === 0 ? resolve() : reject(new Error(`bash build.sh dev exited ${code} in ${cwd}`))
      );
    }),
  goVersionM: (binary) =>
    execFileSync('go', ['version', '-m', binary], {
      encoding: 'utf-8',
      stdio: ['ignore', 'pipe', 'pipe'],
    }),
};

/**
 * Pick the renet binary to upload. A dirty renet working tree no longer blocks the upload: the
 * binary is built from the committed HEAD in a scratch clone and THAT is uploaded, so another
 * session's uncommitted edits in private/renet cannot stop a production `rdc repo up` (2026-10-23,
 * the hostinger observability stack). REDIACC_ALLOW_DIRTY_RENET=1 still uploads the working-tree
 * build as it is.
 */
export async function selectRenetUploadBinary(
  localBinaryPath: string,
  deps: RenetCleanBuildDeps = realCleanBuildDeps
): Promise<RenetUploadSelection> {
  const asIs: RenetUploadSelection = {
    localBinaryPath,
    cleanCommit: null,
    excludedPaths: 0,
    guarded: true,
  };
  if (process.env.REDIACC_ALLOW_DIRTY_RENET === '1') return asIs;
  const state = renetSourceState(localBinaryPath);
  if (state === null || state.dirty.length === 0) return asIs;
  const commit = deps.git(['rev-parse', 'HEAD'], state.top);
  outputService.info(
    `renet working tree ${state.top} has ${state.dirty.length} uncommitted path(s); using a build of committed HEAD ${commit.slice(0, 12)} (local edits not included; REDIACC_ALLOW_DIRTY_RENET=1 uploads the working-tree build)`
  );
  const built = await buildRenetAtCommit(state.top, commit, deps);
  return {
    localBinaryPath: built,
    cleanCommit: commit,
    excludedPaths: state.dirty.length,
    guarded: false,
  };
}

/**
 * Build renet at `commit` with renet's own `./build.sh dev`, in a `git clone --shared` of `top`
 * (no worktree, nothing written to the source checkout), and return the host binary of the result.
 * Cached per commit under {@link cleanBuildRoot}; older commits' builds are pruned.
 *
 * The clone has its own `.git` directory, so Go stamps `vcs.revision=<commit>`; the stamp and a
 * clean clone are verified before the build is accepted. The gitignored embedded assets are copied
 * from the working tree; build.sh's receipt check restages them if HEAD's lockfile differs.
 */
export async function buildRenetAtCommit(
  top: string,
  commit: string,
  deps: RenetCleanBuildDeps = realCleanBuildDeps
): Promise<string> {
  const root = cleanBuildRoot(top, deps);
  const ext = process.platform === 'win32' ? '.exe' : '';
  const finalDir = path.join(root, commit);
  const hostBinary = path.join(finalDir, `renet${ext}`);
  const buildEnv = cleanBuildEnv(top);
  const keyed = Boolean(buildEnv.ACCOUNT_ED25519_PUBLIC_KEY);
  if (isCompleteCleanBuild(finalDir, commit, ext, keyed)) return hostBinary;

  fsSync.mkdirSync(root, { recursive: true });
  const work = path.join(root, `work-${commit.slice(0, 12)}-${process.pid}`);
  const stage = path.join(root, `stage-${commit.slice(0, 12)}-${process.pid}`);
  fsSync.rmSync(work, { recursive: true, force: true });
  fsSync.rmSync(stage, { recursive: true, force: true });
  try {
    deps.git(['clone', '--quiet', '--shared', '--no-checkout', top, work], root);
    deps.git(['-c', 'advice.detachedHead=false', 'switch', '--quiet', '--detach', commit], work);
    copyEmbeddedAssets(top, work);
    pinCommittedEbpfObjects(work);

    outputService.info(`Building renet ${commit.slice(0, 12)} from a clean clone...`);
    await deps.build(work, buildEnv);

    const left = deps.git(['status', '--porcelain'], work);
    if (left) {
      throw new Error(
        `The clean renet build of ${commit.slice(0, 12)} changed tracked files in its clone, so its stamp would be modified:\n${left}`
      );
    }
    fsSync.mkdirSync(stage);
    for (const name of cleanBuildFiles(ext)) {
      const built = path.join(work, 'bin', name);
      const info = deps.goVersionM(built);
      if (!info.includes(`vcs.revision=${commit}`) || !info.includes('vcs.modified=false')) {
        throw new Error(
          `The clean renet build ${built} does not carry vcs.revision=${commit} with vcs.modified=false`
        );
      }
      fsSync.renameSync(built, path.join(stage, name));
    }
    fsSync.writeFileSync(path.join(stage, CLEAN_BUILD_MARKER), cleanBuildMarker(commit, keyed));
    // A leftover directory (a cached build missing a binary, or a keyless one superseded by this keyed build) would make the rename fail with ENOTEMPTY on every run; a rename only ever publishes a whole directory, so what is there is stale.
    if (!isCompleteCleanBuild(finalDir, commit, ext, keyed)) {
      fsSync.rmSync(finalDir, { recursive: true, force: true });
    }
    try {
      fsSync.renameSync(stage, finalDir);
    } catch (err) {
      // A concurrent process finished the same commit first; its build is as good as ours.
      if (!isCompleteCleanBuild(finalDir, commit, ext, keyed)) throw err;
    }
    pruneOtherCleanBuilds(root, commit);
  } finally {
    fsSync.rmSync(work, { recursive: true, force: true });
    fsSync.rmSync(stage, { recursive: true, force: true });
  }
  return hostBinary;
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
    /** Report the owed router refresh as `routerRefreshDue` instead of running it. */
    deferRouterRefresh?: boolean;
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
    throw new Error(result.error ?? PROCESS_DEFAULTS.RENET_PROVISION_ERROR);
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
  extraMachines?: Record<string, { ip: string; port?: number; user: string; datastore?: string }>;
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
