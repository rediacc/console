/**
 * The renet binary the provisioner sends to a machine (split out of renet-provisioner.ts, which the line budget
 * holds under 512 lines).
 */
import * as fs from 'node:fs/promises';
import * as path from 'node:path';
import { getEmbeddedRenetBinary, isSEA, type RenetArch } from '../core/embedded-assets.js';

/**
 * Get the binary data from either embedded assets or a local file.
 * On non-Linux platforms, resolves the cross-compiled Linux binary
 * (e.g. renet-linux-amd64) instead of the local platform binary.
 * Returns the resolved source path (null for embedded SEA assets) so
 * the hash memo can be keyed by file identity.
 */
export async function resolveRenetBinary(
  arch: RenetArch,
  localBinaryPath?: string
): Promise<{ binary: Buffer; sourcePath: string | null }> {
  if (isSEA()) {
    return { binary: getEmbeddedRenetBinary('linux', arch), sourcePath: null };
  }

  if (localBinaryPath) {
    // localBinaryPath is the HOST binary (e.g. private/renet/bin/renet). It is only the right thing to send when the remote runs the host's own arch: on a non-Linux host it never is (the host binary is mac/win, not the linux binary a VM needs), and on a Linux host only when the remote arch matches. Otherwise use the cross-compiled renet-linux-<arch> staged next to it by ./rdc.sh
    // / build.sh dev. This is what lets an amd64 workstation provision an arm64 machine (and vice-versa) without building the SEA.
    const hostArch: RenetArch = process.arch === 'arm64' ? 'arm64' : 'amd64';
    if (process.platform !== 'linux' || arch !== hostArch) {
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
