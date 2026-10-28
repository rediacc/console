/**
 * `rdc machine access push`: write the config's access keys for one machine
 * into that machine's authorized_keys (agent/plans/PLAN-ssh-key-source-ranges.md,
 * Design 3).
 *
 * The file is read over SFTP, planned by the pure planner (authorized-keys.ts),
 * and replaced by compare-and-swap: the new text is written to a temp file
 * beside it over SFTP, and one exec moves it over authorized_keys only when the
 * live file still has the SHA-256 recorded at read time. File contents never
 * pass through a shell.
 */

import { createHash, randomBytes } from 'node:crypto';
import {
  type AccessConfig,
  canonicalKeyBlob,
  parseOpenSshPublicKey,
  resolveAccessSourceRanges,
  type SourceRanges,
} from '@rediacc/shared/config-schema';
import { cidrContains } from '@rediacc/shared/validation';
import ssh2 from 'ssh2';
import { shellQuote } from '../../utils/shell-quote.js';
import { configService } from '../config/config-resources.js';
import {
  type AccessChange,
  type AccessRewritePlan,
  type DesiredAccessKey,
  parseAuthorizedKeys,
  planAccessRewrite,
} from './authorized-keys.js';
import { machineConnections } from './machine-connection.js';

/** Exit code of the compare-and-swap exec when the live file no longer matches what was read. */
export const ACCESS_CAS_MISMATCH_EXIT = 3;

/** The hash recorded for an authorized_keys file that did not exist at read time. */
const ABSENT = 'absent';

export interface AccessPushOptions {
  /** Plan and report, never write. */
  dryRun?: boolean;
}

export interface AccessPushReport {
  machine: string;
  /** The authorized_keys path read (and written), `$HOME/.ssh/authorized_keys` of the machine's user. */
  path: string;
  written: boolean;
  changes: AccessChange[];
}

function lockoutMessage(
  machine: string,
  keyName: string,
  clientAddress: string | undefined,
  removal: boolean
): string {
  const own = `access key ${keyName} is the key this session authenticates with`;
  if (removal) {
    return `${own}, and pushing would remove its last line from authorized_keys on ${machine}; nothing was written`;
  }
  if (clientAddress === undefined) {
    return `${own}, and the session's source address on ${machine} is unknown ($SSH_CONNECTION is empty); refusing to restrict it`;
  }
  return `${own}, and its ranges for ${machine} do not contain this session's source address ${clientAddress}; pushing would lock rdc out, so nothing was written`;
}

/**
 * The push would lock rdc out of the machine, so nothing is written: either the
 * session's own key is a desired access key and the address sshd sees the
 * session coming from lies outside that key's ranges, or (`removal`) the push
 * removes the last authorized_keys line carrying the session's own key.
 */
export class AccessLockoutError extends Error {
  readonly code = 'ACCESS_LOCKOUT';
  readonly retryable = false;
  constructor(
    readonly machine: string,
    readonly keyName: string,
    readonly clientAddress: string | undefined,
    readonly removal = false
  ) {
    super(lockoutMessage(machine, keyName, clientAddress, removal));
    this.name = 'AccessLockoutError';
  }
}

/** authorized_keys changed between the read and the swap: nothing was written; run the push again. */
export class AccessFileChangedError extends Error {
  readonly code = 'ACCESS_FILE_CHANGED';
  readonly retryable = true;
  constructor(
    readonly machine: string,
    readonly path: string
  ) {
    super(
      `${path} on ${machine} changed while the access push was planning; nothing was written, run it again`
    );
    this.name = 'AccessFileChangedError';
  }
}

/** The access keys bound to `machineName`, with the ranges each resolves to there. */
export function desiredAccessKeys(
  access: AccessConfig | undefined,
  machineName: string
): DesiredAccessKey[] {
  if (access === undefined) return [];
  const desired: DesiredAccessKey[] = [];
  for (const [name, key] of Object.entries(access.keys ?? {})) {
    if (key.machines?.[machineName] === undefined) continue;
    const ranges = resolveAccessSourceRanges(access, name, machineName);
    if (ranges === undefined) {
      throw new Error(`access key ${name} resolves to no source range on ${machineName}`);
    }
    desired.push({ name, key: key.publicKey, ranges, restrict: key.restrict !== false });
  }
  return desired;
}

