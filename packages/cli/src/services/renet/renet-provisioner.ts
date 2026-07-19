/**
 * Renet Provisioner - Remote binary provisioning via SFTP
 *
 * Provisions the appropriate renet binary to remote Linux machines
 * before execution. Handles architecture detection, verification, and caching.
 *
 * Installs renet to a versioned path under /usr/lib/rediacc/renet so
 * multiple CLI versions can coexist on the same remote machine.
 */

import * as fs from 'node:fs/promises';
import * as os from 'node:os';
import * as path from 'node:path';
import { DEFAULTS } from '@rediacc/shared/config';
import type { SFTPClient, SFTPClientConfig } from '../../remote/sftp/index.js';
import { VERSION } from '../../version.js';
import {
  computeSha256,
  getEmbeddedRenetBinary,
  isSEA,
  type RenetArch,
} from '../core/embedded-assets.js';
import { busy, type CliExitError } from '../../utils/cli-exit-error.js';
import { formatDuration } from '../../utils/format.js';
import { shellQuote } from '../../utils/shell-quote.js';
import { updateSpinnerText } from '../../utils/spinner.js';
import {
  acquireLocalLock,
  type LockHolder,
  LockTimeoutError,
  releaseLocalLock,
} from '../core/file-lock.js';
import { outputService } from '../core/output.js';
import { withSharedOrPooledSftp } from '../machine/machine-connection.js';
import { compareVersions } from '../update/updater.js';
import { stageRenetBinary } from './renet-binary-transfer.js';

/** Root directory for versioned renet installs on remote machines */
const REMOTE_INSTALL_ROOT = '/usr/lib/rediacc/renet';
const REMOTE_CURRENT_DIR = `${REMOTE_INSTALL_ROOT}/current`;
const REMOTE_CURRENT_PATH = `${REMOTE_CURRENT_DIR}/renet`;

/** Default renet binary path on remote machines (for ad-hoc invocations). */
export const REMOTE_RENET_PATH = REMOTE_CURRENT_PATH;

/**
 * Version-specific install path used by `provisionRenetToRemote` as the
 * committed binary location. Exported so the backup reconciler's dry-run
 * can match the exact ExecStart= path a real deploy would write.
 */
export const REMOTE_INSTALL_PATH = `${REMOTE_INSTALL_ROOT}/${VERSION}/renet`;

/** Prefix for per-attempt staging uploads (no sudo needed for /tmp) */
const STAGING_PATH_PREFIX = '/tmp/.rdc-staging-renet';

/** Remote host-scoped lock file for install/restart critical section */
const REMOTE_LOCK_PATH = '/tmp/.rdc-renet-provision.lock';

/** flock's `-E` exit status, chosen outside anything the install body emits. */
const REMOTE_FLOCK_TIMEOUT_EXIT = 75;

/** Cache TTL in milliseconds (1 hour) */
const CACHE_TTL_MS = 60 * 60 * 1000;
const DEFAULT_LOCAL_LOCK_TIMEOUT_MS = 2 * 60 * 1000;
const MIN_LOCAL_LOCK_TIMEOUT_MS = 1_000;
const MAX_LOCAL_LOCK_TIMEOUT_MS = 10 * 60 * 1000;
const LOCAL_LOCK_POLL_MS = 250;

/**
 * How long to queue behind another local rdc process before refusing.
 *
 * Two minutes is sized for a genuine cold provision (a binary upload plus remote
 * install), not for impatience: a shorter budget would start failing runs that
 * were about to succeed. An env override exists for unusual links; there is no
 * CLI flag, because a knob almost nobody turns is not worth 13 locales and a
 * contract regeneration.
 */
function localLockTimeoutMs(): number {
  const raw = Number(process.env.REDIACC_PROVISION_LOCK_TIMEOUT_MS);
  if (!Number.isFinite(raw) || raw <= 0) return DEFAULT_LOCAL_LOCK_TIMEOUT_MS;
  return Math.min(Math.max(raw, MIN_LOCAL_LOCK_TIMEOUT_MS), MAX_LOCAL_LOCK_TIMEOUT_MS);
}

