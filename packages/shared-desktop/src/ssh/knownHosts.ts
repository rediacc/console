import { createSecureTempFile, removeTempFile } from '../utils/tempFiles.js';

/**
 * Decodes and normalizes a known_hosts entry
 * - Decodes from base64 if needed
 * - Normalizes line endings
 *
 * @param hostEntry - Host entry (may be base64 encoded)
 * @returns Normalized host entry
 */
export function decodeHostEntry(hostEntry: string): string {
  if (!hostEntry || hostEntry.trim().length === 0) {
    return '';
  }

  let entry = hostEntry.trim();

  // Known_hosts entries typically contain spaces (e.g., "hostname ssh-rsa AAAA...")
  // If there are no spaces and no newlines, it's likely base64 encoded
  if (!entry.includes(' ') && !entry.includes('\n')) {
    try {
      entry = Buffer.from(entry, 'base64').toString('utf-8');
    } catch {
      // If decoding fails, use as-is (might already be decoded)
    }
  }

  // Normalize line endings to Unix format
  entry = entry.replace(/\r\n/g, '\n').replace(/\r/g, '\n');

  // Remove trailing newlines (we'll add one when writing to file)
  entry = entry.replace(/\n+$/, '');

  return entry;
}

/**
 * Creates a temporary known_hosts file with the given host entry
 *
 * @param hostEntry - Host entry to write (may be base64 encoded)
 * @returns Path to the temporary known_hosts file
 */
export async function createTempKnownHostsFile(hostEntry?: string): Promise<string> {
  let content = '';

  if (hostEntry) {
    const decoded = decodeHostEntry(hostEntry);
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

/**
 * Validates that a host entry has the expected format
 * Format: hostname key-type base64-key [comment]
 *
 * @param hostEntry - Host entry to validate
 * @returns true if entry appears valid
 */
export function isValidHostEntry(hostEntry: string): boolean {
  if (!hostEntry || hostEntry.trim().length === 0) {
    return false;
  }

  const decoded = decodeHostEntry(hostEntry);
  const parts = decoded.split(/\s+/);

  // Minimum: hostname, key-type, key-data
  if (parts.length < 3) {
    return false;
  }

  // Validate key type
  const validKeyTypes = [
    'ssh-rsa',
    'ssh-dss',
    'ssh-ed25519',
    'ecdsa-sha2-nistp256',
    'ecdsa-sha2-nistp384',
    'ecdsa-sha2-nistp521',
    'sk-ssh-ed25519@openssh.com',
    'sk-ecdsa-sha2-nistp256@openssh.com',
  ];

  const keyType = parts[1];
  if (!validKeyTypes.includes(keyType)) {
    return false;
  }

  // Key data should be base64 (alphanumeric, +, /, =)
  const keyData = parts[2];
  if (!/^[A-Za-z0-9+/=]+$/.test(keyData)) {
    return false;
  }

  return true;
}

/**
 * Extracts the hostname from a known_hosts entry
 *
 * @param hostEntry - Host entry
 * @returns Hostname or null if not found
 */
export function extractHostname(hostEntry: string): string | null {
  if (!hostEntry) return null;

  const decoded = decodeHostEntry(hostEntry);
  const parts = decoded.split(/\s+/);

  if (parts.length < 1) return null;

  // Hostname may include port: [hostname]:port
  const hostPart = parts[0];
  const match = hostPart.match(/^\[?([^\]]+)\]?(?::\d+)?$/);

  return match ? match[1] : hostPart;
}

/**
 * Extracts the key type from a known_hosts entry
 *
 * @param hostEntry - Host entry
 * @returns Key type (e.g., 'ssh-rsa') or null if not found
 */
export function extractKeyType(hostEntry: string): string | null {
  if (!hostEntry) return null;

  const decoded = decodeHostEntry(hostEntry);
  const parts = decoded.split(/\s+/);

  return parts.length >= 2 ? parts[1] : null;
}
