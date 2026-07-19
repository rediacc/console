/**
 * SSH host-key helpers shared by the command layer, the provisioning services
 * and the SFTP client.
 *
 * This lives in utils/ rather than in any one of those layers because all three
 * consume it and utils/ is the only neutral layer they already import from
 * (sibling precedent: utils/ssh-keygen.ts).
 */

import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';

/** One parsed known_hosts entry. */
export interface HostKeyEntry {
  /** Key algorithm, e.g. "ssh-ed25519", "ssh-rsa", "ecdsa-sha2-nistp256". */
  type: string;
  /** Base64-encoded public key blob, exactly as it appears in known_hosts. */
  key: string;
}

/** What happened to one algorithm's pin during a scan. */
type HostKeyChangeKind = 'pinned' | 'unchanged' | 'replaced';

export interface HostKeyChange {
  type: string;
  kind: HostKeyChangeKind;
  /** Previous key, present only when kind is 'replaced'. */
  oldKey?: string;
  /** Newly scanned key. */
  newKey: string;
}

/**
 * ssh-keyscan the host, returning its known_hosts lines (empty string on
 * failure).
 *
 * Single source of truth: this was previously duplicated byte-for-byte in
 * commands/machine/register.ts and services/renet/machine-bootstrap.ts.
 */
export function scanHostKeys(ip: string, port: number): string {
  try {
    return execFileSync('ssh-keyscan', ['-p', String(port), ip], {
      encoding: 'utf-8',
      timeout: 10_000,
      stdio: ['ignore', 'pipe', 'ignore'],
    }).trim();
  } catch {
    return '';
  }
}

/**
 * Parse OpenSSH known_hosts text into typed entries.
 *
 * Line format: `hostname[,hostname] algo base64key [comment]`. Blank lines,
 * comments and malformed lines are skipped.
 *
 * Note this returns the algorithm alongside the key. Host-key comparison must
 * be per-algorithm: a host offers one key per algorithm, and "the ed25519 key
 * changed" is a materially different statement from "some key changed".
 */
export function parseKnownHosts(knownHosts: string): HostKeyEntry[] {
  const entries: HostKeyEntry[] = [];
  for (const line of knownHosts.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const parts = trimmed.split(/\s+/);
    if (parts.length >= 3) {
      entries.push({ type: parts[1], key: parts[2] });
    }
  }
  return entries;
}

/**
 * OpenSSH-style fingerprint of a base64 key blob: `SHA256:<base64-no-padding>`.
 *
 * Matches what `ssh-keygen -lf` and the OpenSSH client print, so a fingerprint
 * shown by rdc can be compared character-for-character against one read from a
 * provider console or an `ssh` warning.
 */
export function fingerprint(base64Key: string): string {
  const digest = createHash('sha256').update(Buffer.from(base64Key, 'base64')).digest('base64');
  return `SHA256:${digest.replace(/=+$/, '')}`;
}

/**
 * Read the algorithm name out of an SSH public-key blob.
 *
 * SSH wire format prefixes the key with its algorithm as a length-delimited
 * string: a 4-byte big-endian length followed by that many ASCII bytes. This
 * lets an offered key (which arrives as a raw blob, with no known_hosts line to
 * read the algorithm from) be labelled and compared against the pin of the same
 * algorithm. Returns an empty string if the blob cannot be decoded.
 */
export function keyBlobAlgorithm(base64Key: string): string {
  try {
    const buf = Buffer.from(base64Key, 'base64');
    if (buf.length < 4) return '';
    const len = buf.readUInt32BE(0);
    // Guard against a bogus length: algorithm names are short, and a corrupt
    // blob must not cause an out-of-range read.
    if (len === 0 || len > 64 || buf.length < 4 + len) return '';
    const name = buf.subarray(4, 4 + len).toString('ascii');
    return /^[\w.@-]+$/.test(name) ? name : '';
  } catch {
    return '';
  }
}

/** Abbreviate a fingerprint for table output: `SHA256:abcd…wxyz`. */
export function shortFingerprint(base64Key: string): string {
  const full = fingerprint(base64Key).slice('SHA256:'.length);
  return full.length <= 12 ? `SHA256:${full}` : `SHA256:${full.slice(0, 4)}…${full.slice(-4)}`;
}

/**
 * Compare a previous known_hosts blob against a freshly scanned one, per
 * algorithm.
 *
 * Only algorithms present in the new scan are reported: an algorithm that
 * disappears from the host is not a security event the way a *changed* key is,
 * and reporting it as one would add noise to the common case of a server
 * dropping a legacy algorithm.
 */
export function classifyKeyChange(oldKnownHosts: string, newKnownHosts: string): HostKeyChange[] {
  const oldByType = new Map(parseKnownHosts(oldKnownHosts).map((e) => [e.type, e.key]));

  return parseKnownHosts(newKnownHosts).map(({ type, key }) => {
    const previous = oldByType.get(type);
    if (previous === undefined) return { type, kind: 'pinned' as const, newKey: key };
    if (previous === key) return { type, kind: 'unchanged' as const, newKey: key };
    return { type, kind: 'replaced' as const, oldKey: previous, newKey: key };
  });
}
