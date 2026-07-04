import { createSecureTempFile, removeTempFile } from '../utils/tempFiles.js';

/**
 * Decodes and normalizes a known_hosts entry
 * - Accepts plain text
 * - Normalizes line endings
 *
 * @param known_hosts - Host entry (plain text)
 * @returns Normalized host entry
 */
function decodeKnownHosts(known_hosts: string): string {
  if (!known_hosts || known_hosts.trim().length === 0) {
    return '';
  }

  let entry = known_hosts.trim();

  // Normalize line endings to Unix format
  entry = entry.replaceAll('\r\n', '\n').replaceAll('\r', '\n');

  // Remove trailing newlines (we'll add one when writing to file)
  entry = entry.replace(/\n+$/, '');

  return entry;
}

/**
 * Creates a temporary known_hosts file with the given host entry
 *
 * @param known_hosts - Host entry to write (plain text)
 * @returns Path to the temporary known_hosts file
 */
export async function createTempKnownHostsFile(known_hosts?: string): Promise<string> {
  let content = '';

  if (known_hosts) {
    const decoded = decodeKnownHosts(known_hosts);
    if (decoded) {
      content = `${decoded}\n`;
    }
  }

  return createSecureTempFile(content, {
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