/** Describe a lock holder for a human: "pid 1234, held 2m 4s, running `rdc backup run`". */
function describeHolder(holder: LockHolder): string {
  const parts = [holder.pid === null ? 'unknown pid' : `pid ${holder.pid}`];
  if (holder.heldForMs !== null) parts.push(`held ${formatDuration(holder.heldForMs)}`);
  if (holder.command) parts.push(`running \`${holder.command}\``);
  return parts.join(', ');
}

/**
 * Tell the operator they are queued, the moment we know it.
 *
 * Prefers retitling the live spinner, so the wait replaces the misleading
 * "Provisioning renet" text rather than scrolling past it. With no TTY there is
 * no spinner to retitle, so fall back to a single stderr note (stderr keeps JSON
 * output on stdout clean).
 */
function announceLockWait(cacheKey: string, holder: LockHolder): void {
  const message = `Waiting for another rdc process to finish provisioning renet for ${cacheKey} (${describeHolder(holder)})`;
  if (!updateSpinnerText(`${message}...`)) outputService.info(message);
}

/** Turn a provisioning-lock timeout into an actionable BUSY refusal. */
function lockBusyError(cacheKey: string, error: LockTimeoutError): CliExitError {
  const { holder } = error;
  const details = [`Lock: ${error.lockPath}`];
  if (holder.command) details.push(`Holder: ${holder.command}`);

  return busy(
    `Another rdc process is still provisioning renet for ${cacheKey} (${describeHolder(holder)}).`,
    {
      details,
      next: {
        summary: 'Wait for the other run to finish, then retry. Clear the lock only if it is dead.',
        options: [
          ...(holder.pid === null
            ? []
            : [
                {
                  description: 'Inspect the process holding the lock',
                  run: `ps -p ${holder.pid} -o pid,etime,cmd`,
                },
              ]),
          {
            description: 'Remove the lock if that process is gone',
            run: `rm -rf ${error.lockPath}`,
          },
        ],
      },
    }
  );
}

/** Systemd service name for the route server */
const ROUTER_SERVICE = 'rediacc-router';

/** Result of a provisioning operation */
interface ProvisionResult {
  /** Whether provisioning succeeded */
  success: boolean;
  /** Action taken: uploaded new binary, verified existing, or failed */
  action: 'uploaded' | 'verified' | 'failed' | 'version_rejected';
  /** Detected architecture (undefined if detection failed) */
  arch?: RenetArch;
  /** Error message if failed */
  error?: string;
  /** Whether running services were restarted after binary update */
  servicesRestarted?: boolean;
  /** Exact remote binary path that was verified or installed */
  remotePath: string;
}

/** Cache entry for a provisioned host */
interface CacheEntry {
  hash: string;
  arch: RenetArch;
  provisionedAt: number;
}

/** Memoized SHA256 of a local binary, keyed by file identity */
interface LocalHashMemo {
  mtimeMs: number;
  size: number;
  hash: string;
}

interface InstallResult {
  binaryUpdated: boolean;
  currentUpdated: boolean;
}

interface ProvisionContext {
  arch: RenetArch;
  binary: Buffer;
  localHash: string;
  cacheKey: string;
  remoteInstallPath: string;
}

/**
 * Service for provisioning renet binaries to remote Linux machines.
 *
 * Works in both SEA and dev modes:
 * - SEA mode: extracts binary from embedded assets
 * - Dev mode: reads binary from a local file path
 *
 * Installation flow:
 * 1. Compute SHA256 of local binary
 * 2. Single SSH call: `renet hash` + `renet version` (sha256sum fallback)
 * 3. If hash mismatch + version guard passes: SFTP upload to staging, atomic mv to the versioned install path
 *
 * Maintains an in-memory cache to avoid redundant checks within TTL.
 */
