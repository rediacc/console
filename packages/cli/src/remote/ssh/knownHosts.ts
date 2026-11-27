import { knownHostsHost } from '../../utils/host-keys.js';
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

/** The endpoint a system ssh actually dials, which OpenSSH looks pinned keys up under. */
export interface KnownHostsTarget {
  host: string;
  port: number;
}

/**
 * Re-key every pinned line under the host field of the endpoint being dialed.
 *
 * The pin is the key, not the address it was scanned at: the ssh2 path trusts
 * by key alone (utils/host-keys.ts), so a machine whose address changed (an
 * IPv4 swapped for its IPv6) keeps working there. OpenSSH looks the key up by
 * host field instead, and a line still carrying the old address is invisible to
 * it, so it refused with "No ED25519 host key is known for <new address>".
 * Writing the same keys under the dialed host keeps the check exactly as strict
 * (only the pinned keys are accepted) while matching what ssh looks up. A
 * leading marker (`@revoked`, `@cert-authority`) is kept; comments are dropped.
 */
function retargetKnownHosts(entry: string, target: KnownHostsTarget): string {
  const hostField = knownHostsHost(target.host, target.port);
  const out: string[] = [];
  for (const raw of entry.split('\n')) {
    const line = raw.trim();
    if (!line || line.startsWith('#')) continue;
    const parts = line.split(/\s+/);
    const marker = parts[0]?.startsWith('@') ? parts.shift() : undefined;
    // `<host> <type> <key> [comment]`: a line without a key is not a pin.
    if (parts.length < 3) continue;
    const [, type, key] = parts;
    out.push(marker ? `${marker} ${hostField} ${type} ${key}` : `${hostField} ${type} ${key}`);
  }
  return out.join('\n');
}

/**
 * The known_hosts file content an OpenSSH client dialing `target` reads: every
 * pinned key under the dialed host field, newline-terminated, or '' when
 * nothing is pinned. Every file handed to a system ssh is written from this.
 */
export function knownHostsFileContent(
  known_hosts: string | undefined,
  target: KnownHostsTarget
): string {
  if (!known_hosts) return '';
  const decoded = decodeKnownHosts(known_hosts);
  const retargeted = decoded ? retargetKnownHosts(decoded, target) : '';
  return retargeted ? `${retargeted}\n` : '';
}

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
