import { type KnownHostsTarget, knownHostsFileContent } from '../../utils/host-keys.js';
import { createSecureTempFile, removeTempFile } from '../utils/tempFiles.js';

export type { KnownHostsTarget } from '../../utils/host-keys.js';

/**
 * Creates a temporary known_hosts file holding the pinned keys under the host
 * field of the endpoint the caller's system ssh dials.
 *
 * @param known_hosts - Pinned host keys (known_hosts text, any host field)
 * @param target - The host and port the ssh command connects to
 * @returns Path to the temporary known_hosts file
 */
export function createTempKnownHostsFile(
  known_hosts: string | undefined,
  target: KnownHostsTarget
): Promise<string> {
  return createSecureTempFile(knownHostsFileContent(known_hosts, target), {
    prefix: 'known_hosts',
    extension: '',
  });
}

/**
 * Safely removes a temporary known_hosts file
 *
 * @param filePath - Path to the file to remove
 */
export async function removeTempKnownHostsFile(filePath: string): Promise<void> {
  await removeTempFile(filePath);
}