class RenetProvisionerService {
  private readonly cache = new Map<string, CacheEntry>();
  private readonly inflight = new Map<string, Promise<ProvisionResult>>();
  /** Per-host arch memo so partial cache misses skip the remote `uname -m` exec */
  private readonly archByHost = new Map<string, RenetArch>();
  /** Local binary hash memo keyed by source path, validated by (mtime, size) */
  private readonly localHashMemo = new Map<string, LocalHashMemo>();
  /** Embedded (SEA) binary hash memo keyed by arch; embedded assets are immutable per process */
  private readonly embeddedHashMemo = new Map<RenetArch, string>();

  /**
   * Provision renet to a remote Linux machine.
   *
   * @param config - SFTP connection configuration
   * @param options - Optional provisioning options
   * @param options.localBinaryPath - Dev mode: read binary from this local file
   * @returns Provision result with action taken
   */
  async provision(
    config: SFTPClientConfig,
    options?: {
      localBinaryPath?: string;
      /** Restart running services after binary update. Default: false. */
      restartServices?: boolean;
      debug?: boolean;
    },
    sharedSftp?: SFTPClient
  ): Promise<ProvisionResult> {
    const cacheKey = this.buildCacheKey(config);
    // Cache-first: a fresh entry means this process already provisioned the
    // host. Return immediately with zero remote execs and zero local file reads.
    const cached = this.getFreshCacheEntry(cacheKey);
    if (cached) {
      return this.buildVerifiedResult(cached.arch, REMOTE_INSTALL_PATH);
    }

    const inflight = this.inflight.get(cacheKey);
    if (inflight) {
      return inflight;
    }

    const provisioningPromise = this.withLocalProvisionLock(cacheKey, () =>
      this.provisionInternal(config, options, sharedSftp)
    );
    this.inflight.set(cacheKey, provisioningPromise);

    try {
      return await provisioningPromise;
    } finally {
      if (this.inflight.get(cacheKey) === provisioningPromise) {
        this.inflight.delete(cacheKey);
      }
    }
  }

  private async provisionInternal(
    config: SFTPClientConfig,
    options?: {
      localBinaryPath?: string;
      restartServices?: boolean;
      debug?: boolean;
    },
    sharedSftp?: SFTPClient
  ): Promise<ProvisionResult> {
    try {
      return await withSharedOrPooledSftp(sharedSftp, config, (sftp) =>
        this.doProvision(sftp, config, options)
      );
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      return {
        success: false,
        action: 'failed',
        remotePath: REMOTE_INSTALL_PATH,
        error: `Failed to provision renet: ${errorMessage}`,
      };
    }
  }

  /** Core provisioning logic after connection is established. */
  private async doProvision(
    sftp: SFTPClient,
    config: SFTPClientConfig,
    options?: { localBinaryPath?: string; restartServices?: boolean; debug?: boolean }
  ): Promise<ProvisionResult> {
    const context = await this.buildProvisionContext(sftp, config, options?.localBinaryPath);
    const remote = await this.getRemoteHashAndVersion(sftp, context.remoteInstallPath);
    const versionRejected = this.buildVersionRejectedResult(remote.version, context);
    if (versionRejected) return versionRejected;

    const stagingPath = this.buildStagingPath();
    if (remote.hash !== context.localHash) {
      await stageRenetBinary(sftp, config, stagingPath, context.binary, context.localHash, {
        installRoot: REMOTE_INSTALL_ROOT,
        currentPath: REMOTE_CURRENT_PATH,
      });
    }
    if (options?.debug) {
      outputService.info(`Activating remote renet slot ${context.remoteInstallPath}...`);
    }
    const installResult = await this.installWithRemoteLock(
      sftp,
      stagingPath,
      context.localHash,
      context.remoteInstallPath
    );
    this.logInstallResult(config.host, installResult, options?.debug === true);

    // Best-effort: restart route server so it picks up the new binary
    let servicesRestarted = false;
    if (options?.restartServices === true && installResult.currentUpdated) {
      servicesRestarted = await this.restartRunningServices(sftp);
    }

    this.cache.set(context.cacheKey, {
      hash: context.localHash,
      arch: context.arch,
      provisionedAt: Date.now(),
    });
    return {
      success: true,
      action: installResult.binaryUpdated ? 'uploaded' : 'verified',
      arch: context.arch,
      servicesRestarted,
      remotePath: context.remoteInstallPath,
    };
  }

