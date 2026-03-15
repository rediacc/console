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
import { SFTPClient, type SFTPClientConfig } from '@rediacc/shared-desktop/sftp';
import { createTempSSHKeyFile, removeTempSSHKeyFile } from '@rediacc/shared-desktop/ssh';
import { executeRsync, getRsyncCommand } from '@rediacc/shared-desktop/sync';
import { VERSION } from '../version.js';
import { computeSha256, getEmbeddedRenetBinary, isSEA, type RenetArch } from './embedded-assets.js';
import { outputService } from './output.js';
import { compareVersions } from './updater.js';

/** Root directory for versioned renet installs on remote machines */
const REMOTE_INSTALL_ROOT = '/usr/lib/rediacc/renet';
const REMOTE_CURRENT_DIR = `${REMOTE_INSTALL_ROOT}/current`;
const REMOTE_CURRENT_PATH = `${REMOTE_CURRENT_DIR}/renet`;

const REMOTE_INSTALL_PATH = `${REMOTE_INSTALL_ROOT}/${VERSION}/renet`;

/** Prefix for per-attempt staging uploads (no sudo needed for /tmp) */
const STAGING_PATH_PREFIX = '/tmp/.rdc-staging-renet';

/** Remote host-scoped lock file for install/restart critical section */
const REMOTE_LOCK_PATH = '/tmp/.rdc-renet-provision.lock';

/** Cache TTL in milliseconds (1 hour) */
const CACHE_TTL_MS = 60 * 60 * 1000;
const LOCAL_LOCK_TIMEOUT_MS = 2 * 60 * 1000;
const LOCAL_LOCK_POLL_MS = 250;

/** Systemd service name for the route server */
const ROUTER_SERVICE = 'rediacc-router';

/** Result of a provisioning operation */
export interface ProvisionResult {
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
  provisionedAt: number;
}

interface InstallResult {
  binaryUpdated: boolean;
  currentUpdated: boolean;
}