function sha256(data: Buffer): string {
  return createHash('sha256').update(data).digest('hex');
}

/** Canonical blobs of the keys this session authenticates with: the private key's public half, and the configured public key. */
export function sessionKeyBlobs(sshPrivateKey: string, sshPublicKey?: string): Set<string> {
  const blobs = new Set<string>();
  const parsed = ssh2.utils.parseKey(sshPrivateKey);
  const first = Array.isArray(parsed) ? parsed[0] : parsed;
  if (first !== undefined && !(first instanceof Error)) {
    const blob = canonicalKeyBlob(first.getPublicSSH().toString('base64'));
    if (blob !== null) blobs.add(blob);
  }
  if (sshPublicKey) {
    const raw = parseOpenSshPublicKey(sshPublicKey.trim())?.blob;
    const blob = raw === undefined ? null : canonicalKeyBlob(raw);
    if (blob !== null) blobs.add(blob);
  }
  return blobs;
}

function rangesContain(ranges: SourceRanges, address: string): boolean {
  return [...(ranges.ipv4 ?? []), ...(ranges.ipv6 ?? [])].some((cidr) =>
    cidrContains(cidr, address)
  );
}

function lineBlob(blob: string | undefined): string | null {
  return blob === undefined ? null : canonicalKeyBlob(blob);
}

/** Refuse when a desired key is the session's own and the session address is outside its ranges. */
function assertDesiredKeysReachable(
  machine: string,
  desired: DesiredAccessKey[],
  sessionBlobs: Set<string>,
  clientAddress: string | undefined
): void {
  for (const key of desired) {
    const blob = lineBlob(parseOpenSshPublicKey(key.key.trim())?.blob);
    if (blob === null || !sessionBlobs.has(blob)) continue;
    if (clientAddress === undefined || !rangesContain(key.ranges, clientAddress)) {
      throw new AccessLockoutError(machine, key.name, clientAddress);
    }
  }
}

/**
 * Refuse when the plan removes a line carrying the session's own key and no
 * line carrying it is left: a binding dropped from a key this config had
 * adopted (the adopt dropped every unmarked duplicate, so the marked line is
 * the session key's only line).
 */
function assertSessionKeyKept(
  machine: string,
  plan: AccessRewritePlan,
  sessionBlobs: Set<string>,
  clientAddress: string | undefined
): void {
  const removed = plan.changes.filter((change) => change.action === 'remove');
  if (removed.length === 0) return;
  const remaining = new Set(parseAuthorizedKeys(plan.text).map((line) => lineBlob(line.blob)));
  for (const change of removed) {
    const blob = lineBlob(parseAuthorizedKeys(change.text)[0]?.blob);
    if (blob !== null && sessionBlobs.has(blob) && !remaining.has(blob)) {
      throw new AccessLockoutError(machine, change.key, clientAddress, true);
    }
  }
}

/** Refuse any plan that would lock this session's key out of the machine. */
function assertNoLockout(
  machine: string,
  desired: DesiredAccessKey[],
  plan: AccessRewritePlan,
  sessionBlobs: Set<string>,
  clientAddress: string | undefined
): void {
  assertDesiredKeysReachable(machine, desired, sessionBlobs, clientAddress);
  assertSessionKeyKept(machine, plan, sessionBlobs, clientAddress);
}

/** `$HOME` and the client address (field 1 of `$SSH_CONNECTION`) of the session. */
function parseSessionProbe(output: string): { home: string; clientAddress?: string } {
  const [home = '', connection = ''] = output.split('\n');
  if (!home.startsWith('/')) {
    throw new Error(`could not resolve $HOME on the machine (got ${JSON.stringify(home)})`);
  }
  const clientAddress = connection.trim().split(/\s+/)[0] || undefined;
  return { home, clientAddress };
}