  private async buildProvisionContext(
    sftp: SFTPClient,
    config: SFTPClientConfig,
    localBinaryPath?: string
  ): Promise<ProvisionContext> {
    const remoteInstallPath = REMOTE_INSTALL_PATH;
    const cacheKey = this.buildCacheKey(config);
    const arch = await this.resolveArch(sftp, cacheKey);
    const { binary, sourcePath } = await this.resolveBinary(arch, localBinaryPath);
    return {
      arch,
      binary,
      localHash: await this.computeLocalHash(arch, binary, sourcePath),
      cacheKey,
      remoteInstallPath,
    };
  }

  private buildCacheKey(config: SFTPClientConfig): string {
    return `${config.host}:${config.port ?? DEFAULTS.SSH.PORT}`;
  }

  private getFreshCacheEntry(cacheKey: string): CacheEntry | null {
    const cached = this.cache.get(cacheKey);
    if (cached && Date.now() - cached.provisionedAt < CACHE_TTL_MS) {
      return cached;
    }
    return null;
  }

  /** Resolve the remote arch, preferring the per-host memo over a remote exec. */
  private async resolveArch(sftp: SFTPClient, cacheKey: string): Promise<RenetArch> {
    const memoized = this.archByHost.get(cacheKey);
    if (memoized) {
      return memoized;
    }
    const arch = await this.detectArch(sftp);
    this.archByHost.set(cacheKey, arch);
    return arch;
  }

  /**
   * Compute the local binary's SHA256, memoized so repeat misses don't re-hash.
   * File-based binaries are keyed by source path and validated by (mtime, size);
   * embedded SEA binaries are keyed by arch (immutable within a process).
   */
  private async computeLocalHash(
    arch: RenetArch,
    binary: Buffer,
    sourcePath: string | null
  ): Promise<string> {
    if (sourcePath === null) {
      const memoized = this.embeddedHashMemo.get(arch);
      if (memoized) {
        return memoized;
      }
      const hash = computeSha256(binary);
      this.embeddedHashMemo.set(arch, hash);
      return hash;
    }

    const stat = await fs.stat(sourcePath);
    const memoized = this.localHashMemo.get(sourcePath);
    if (memoized?.mtimeMs === stat.mtimeMs && memoized.size === stat.size) {
      return memoized.hash;
    }
    const hash = computeSha256(binary);
    this.localHashMemo.set(sourcePath, { mtimeMs: stat.mtimeMs, size: stat.size, hash });
    return hash;
  }

  private buildVerifiedResult(arch: RenetArch, remoteInstallPath: string): ProvisionResult {
    return { success: true, action: 'verified', arch, remotePath: remoteInstallPath };
  }

  private buildVersionRejectedResult(
    remoteVersion: string | null,
    context: ProvisionContext
  ): ProvisionResult | null {
    const isDowngrade = remoteVersion && compareVersions(VERSION, remoteVersion) < 0;
    if (!isDowngrade || process.env.RDC_ALLOW_DOWNGRADE) {
      return null;
    }

    return {
      success: false,
      action: 'version_rejected',
      arch: context.arch,
      remotePath: context.remoteInstallPath,
      error: `Remote has renet v${remoteVersion} but this CLI bundles v${VERSION}. Run \`rdc update\` to upgrade your CLI, or set RDC_ALLOW_DOWNGRADE=1 to force.`,
    };
  }

  private logInstallResult(host: string, installResult: InstallResult, debug: boolean): void {
    if (!debug) {
      return;
    }

    if (installResult.binaryUpdated || installResult.currentUpdated) {
      outputService.info(
        `Remote renet ready on ${host} (${installResult.binaryUpdated ? 'slot updated' : 'slot verified'}${installResult.currentUpdated ? ', current updated' : ''})`
      );
      return;
    }

    outputService.info(`Remote renet already current on ${host}`);
  }