interface RemoteSeedCandidate {
  path: string;
  source: 'current' | 'slot';
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
    }
  ): Promise<ProvisionResult> {
    const cacheKey = `${config.host}:${config.port ?? DEFAULTS.SSH.PORT}`;
    const inflight = this.inflight.get(cacheKey);
    if (inflight) {
      return inflight;
    }

    const provisioningPromise = this.withLocalProvisionLock(cacheKey, () =>
      this.provisionInternal(config, options)
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
    }
  ): Promise<ProvisionResult> {
    const sftp = new SFTPClient(config);

    try {
      await sftp.connect();
      const context = await this.buildProvisionContext(sftp, config, options?.localBinaryPath);
      if (this.isCachedProvision(context.cacheKey, context.localHash)) {
        return this.buildVerifiedResult(context.arch, context.remoteInstallPath);
      }

      const remote = await this.getRemoteHashAndVersion(sftp, context.remoteInstallPath);
      const versionRejected = this.buildVersionRejectedResult(remote.version, context);
      if (versionRejected) {
        return versionRejected;
      }

      const stagingPath = this.buildStagingPath();
      if (remote.hash !== context.localHash) {
        await this.stageBinary(sftp, config, stagingPath, context.binary, context.localHash);
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

      // Restart the route server so it picks up the new binary.
      // Safe: the router is only a config provider (not in the data path).
      // Traefik keeps serving with last-known config during the ~1-2s restart.
      // Best-effort: don't fail provisioning if restart fails.
      let servicesRestarted = false;
      if (options?.restartServices === true && installResult.currentUpdated) {
        servicesRestarted = await this.restartRunningServices(sftp);
      }

      this.cache.set(context.cacheKey, { hash: context.localHash, provisionedAt: Date.now() });
      return {
        success: true,
        action: installResult.binaryUpdated ? 'uploaded' : 'verified',
        arch: context.arch,
        servicesRestarted,
        remotePath: context.remoteInstallPath,
      };
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      return {
        success: false,
        action: 'failed',
        remotePath: REMOTE_INSTALL_PATH,
        error: `Failed to provision renet: ${errorMessage}`,
      };
    } finally {
      sftp.close();
    }
  }

  private async buildProvisionContext(
    sftp: SFTPClient,
    config: SFTPClientConfig,
    localBinaryPath?: string
  ): Promise<ProvisionContext> {
    const remoteInstallPath = REMOTE_INSTALL_PATH;
    const arch = await this.detectArch(sftp);
    const binary = await this.getBinary(arch, localBinaryPath);
    return {
      arch,
      binary,
      localHash: computeSha256(binary),
      cacheKey: `${config.host}:${config.port ?? DEFAULTS.SSH.PORT}`,
      remoteInstallPath,
    };
  }

  private isCachedProvision(cacheKey: string, localHash: string): boolean {
    const cached = this.cache.get(cacheKey);
    return cached?.hash === localHash && Date.now() - cached.provisionedAt < CACHE_TTL_MS;
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
   */
  private async getBinary(arch: RenetArch, localBinaryPath?: string): Promise<Buffer> {
    if (isSEA()) {
      return getEmbeddedRenetBinary('linux', arch);
    }

    if (localBinaryPath) {
      return fs.readFile(localBinaryPath);
    }

    throw new Error('Cannot provision renet: not running as SEA and no localBinaryPath provided');
  }

  private async stageBinary(
    sftp: SFTPClient,
    config: SFTPClientConfig,
    stagingPath: string,
    binary: Buffer,
    localHash: string
  ): Promise<void> {
    const seedCandidate = await this.findRemoteSeedCandidate(sftp, REMOTE_INSTALL_PATH);
    const remoteRsyncPath = await this.getRemoteRsyncPath(sftp);
    if (
      await this.tryDeltaSyncStage(
        sftp,
        config,
        stagingPath,
        binary,
        localHash,
        seedCandidate,
        remoteRsyncPath
      )
    ) {
      return;
    }

    // Stage and install: SFTP upload to /tmp, then atomic mv to a versioned remote path.
    // Uses mv (not cp) so the replacement works even when the binary is running
    // (e.g., during a backup sync). mv replaces the directory entry atomically;
    // the old inode stays alive until the running process exits.
    outputService.info(`Uploading renet to ${config.host}...`);
    const uploadStart = Date.now();
    await sftp.writeFile(stagingPath, binary);
    outputService.info(
      `Uploaded renet to ${config.host} in ${((Date.now() - uploadStart) / 1000).toFixed(1)}s`
    );
  }

  private async tryDeltaSyncStage(
    sftp: SFTPClient,
    config: SFTPClientConfig,
    stagingPath: string,
    binary: Buffer,
    localHash: string,
    seedCandidate: RemoteSeedCandidate | null,
    remoteRsyncPath: string | null
  ): Promise<boolean> {
    if (seedCandidate === null || remoteRsyncPath === null || !(await this.hasLocalRsync())) {
      return false;
    }

    try {
      outputService.info(
        `Seeding remote renet from ${seedCandidate.source === 'current' ? 'current slot' : 'existing slot'}...`
      );
      await sftp.exec(
        `cp -f ${this.shellEscape(seedCandidate.path)} ${this.shellEscape(stagingPath)} && chmod 600 ${this.shellEscape(stagingPath)}`
      );
      outputService.info(`Syncing renet delta to ${config.host}...`);
      await this.deltaSyncBinary(config, binary, stagingPath, remoteRsyncPath);
      const stagedHash = await this.getRemoteFileHash(sftp, stagingPath);
      if (stagedHash !== localHash) {
        throw new Error(
          `Staged renet hash mismatch after rsync: expected ${localHash}, got ${stagedHash ?? 'none'}`
        );
      }
      return true;
    } catch (error) {
      outputService.info(`Falling back to full upload to ${config.host}...`);
      await this.cleanupStagingPath(sftp, stagingPath);
      if (process.env.RDC_DEBUG_RENET_PROVISION === '1') {
        outputService.info(
          `Delta sync fallback reason: ${error instanceof Error ? error.message : String(error)}`
        );
      }
      return false;
    }
  }

  private async cleanupStagingPath(sftp: SFTPClient, stagingPath: string): Promise<void> {
    try {
      await sftp.exec(`rm -f ${this.shellEscape(stagingPath)}`);
    } catch {
      // Best-effort cleanup only.
    }
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

  private async findRemoteSeedCandidate(
    sftp: SFTPClient,
    _remoteInstallPath: string
  ): Promise<RemoteSeedCandidate | null> {
    const currentTarget = (
      await sftp.exec(`readlink ${this.shellEscape(REMOTE_CURRENT_PATH)} 2>/dev/null || true`)
    ).trim();
    if (currentTarget) {
      return { path: currentTarget, source: 'current' };
    }

    const firstSlot = (
      await sftp.exec(
        `find ${this.shellEscape(REMOTE_INSTALL_ROOT)} -mindepth 2 -maxdepth 2 -type f -name renet 2>/dev/null | head -n 1`
      )
    ).trim();
    if (firstSlot) {
      return { path: firstSlot, source: 'slot' };
    }

    return null;
  }

  private async getRemoteRsyncPath(sftp: SFTPClient): Promise<string | null> {
    const output = await sftp.exec(
      'if command -v rsync >/dev/null 2>&1; then command -v rsync; elif [ -x /usr/local/bin/rsync-renet ]; then echo /usr/local/bin/rsync-renet; fi'
    );
    const rsyncPath = output.trim();
    return rsyncPath || null;
  }

  private async hasLocalRsync(): Promise<boolean> {
    try {
      await getRsyncCommand();
      return true;
    } catch {
      return false;
    }
  }

  private async deltaSyncBinary(
    config: SFTPClientConfig,
    binary: Buffer,
    stagingPath: string,
    remoteRsyncPath: string
  ): Promise<void> {
    const keyFilePath = await createTempSSHKeyFile(config.privateKey);
    const tempDir = await fs.mkdtemp(path.join(os.tmpdir(), 'rdc-renet-'));
    const localBinaryPath = path.join(tempDir, 'renet');

    try {
      await fs.writeFile(localBinaryPath, binary, { mode: 0o700 });
      const sshOptions = [
        '-o StrictHostKeyChecking=no',
        '-o UserKnownHostsFile=/dev/null',
        '-o IdentitiesOnly=yes',
        `-p ${config.port ?? DEFAULTS.SSH.PORT}`,
        `-i "${keyFilePath}"`,
      ].join(' ');
      const destination = `${config.username}@${config.host}:${stagingPath}`;
      const result = await executeRsync({
        sshOptions,
        source: localBinaryPath,
        destination,
        remoteRsyncPath,
      } as Parameters<typeof executeRsync>[0]);
      if (!result.success) {
        throw new Error(result.errors.join('\n') || 'rsync transfer failed');
      }
    } finally {
      await fs.rm(tempDir, { recursive: true, force: true });
      await removeTempSSHKeyFile(keyFilePath);
    }
  }

  private async getRemoteFileHash(sftp: SFTPClient, remotePath: string): Promise<string | null> {
    const output = await sftp.exec(
      `sha256sum ${this.shellEscape(remotePath)} 2>/dev/null | cut -d' ' -f1 || true`
    );
    const hash = output.trim();
    return hash || null;
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
      const escapedInstallPath = this.shellEscape(remoteInstallPath);
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
   * Clear the in-memory cache.
   * Useful for testing or forcing re-verification.
   */
  clearCache(): void {
    this.cache.clear();
  }

  private async withLocalProvisionLock<T>(cacheKey: string, fn: () => Promise<T>): Promise<T> {
    const lockPath = path.join(
      os.tmpdir(),
      `.rdc-renet-provision-${cacheKey.replaceAll(/[^a-zA-Z0-9_.-]/g, '_')}.lock`
    );

    await acquireLocalLock(lockPath, Date.now() + LOCAL_LOCK_TIMEOUT_MS);
    try {
      return await fn();
    } finally {
      await fs.rm(lockPath, { recursive: true, force: true });
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
      throw error;
    }
  }

  private buildLockedInstallCommand(
    stagingPath: string,
    localHash: string,
    remoteInstallPath: string
  ): string {
    const escapedHash = this.shellEscape(localHash);
    const escapedStagingPath = this.shellEscape(stagingPath);
    const escapedInstallPath = this.shellEscape(remoteInstallPath);
    const escapedLockPath = this.shellEscape(REMOTE_LOCK_PATH);
    const escapedInstallDir = this.shellEscape(path.dirname(remoteInstallPath));
    const escapedCurrentDir = this.shellEscape(REMOTE_CURRENT_DIR);
    const escapedCurrentPath = this.shellEscape(REMOTE_CURRENT_PATH);
    const escapedCurrentTmpPath = this.shellEscape(`${REMOTE_CURRENT_PATH}.tmp`);

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

    const quotedBody = this.shellEscape(body);
    return `command -v flock >/dev/null 2>&1 || { echo FLOCK_MISSING >&2; exit 127; }; flock -w 120 ${escapedLockPath} sh -c ${quotedBody}`;
  }

  private shellEscape(v: string): string {
    return `'${v.replaceAll("'", `'\\''`)}'`;
  }
}
const isLockAlreadyHeldError = (e: unknown): e is NodeJS.ErrnoException =>
  e instanceof Error && 'code' in e && e.code === 'EEXIST';
async function isLockStale(pidPath: string): Promise<boolean> {
  try {
    const pid = Number.parseInt((await fs.readFile(pidPath, 'utf-8')).trim(), 10);
    if (Number.isNaN(pid)) return true;
    process.kill(pid, 0); // signal 0: existence check, throws ESRCH if dead
    return false;
  } catch {
    return true;
  }
}
async function tryCreateLock(lockPath: string): Promise<boolean> {
  try {
    await fs.mkdir(lockPath);
    await fs.writeFile(path.join(lockPath, 'pid'), String(process.pid));
    return true;
  } catch (error) {
    if (!isLockAlreadyHeldError(error)) throw error;
    return false;
  }
}
async function acquireLocalLock(lockPath: string, deadline: number): Promise<void> {
  const pidPath = path.join(lockPath, 'pid');
  while (!(await tryCreateLock(lockPath))) {
    if (await isLockStale(pidPath)) {
      await fs.rm(lockPath, { recursive: true, force: true });
      continue;
    }
    if (Date.now() >= deadline) {
      throw new Error(`Timed out waiting for local renet provision lock: ${lockPath}`);
    }
    await new Promise((resolve) => setTimeout(resolve, LOCAL_LOCK_POLL_MS));
  }
}

export const renetProvisioner = new RenetProvisionerService(); // singleton
