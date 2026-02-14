/**
 * Renet Provisioner - Remote binary provisioning via SFTP
 *
 * Provisions the appropriate renet binary to remote Linux machines
 * before execution. Handles architecture detection, verification, and caching.
 *
 * Installs renet to /usr/bin/renet (canonical path) so that `sudo renet`
 * works without PATH issues. Uses a staging upload to /tmp then sudo cp.
 */

import * as fs from 'node:fs/promises';
import { SFTPClient, type SFTPClientConfig } from '@rediacc/shared-desktop/sftp';
import { DEFAULTS } from '@rediacc/shared/config';
import { isSEA, getEmbeddedRenetBinary, computeSha256, type LinuxArch } from './embedded-assets.js';
import { compareVersions } from './updater.js';
import { VERSION } from '../version.js';

/** Canonical install path on remote machines */
const REMOTE_INSTALL_PATH = '/usr/bin/renet';

/** Staging path for SFTP upload (no sudo needed for /tmp) */
const STAGING_PATH = '/tmp/.rdc-staging-renet';

/** Cache TTL in milliseconds (1 hour) */
const CACHE_TTL_MS = 60 * 60 * 1000;

/** Result of a provisioning operation */
export interface ProvisionResult {
  /** Whether provisioning succeeded */
  success: boolean;
  /** Action taken: uploaded new binary, verified existing, or failed */
  action: 'uploaded' | 'verified' | 'failed' | 'version_rejected';
  /** Detected architecture (undefined if detection failed) */
  arch?: LinuxArch;
  /** Error message if failed */
  error?: string;
}

/** Cache entry for a provisioned host */
interface CacheEntry {
  hash: string;
  provisionedAt: number;
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
 * 2. Check remote /usr/bin/renet via sha256sum
 * 3. If mismatch: SFTP upload to staging path, sudo cp to /usr/bin/renet
 *
 * Maintains an in-memory cache to avoid redundant checks within TTL.
 */
class RenetProvisionerService {
  private readonly cache = new Map<string, CacheEntry>();

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
    }
  ): Promise<ProvisionResult> {
    const sftp = new SFTPClient(config);

    try {
      await sftp.connect();

      // Detect remote architecture
      const arch = await this.detectArch(sftp);

      // Get binary data from the appropriate source
      const binary = await this.getBinary(arch, options?.localBinaryPath);
      const localHash = computeSha256(binary);

      // Check in-memory cache
      const cacheKey = `${config.host}:${config.port ?? DEFAULTS.SSH.PORT}`;
      const cached = this.cache.get(cacheKey);
      if (cached?.hash === localHash && Date.now() - cached.provisionedAt < CACHE_TTL_MS) {
        return { success: true, action: 'verified', arch };
      }

      // Check remote binary via sha256sum
      const needsInstall = await this.needsInstall(sftp, localHash);

      if (!needsInstall) {
        this.cache.set(cacheKey, { hash: localHash, provisionedAt: Date.now() });
        return { success: true, action: 'verified', arch };
      }

      // Version guard: prevent accidental downgrade unless explicitly allowed
      if (!process.env.RDC_ALLOW_DOWNGRADE) {
        const remoteVersion = await this.getRemoteVersion(sftp);
        if (remoteVersion && compareVersions(VERSION, remoteVersion) < 0) {
          return {
            success: false,
            action: 'version_rejected',
            arch,
            error: `Remote has renet v${remoteVersion} but this CLI bundles v${VERSION}. Run \`rdc update\` to upgrade your CLI, or set RDC_ALLOW_DOWNGRADE=1 to force.`,
          };
        }
      }

      // Stage and install: SFTP upload to /tmp, then atomic mv to /usr/bin/renet.
      // Uses mv (not cp) so the replacement works even when the binary is running
      // (e.g., during a backup sync). mv replaces the directory entry atomically;
      // the old inode stays alive until the running process exits.
      await sftp.writeFile(STAGING_PATH, binary);
      await sftp.exec(
        `sudo chmod 755 ${STAGING_PATH} && sudo mv -f ${STAGING_PATH} ${REMOTE_INSTALL_PATH}`
      );

      this.cache.set(cacheKey, { hash: localHash, provisionedAt: Date.now() });
      return { success: true, action: 'uploaded', arch };
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      return {
        success: false,
        action: 'failed',
        error: `Failed to provision renet: ${errorMessage}`,
      };
    } finally {
      sftp.close();
    }
  }

  /**
   * Get the binary data from either embedded assets or a local file.
   */
  private async getBinary(arch: LinuxArch, localBinaryPath?: string): Promise<Buffer> {
    if (isSEA()) {
      return getEmbeddedRenetBinary(arch);
    }

    if (localBinaryPath) {
      return fs.readFile(localBinaryPath);
    }

    throw new Error('Cannot provision renet: not running as SEA and no localBinaryPath provided');
  }

  /**
   * Detect the remote machine's architecture.
   * Uses `uname -m` output which is reliable across all Linux distributions.
   */
  private async detectArch(sftp: SFTPClient): Promise<LinuxArch> {
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
   * Check if the remote binary needs to be installed.
   * Uses sha256sum on the remote to compare with expected hash.
   */
  private async needsInstall(sftp: SFTPClient, expectedHash: string): Promise<boolean> {
    try {
      const output = await sftp.exec(`sha256sum ${REMOTE_INSTALL_PATH}`);
      // sha256sum output format: "<hash>  <path>"
      const remoteHash = output.trim().split(/\s+/)[0];
      return remoteHash !== expectedHash;
    } catch {
      // Binary doesn't exist or sha256sum failed — needs install
      return true;
    }
  }

  /**
   * Get the version of the renet binary currently on the remote machine.
   * Returns null if the binary doesn't exist, can't execute, or version
   * can't be parsed (in all these cases, we allow overwriting).
   */
  private async getRemoteVersion(sftp: SFTPClient): Promise<string | null> {
    try {
      const output = await sftp.exec(`${REMOTE_INSTALL_PATH} version`);
      // Version output is i18n-localized but semver is always present.
      // Examples: "renet version 0.5.0", "renet版本 0.5.0", "renet sürümü 0.5.0"
      const match = output.match(/\d+\.\d+\.\d+/);
      return match ? match[0] : null;
    } catch {
      // Binary missing, corrupted, or can't execute — allow overwrite
      return null;
    }
  }

  /**
   * Clear the in-memory cache.
   * Useful for testing or forcing re-verification.
   */
  clearCache(): void {
    this.cache.clear();
  }
}

/** Singleton instance of the renet provisioner */
export const renetProvisioner = new RenetProvisionerService();