  /**
   * Get the binary data from either embedded assets or a local file.
   * On non-Linux platforms, resolves the cross-compiled Linux binary
   * (e.g. renet-linux-amd64) instead of the local platform binary.
   * Returns the resolved source path (null for embedded SEA assets) so
   * the hash memo can be keyed by file identity.
   */
  private async resolveBinary(
    arch: RenetArch,
    localBinaryPath?: string
  ): Promise<{ binary: Buffer; sourcePath: string | null }> {
    if (isSEA()) {
      return { binary: getEmbeddedRenetBinary('linux', arch), sourcePath: null };
    }

    if (localBinaryPath) {
      // On non-Linux hosts, the localBinaryPath points to the host platform binary
      // (e.g. renet.exe on Windows). Look for the cross-compiled Linux binary instead.
      if (process.platform !== 'linux') {
        const dir = path.dirname(localBinaryPath);
        const linuxBinaryPath = path.join(dir, `renet-linux-${arch}`);
        try {
          return { binary: await fs.readFile(linuxBinaryPath), sourcePath: linuxBinaryPath };
        } catch {
          throw new Error(
            `Cross-compiled Linux binary not found at ${linuxBinaryPath}. ` +
              'Rebuild renet with ./rdc.sh or ./build.sh dev to generate Linux binaries.'
          );
        }
      }
      return { binary: await fs.readFile(localBinaryPath), sourcePath: localBinaryPath };
    }

    throw new Error('Cannot provision renet: not running as SEA and no localBinaryPath provided');
  }

  /**
   * Detect the remote machine's architecture.
   * Uses `uname -m` output which is reliable across all Linux distributions.
   */
  private async detectArch(sftp: SFTPClient): Promise<RenetArch> {
    try {
      // uname -m returns the machine hardware name, which is the most reliable
      // cross-distribution method for architecture detection:
      // - x86_64 for AMD64/Intel 64-bit
      // - aarch64 for ARM64
      const arch = await sftp.exec('uname -m');
      const archStr = arch.trim().toLowerCase();

      if (archStr === 'aarch64' || archStr === 'arm64') {
        return 'arm64';
      }
      // Default to amd64 for x86_64 and any other architecture
      return 'amd64';
    } catch {
      // If exec fails (e.g., restricted shell), fall back to filesystem detection
      // Check multiple paths that indicate ARM64 across different distros:
      // - /lib/aarch64-linux-gnu: Debian/Ubuntu multiarch
      // - /lib64/ld-linux-aarch64.so.1: RHEL/CentOS/Fedora ARM64 dynamic linker
      const arm64Paths = ['/lib/aarch64-linux-gnu', '/lib64/ld-linux-aarch64.so.1'];
      for (const p of arm64Paths) {
        if (await sftp.exists(p)) {
          return 'arm64';
        }
      }
      return 'amd64';
    }
  }

  /**
   * Get the remote binary's hash and version in a single SSH call.
   * Returns hash (for content comparison) and version (for downgrade guard).
   * Uses `renet hash` + `renet version` combined, with sha256sum fallback.
   */
  private async getRemoteHashAndVersion(
    sftp: SFTPClient,
    remoteInstallPath: string
  ): Promise<{ hash: string | null; version: string | null }> {
    try {
      const escapedInstallPath = shellQuote(remoteInstallPath);
      // Single SSH exec: get both hash and version. Two lines of output.
      // Falls back to sha256sum if `renet hash` isn't available (pre-0.6.0).
      const output = await sftp.exec(
        `(${escapedInstallPath} hash 2>/dev/null || sha256sum ${escapedInstallPath} | cut -d' ' -f1) && ${escapedInstallPath} version 2>/dev/null || true`
      );
      const lines = output.trim().split('\n');
      const hash = lines[0]?.trim().split(/\s+/)[0] ?? null;
      const versionMatch = /\d+\.\d+\.\d+/.exec(lines.slice(1).join(' '));
      return { hash, version: versionMatch ? versionMatch[0] : null };
    } catch {
      // Binary doesn't exist or exec failed — needs install, no version to guard
      return { hash: null, version: null };
    }
  }

