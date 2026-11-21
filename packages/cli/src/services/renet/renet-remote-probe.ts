/**
 * What the provisioner asks a machine over one SFTP exec session: its architecture and the hash and version of a
 * renet binary on it. Split out of renet-provisioner.ts, which keeps the install and the cache.
 */
import type { SFTPClient } from '../../remote/sftp/index.js';
import { shellQuote } from '../../utils/shell-quote.js';
import type { RenetArch } from '../core/embedded-assets.js';

/** x.y.z with its suffix, so a dev build stays visible as one. */
const VERSION_WITH_SUFFIX = /\d+\.\d+\.\d+(?:-[0-9A-Za-z][0-9A-Za-z.-]*)?/;

/**
 * Detect the remote machine's architecture.
 * Uses `uname -m` output which is reliable across all Linux distributions.
 */
export async function detectRemoteArch(sftp: SFTPClient): Promise<RenetArch> {
  try {
    // uname -m returns the machine hardware name, which is the most reliable cross-distribution method for architecture detection: - x86_64 for AMD64/Intel 64-bit - aarch64 for ARM64
    const arch = await sftp.exec('uname -m');
    const archStr = arch.trim().toLowerCase();

    if (archStr === 'aarch64' || archStr === 'arm64') {
      return 'arm64';
    }
    // Default to amd64 for x86_64 and any other architecture
    return 'amd64';
  } catch {
    // If exec fails (e.g., restricted shell), fall back to filesystem detection Check multiple paths that indicate ARM64 across different distros: - /lib/aarch64-linux-gnu: Debian/Ubuntu multiarch - /lib64/ld-linux-aarch64.so.1: RHEL/CentOS/Fedora ARM64 dynamic linker
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
 * The version keeps its suffix, since `-dev` is what marks a dev build. With
 * `strict`, a failed exec throws instead of reading as an absent binary.
 */
export async function getRemoteHashAndVersion(
  sftp: SFTPClient,
  remoteInstallPath: string,
  options?: { strict?: boolean }
): Promise<{ hash: string | null; version: string | null }> {
  try {
    const escapedInstallPath = shellQuote(remoteInstallPath);
    // Single SSH exec: get both hash and version. Two lines of output. Falls back to sha256sum if `renet hash` isn't available (pre-0.6.0).
    const output = await sftp.exec(
      `(${escapedInstallPath} hash 2>/dev/null || sha256sum ${escapedInstallPath} | cut -d' ' -f1) && ${escapedInstallPath} version 2>/dev/null || true`
    );
    const lines = output.trim().split('\n');
    const hash = lines[0]?.trim().split(/\s+/)[0] ?? null;
    const versionMatch = VERSION_WITH_SUFFIX.exec(lines.slice(1).join(' '));
    return { hash, version: versionMatch ? versionMatch[0] : null };
  } catch (error) {
    if (options?.strict === true) throw error;
    // Binary doesn't exist or exec failed, needs install, no version to guard
    return { hash: null, version: null };
  }
}