/**
 * The compare-and-swap: move `tmp` over `file` only when the live file still
 * hashes to `expected` (`absent` when it did not exist). On a mismatch the temp
 * file is removed and the script exits 3. Only paths and a hex digest are
 * interpolated, each shell-quoted; the file contents never reach the shell.
 *
 * The swap is not atomic. POSIX gives no conditional rename, and other writers
 * of authorized_keys (ssh-copy-id, an editor, rdc's repo-key deployment) take no
 * lock, so a write landing between the hash and the `mv` is overwritten. The
 * check catches every change made while the push read, planned and uploaded,
 * which is the window that lasts seconds; every preparatory step (modes) runs
 * before the hash, so the residual window is the two adjacent commands
 * `[ "$have" != "$want" ]` and `mv -f`.
 */
export function buildSwapScript(dir: string, file: string, tmp: string, expected: string): string {
  return [
    'set -eu',
    `d=${shellQuote(dir)}; f=${shellQuote(file)}; t=${shellQuote(tmp)}; want=${shellQuote(expected)}`,
    'mkdir -p "$d"; chmod 700 "$d"; chmod 600 "$t"',
    'if command -v sha256sum >/dev/null 2>&1; then sum() { sha256sum < "$1"; }; else sum() { shasum -a 256 < "$1"; }; fi',
    'if [ -e "$f" ]; then have=$(sum "$f"); have=${have%% *}; else have=absent; fi',
    `if [ "$have" != "$want" ]; then rm -f "$t"; exit ${ACCESS_CAS_MISMATCH_EXIT}; fi`,
    'mv -f "$t" "$f"',
  ].join('\n');
}

/** Plan, and unless `dryRun`, apply the config's access keys to `machineName`'s authorized_keys. */
export async function pushAccess(
  machineName: string,
  options: AccessPushOptions = {}
): Promise<AccessPushReport> {
  const config = await configService.getCurrent();
  if (!config) throw new Error('No active config');
  const desired = desiredAccessKeys(config.access, machineName);
  const { sshPublicKey } = await configService.getLocalConfig();

  const lease = await machineConnections.acquire(machineName);
  try {
    const sftp = lease.sftp;
    const { home, clientAddress } = parseSessionProbe(
      await sftp.exec('printf \'%s\\n%s\\n\' "$HOME" "${SSH_CONNECTION:-}"')
    );
    const dir = `${home}/.ssh`;
    const path = `${dir}/authorized_keys`;

    const exists = await sftp.exists(path);
    const current = exists ? await sftp.readFile(path) : Buffer.alloc(0);
    const recorded = exists ? sha256(current) : ABSENT;
    const text = current.toString('utf8');
    const plan = planAccessRewrite(parseAuthorizedKeys(text), desired, config.id);

    assertNoLockout(
      machineName,
      desired,
      plan,
      sessionKeyBlobs(lease.sshPrivateKey, sshPublicKey),
      clientAddress
    );

    const report: AccessPushReport = {
      machine: machineName,
      path,
      written: false,
      changes: plan.changes,
    };
    if (plan.text === text || options.dryRun) return report;

    // The temp file is written into .ssh, so .ssh must exist before the swap's own mkdir.
    if (!exists) await sftp.exec(`mkdir -p -m 700 ${shellQuote(dir)}`);
    const tmp = `${dir}/.authorized_keys.rdc-${randomBytes(8).toString('hex')}`;
    await sftp.writeFile(tmp, Buffer.from(plan.text, 'utf8'));
    let code: number;
    try {
      code = await sftp.execStreaming(buildSwapScript(dir, path, tmp, recorded), {});
    } catch (error) {
      await sftp.delete(tmp, false).catch(() => undefined);
      throw error;
    }
    if (code === 0) return { ...report, written: true };
    await sftp.delete(tmp, false).catch(() => undefined);
    if (code === ACCESS_CAS_MISMATCH_EXIT) throw new AccessFileChangedError(machineName, path);
    throw new Error(`replacing ${path} on ${machineName} failed (exit ${code})`);
  } finally {
    lease.release();
  }
}