  /**
   * Restart services that use the renet binary, if they are currently running.
   * Returns true if any service was restarted.
   */
  private async restartRunningServices(sftp: SFTPClient): Promise<boolean> {
    try {
      // Only restart if the service is active — is-active returns non-zero otherwise,
      // so the && short-circuits and || true ensures the command always succeeds.
      const output = await sftp.exec(
        `sudo systemctl is-active --quiet ${ROUTER_SERVICE} && sudo systemctl restart ${ROUTER_SERVICE} && echo RESTARTED || true`
      );
      return output.trim().includes('RESTARTED');
    } catch {
      return false;
    }
  }

  /**
   * Clear the in-memory caches (provision results, arch memos, hash memos).
   * Useful for testing or forcing re-verification.
   */
  clearCache(): void {
    this.cache.clear();
    this.archByHost.clear();
    this.localHashMemo.clear();
    this.embeddedHashMemo.clear();
  }

  private async withLocalProvisionLock<T>(cacheKey: string, fn: () => Promise<T>): Promise<T> {
    const lockPath = path.join(
      os.tmpdir(),
      `.rdc-renet-provision-${cacheKey.replaceAll(/[^a-zA-Z0-9_.-]/g, '_')}.lock`
    );

    try {
      await acquireLocalLock(lockPath, {
        deadline: Date.now() + localLockTimeoutMs(),
        pollMs: LOCAL_LOCK_POLL_MS,
        // Contention is INVISIBLE without this: the operator sees the
        // "Provisioning renet" spinner sit there and reasonably concludes the
        // CLI has hung, when in fact another local rdc run is ahead of them.
        onWait: (holder) => announceLockWait(cacheKey, holder),
      });
    } catch (error) {
      if (error instanceof LockTimeoutError) throw lockBusyError(cacheKey, error);
      throw error;
    }

    try {
      return await fn();
    } finally {
      await releaseLocalLock(lockPath);
    }
  }

  private buildStagingPath(): string {
    const timestamp = Date.now();
    const random = Math.random().toString(16).slice(2, 10);
    return `${STAGING_PATH_PREFIX}-${process.pid}-${timestamp}-${random}`;
  }

  private async installWithRemoteLock(
    sftp: SFTPClient,
    stagingPath: string,
    localHash: string,
    remoteInstallPath: string
  ): Promise<InstallResult> {
    try {
      const output = await sftp.exec(
        this.buildLockedInstallCommand(stagingPath, localHash, remoteInstallPath)
      );
      const trimmed = output.trim();
      const statusTokens = new Set(trimmed.split(/\s+/).filter(Boolean));
      const binaryUpdated = statusTokens.has('UPDATED');
      const currentUpdated = statusTokens.has('CURRENT_UPDATED') || binaryUpdated;
      if (binaryUpdated || statusTokens.has('VERIFIED') || statusTokens.has('CURRENT_UPDATED')) {
        return { binaryUpdated, currentUpdated };
      }
      throw new Error(`Unexpected provisioning result: ${trimmed || '(empty output)'}`);
    } catch (error) {
      try {
        await sftp.exec(`rm -f ${stagingPath}`);
      } catch {
        // Best-effort cleanup only.
      }
      if (error instanceof Error && error.message.includes('FLOCK_MISSING')) {
        throw new Error(
          "Remote machine is missing 'flock', which is required for safe concurrent renet provisioning"
        );
      }
      if (error instanceof Error && error.message.includes('FLOCK_TIMEOUT')) {
        // The competing process may belong to a different workstation entirely,
        // so unlike the local lock there is no pid worth naming here.
        throw busy(
          `Another process on the machine held the renet install lock for over 120s, so provisioning was skipped.`,
          {
            details: [`Lock: ${REMOTE_LOCK_PATH}`],
            next: {
              summary: 'Wait for the other provisioning run to finish, then retry.',
              options: [
                {
                  description: 'Find the process holding the remote lock',
                  run: `rdc term connect <machine> -c "fuser -v ${REMOTE_LOCK_PATH}"`,
                },
              ],
            },
          }
        );
      }
      throw error;
    }
  }

