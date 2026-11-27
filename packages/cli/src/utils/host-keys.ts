/**
 * SSH host-key helpers shared by the command layer, the provisioning services
 * and the SFTP client.
 *
 * This lives in utils/ rather than in any one of those layers because all three
 * consume it and utils/ is the only neutral layer they already import from
 * (sibling precedent: utils/ssh-keygen.ts).
 */

import { createHash } from 'node:crypto';
import ssh2, { type ServerHostKeyAlgorithm } from 'ssh2';

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

/** Default bound on one host-key scan, per connection. */
const SCAN_TIMEOUT_MS = 10_000;

/**
 * One connection per host-key family, each restricted to that family's
 * signature algorithms, so the server shows every key it holds rather than only
 * the one it prefers. The known_hosts type is read out of the offered key blob
 * itself: an RSA key signs as rsa-sha2-512 but is recorded as `ssh-rsa`,
 * exactly as ssh-keyscan records it.
 */
const HOST_KEY_FAMILIES: ReadonlyArray<{ label: string; algorithms: ServerHostKeyAlgorithm[] }> = [
  { label: 'rsa', algorithms: ['rsa-sha2-512', 'rsa-sha2-256', 'ssh-rsa'] },
  {
    label: 'ecdsa',
    algorithms: ['ecdsa-sha2-nistp256', 'ecdsa-sha2-nistp384', 'ecdsa-sha2-nistp521'],
  },
  { label: 'ed25519', algorithms: ['ssh-ed25519'] },
];

/** Why a scan read no host key. */
type HostKeyScanFailureKind = 'unreachable' | 'timeout' | 'no-algorithm' | 'error';

/** A host-key scan that read no key at all; the message names the host and the cause. */
export class HostKeyScanError extends Error {
  constructor(
    readonly host: string,
    readonly port: number,
    readonly kind: HostKeyScanFailureKind,
    readonly detail: string
  ) {
    super(`${kind} (${host}:${port}): ${detail}`);
    this.name = 'HostKeyScanError';
  }
}

type FamilyFailure = { ok: false; kind: HostKeyScanFailureKind; detail: string };
type FamilyResult = { ok: true; type: string; key: string } | FamilyFailure;

const UNREACHABLE_CODES = new Set([
  'ECONNREFUSED',
  'EHOSTUNREACH',
  'ENETUNREACH',
  'ENOTFOUND',
  'EAI_AGAIN',
  'ECONNRESET',
  'EADDRNOTAVAIL',
]);

function classifyScanError(err: Error & { code?: string; level?: string }): HostKeyScanFailureKind {
  if (err.code && UNREACHABLE_CODES.has(err.code)) return 'unreachable';
  if (err.level === 'client-timeout' || err.code === 'ETIMEDOUT') return 'timeout';
  if (/no matching|host key/i.test(err.message)) return 'no-algorithm';
  return 'error';
}

/** Open one handshake offering only `algorithms` as host-key types, capture the key, and hang up before auth. */
function scanFamily(
  host: string,
  port: number,
  algorithms: ServerHostKeyAlgorithm[],
  timeoutMs: number
): Promise<FamilyResult> {
  return new Promise((resolve) => {
    const client = new ssh2.Client();
    let settled = false;
    let timer: NodeJS.Timeout | undefined;
    const finish = (result: FamilyResult): void => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      client.end();
      resolve(result);
    };
    timer = setTimeout(
      () => finish({ ok: false, kind: 'timeout', detail: `no host key within ${timeoutMs} ms` }),
      timeoutMs
    );
    client.on('error', (err: Error & { code?: string; level?: string }) =>
      finish({ ok: false, kind: classifyScanError(err), detail: err.message })
    );
    client.on('close', () =>
      finish({
        ok: false,
        kind: 'error',
        detail: 'connection closed before a host key was offered',
      })
    );
    client.on('ready', () =>
      finish({ ok: false, kind: 'error', detail: 'session opened without a host key check' })
    );
    try {
      client.connect({
        host,
        port,
        username: 'rdc-host-key-scan',
        readyTimeout: timeoutMs,
        algorithms: { serverHostKey: algorithms },
        hostVerifier: (key: Buffer) => {
          const blob = key.toString('base64');
          const type = keyBlobAlgorithm(blob);
          finish(
            type
              ? { ok: true, type, key: blob }
              : { ok: false, kind: 'error', detail: 'offered host key blob could not be decoded' }
          );
          // Refusing the host aborts the handshake here, before any authentication is attempted.
          return false;
        },
      });
    } catch (err) {
      finish({ ok: false, kind: 'error', detail: (err as Error).message });
    }
  });
}

