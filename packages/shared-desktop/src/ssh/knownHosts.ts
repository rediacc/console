import { createSecureTempFile, removeTempFile } from '../utils/tempFiles.js';

/**
 * Decodes and normalizes a known_hosts entry
 * - Accepts plain text
 * - Normalizes line endings
 *
 * @param known_hosts - Host entry (plain text)
 * @returns Normalized host entry
 */
export function decodeKnownHosts(known_hosts: string): string {
  if (!known_hosts || known_hosts.trim().length === 0) {
    return '';
  }

  let entry = known_hosts.trim();

  // Normalize line endings to Unix format
  entry = entry.replace(/\r\n/g, '\n').replace(/\r/g, '\n');

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

/**
 * Validates that a host entry has the expected format
 * Format: hostname key-type base64-key [comment]
 *
 * @param known_hosts - Host entry to validate
 * @returns true if entry appears valid
 */
export function isValidKnownHosts(known_hosts: string): boolean {
  if (!known_hosts || known_hosts.trim().length === 0) {
    return false;
  }

  const decoded = decodeKnownHosts(known_hosts);
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
 * @param known_hosts - Host entry
 * @returns Hostname or null if not found
 */
export function extractHostname(known_hosts: string): string | null {
  if (!known_hosts) return null;

  const decoded = decodeKnownHosts(known_hosts);
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
 * @param known_hosts - Host entry
 * @returns Key type (e.g., 'ssh-rsa') or null if not found
 */
export function extractKeyType(known_hosts: string): string | null {
  if (!known_hosts) return null;

  const decoded = decodeKnownHosts(known_hosts);
  const parts = decoded.split(/\s+/);

  return parts.length >= 2 ? parts[1] : null;
}