  private buildLockedInstallCommand(
    stagingPath: string,
    localHash: string,
    remoteInstallPath: string
  ): string {
    const escapedHash = shellQuote(localHash);
    const escapedStagingPath = shellQuote(stagingPath);
    const escapedInstallPath = shellQuote(remoteInstallPath);
    const escapedLockPath = shellQuote(REMOTE_LOCK_PATH);
    const escapedInstallDir = shellQuote(path.dirname(remoteInstallPath));
    const escapedCurrentDir = shellQuote(REMOTE_CURRENT_DIR);
    const escapedCurrentPath = shellQuote(REMOTE_CURRENT_PATH);
    const escapedCurrentTmpPath = shellQuote(`${REMOTE_CURRENT_PATH}.tmp`);

    const body = [
      // Execute under POSIX sh on remote hosts; do not rely on bash-only options.
      'set -eu',
      `hash_remote() { (${escapedInstallPath} hash 2>/dev/null || sha256sum ${escapedInstallPath} | cut -d' ' -f1) 2>/dev/null || true; }`,
      `current_target() { readlink ${escapedCurrentPath} 2>/dev/null || true; }`,
      'result=',
      `sudo mkdir -p ${escapedInstallDir}`,
      `sudo mkdir -p ${escapedCurrentDir}`,
      `if [ "$(hash_remote)" = ${escapedHash} ]; then rm -f ${escapedStagingPath}; else sudo chmod 755 ${escapedStagingPath}; sudo mv -f ${escapedStagingPath} ${escapedInstallPath}; result=UPDATED; fi`,
      `if [ "$(current_target)" != ${escapedInstallPath} ]; then sudo ln -sfn ${escapedInstallPath} ${escapedCurrentTmpPath}; sudo mv -Tf ${escapedCurrentTmpPath} ${escapedCurrentPath}; if [ -n "$result" ]; then result="$result CURRENT_UPDATED"; else result=CURRENT_UPDATED; fi; fi`,
      // Ensure /usr/bin/renet symlinks to current so "sudo renet" always resolves to the provisioned binary
      `if [ ! -L /usr/bin/renet ] || [ "$(readlink /usr/bin/renet)" != ${escapedCurrentPath} ]; then sudo ln -sf ${escapedCurrentPath} /usr/bin/renet; fi`,
      'if [ -z "$result" ]; then result=VERIFIED; fi',
      'echo "$result"',
    ].join('; ');
    const quotedBody = shellQuote(body);
    // `-E ${REMOTE_FLOCK_TIMEOUT_EXIT}` gives the lock-not-acquired case its own
    // exit status. Without it flock exits 1, which the install body can also
    // produce, so a machine busy with another operator's provision was reported
    // as "Unexpected provisioning result: (empty output)" and looked like a
    // broken install. -E is util-linux >= 2.20 (2011); the probe above still
    // only checks for flock's presence, and an -E-less flock fails loudly rather
    // than silently mis-reporting.
    return `command -v flock >/dev/null 2>&1 || { echo FLOCK_MISSING >&2; exit 127; }; flock -w 120 -E ${REMOTE_FLOCK_TIMEOUT_EXIT} ${escapedLockPath} sh -c ${quotedBody} || { rc=$?; [ "$rc" = ${REMOTE_FLOCK_TIMEOUT_EXIT} ] && echo FLOCK_TIMEOUT >&2; exit "$rc"; }`;
  }
}

export const renetProvisioner = new RenetProvisionerService(); // singleton