/**
 * The known_hosts host field OpenSSH (and ssh-keyscan) uses for an endpoint:
 * the bare host on port 22, `[host]:port` otherwise. A host already written in
 * brackets (an IPv6 literal) is unwrapped first so it is never double-bracketed.
 */
function knownHostsHost(host: string, port: number): string {
  const bare = host.startsWith('[') && host.endsWith(']') ? host.slice(1, -1) : host;
  return port === 22 ? bare : `[${bare}]:${port}`;
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
 * by key alone (SFTPClient's hostVerifier), so a machine whose address changed
 * (an IPv4 swapped for its IPv6) keeps working there. OpenSSH looks the key up
 * by host field instead, and a line still carrying the old address is invisible
 * to it, so it refused with "No ED25519 host key is known for <new address>".
 * Writing the same keys under the dialed host keeps the check exactly as strict
 * (only the pinned keys are accepted) while matching what ssh looks up. A
 * leading marker (`@revoked`, `@cert-authority`) is kept; comments are dropped.
 */
function retargetKnownHosts(entry: string, target: KnownHostsTarget): string {
  const hostField = knownHostsHost(target.host, target.port);
  const out: string[] = [];
  for (const raw of entry.replaceAll('\r\n', '\n').replaceAll('\r', '\n').split('\n')) {
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
 * nothing is pinned. Every file handed to a system ssh is written from this
 * (the temp files in remote/ssh/knownHosts.ts, VS Code's persisted one). It
 * lives here, in the neutral layer, so remote/vscode (which the config service
 * reaches) does not import the ssh layer for it.
 */
export function knownHostsFileContent(
  knownHosts: string | undefined,
  target: KnownHostsTarget
): string {
  const retargeted = knownHosts ? retargetKnownHosts(knownHosts, target) : '';
  return retargeted ? `${retargeted}\n` : '';
}

/**
 * Read the host's public keys over SSH and return them as known_hosts lines
 * (`<host> <type> <base64>`), one per key type the host offers.
 *
 * Uses the ssh2 library rather than the ssh-keyscan binary: the OpenSSH that
 * ships with Windows (9.5p2) returns zero keys against Ubuntu's OpenSSH 9.6p1
 * (`choose_kex: unsupported KEX method sntrup761x25519-sha512@openssh.com`)
 * while ssh2 negotiates with it, and no binary on PATH is needed.
 *
 * Rejects with a HostKeyScanError carrying the cause (unreachable, timeout,
 * no host-key algorithm accepted, or the underlying error) when no key at all
 * could be read. A family the host lacks is not an error while another family
 * answered.
 */
export async function scanHostKeys(
  ip: string,
  port: number,
  options: { timeoutMs?: number } = {}
): Promise<string> {
  const timeoutMs = options.timeoutMs ?? SCAN_TIMEOUT_MS;
  const results = await Promise.all(
    HOST_KEY_FAMILIES.map((f) => scanFamily(ip, port, f.algorithms, timeoutMs))
  );
  const hostField = knownHostsHost(ip, port);
  const lines: string[] = [];
  const seen = new Set<string>();
  for (const r of results) {
    if (!r.ok || seen.has(r.type)) continue;
    seen.add(r.type);
    lines.push(`${hostField} ${r.type} ${r.key}`);
  }
  if (lines.length > 0) return lines.join('\n');

  const failures = results.filter((r): r is FamilyFailure => !r.ok);
  const kinds = new Set(failures.map((f) => f.kind));
  // One shared cause (refused, unreachable, timed out) reads as one reason; mixed causes are listed per family.
  if (kinds.size === 1) {
    throw new HostKeyScanError(ip, port, failures[0]!.kind, failures[0]!.detail);
  }
  const detail = failures
    .map((f, i) => `${HOST_KEY_FAMILIES[i]!.label}: ${f.kind}: ${f.detail}`)
    .join('; ');
  throw new HostKeyScanError(ip, port, 'error', detail);
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
    // Guard against a bogus length: algorithm names are short, and a corrupt blob must not cause an out-of-range read.
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
