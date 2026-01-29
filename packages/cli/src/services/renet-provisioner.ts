/**
 * Renet Provisioner - Remote binary provisioning via SFTP
 *
 * Provisions the appropriate renet binary to remote Linux machines
 * before execution. Handles architecture detection, verification, and caching.
 */

import { SFTPClient, type SFTPClientConfig } from '@rediacc/shared-desktop/sftp';
import { DEFAULTS } from '@rediacc/shared/config';
import {
  isSEA,
  getEmbeddedRenetBinary,
  getEmbeddedMetadata,
  computeSha256,
  type LinuxArch,
} from './embedded-assets.js';

/** Default remote path for provisioned renet binary */
const DEFAULT_REMOTE_PATH = '/tmp/.rdc/renet';

/** Cache TTL in milliseconds (1 hour) */
const CACHE_TTL_MS = 60 * 60 * 1000;

/** Result of a provisioning operation */
export interface ProvisionResult {
  /** Whether provisioning succeeded */
  success: boolean;
  /** Action taken: uploaded new binary, verified existing, skipped (not SEA), or failed */
  action: 'uploaded' | 'verified' | 'skipped' | 'failed';
  /** Remote path where renet is available */
  remotePath: string;
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
 * When running as SEA, extracts the appropriate architecture binary
 * from embedded assets and uploads via SFTP. Uses a verification flow:
 * 1. Check if remote binary exists
 * 2. Compare size with expected
 * 3. Compare SHA256 hash with expected
 * 4. Upload only if verification fails
 *
 * Maintains an in-memory cache to avoid redundant checks within TTL.
 */
class RenetProvisionerService {
  private readonly cache = new Map<string, CacheEntry>();

  /**
   * Provision renet to a remote Linux machine
   *
   * @param config - SFTP connection configuration
   * @param remotePath - Remote path for the binary (default: /tmp/.rdc/renet)
   * @returns Provision result with action taken
   */
  async provision(
    config: SFTPClientConfig,
    remotePath = DEFAULT_REMOTE_PATH
  ): Promise<ProvisionResult> {
    // Not running as SEA - use local renet path
    if (!isSEA()) {
      return { success: true, action: 'skipped', remotePath: 'renet', arch: 'amd64' };
    }

    const sftp = new SFTPClient(config);

    try {
      await sftp.connect();

      // Detect remote architecture
      const arch = await this.detectArch(sftp);
      const metadata = getEmbeddedMetadata().binaries[arch];

      // Check in-memory cache
      const cacheKey = `${config.host}:${config.port ?? DEFAULTS.SSH.PORT}`;
      const cached = this.cache.get(cacheKey);
      if (cached?.hash === metadata.sha256 && Date.now() - cached.provisionedAt < CACHE_TTL_MS) {
        return { success: true, action: 'skipped', remotePath, arch };
      }

      // Verify remote binary
      const needsUpload = await this.needsUpload(sftp, remotePath, metadata);

      if (!needsUpload) {
        this.cache.set(cacheKey, { hash: metadata.sha256, provisionedAt: Date.now() });
        return { success: true, action: 'verified', remotePath, arch };
      }

      // Extract and upload binary
      const binary = getEmbeddedRenetBinary(arch);
      const parentDir = remotePath.substring(0, remotePath.lastIndexOf('/'));
      await sftp.mkdirRecursive(parentDir);
      await sftp.writeFile(remotePath, binary);
      await sftp.chmod(remotePath, 0o755);

      this.cache.set(cacheKey, { hash: metadata.sha256, provisionedAt: Date.now() });
      return { success: true, action: 'uploaded', remotePath, arch };
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      return {
        success: false,
        action: 'failed',
        remotePath,
        error: `Failed to provision renet: ${errorMessage}`,
      };
    } finally {
      sftp.close();
    }
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
      for (const path of arm64Paths) {
        if (await sftp.exists(path)) {
          return 'arm64';
        }
      }
      return 'amd64';
    }
  }

  /**
   * Check if the remote binary needs to be uploaded.
   * Verifies existence, size, and SHA256 hash.
   */
  private async needsUpload(
    sftp: SFTPClient,
    path: string,
    expected: { size: number; sha256: string }
  ): Promise<boolean> {
    try {
      // Check existence
      if (!(await sftp.exists(path))) {
        return true;
      }

      // Check size first (fast check)
      const stat = await sftp.stat(path);
      if (stat.size !== expected.size) {
        return true;
      }

      // Verify SHA256 hash (slow but thorough)
      const content = await sftp.readFile(path);
      return computeSha256(content) !== expected.sha256;
    } catch {
      // Any error means we need to upload
      return true;
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
