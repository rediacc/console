/**
 * The machine side of repo licensing: the on-machine license store layout,
 * machine identity, renet's license scans and the size probe. Everything here
 * talks to one machine over an established SFTP connection; the account-server
 * calls that consume it live in `license.ts` and `license-batch.ts`.
 */

import { randomUUID } from 'node:crypto';
import { dirname, join } from 'node:path';
import { DEFAULTS } from '@rediacc/shared/config';
import { WK_DATASTORE_PATH } from '@rediacc/shared/config/well-known.generated';
import { getConfigDir } from '@rediacc/shared/paths';
import { isValidPublicKeyId } from '@rediacc/shared/subscription';
import type { SFTPClient } from '../../remote/sftp/index.js';
import { ERROR_CODES } from '../../types/errors.js';
import type { MachineConfig } from '../../types/index.js';
import { CliExitError } from '../../utils/cli-exit-error.js';
import { shellQuote } from '../../utils/shell-quote.js';
import { outputService } from '../core/output.js';
import { getExecutor } from '../executor/executor-factory.js';
import type { RemoteRepoLicenseScanEntry, RuntimeRepoLicenseStatus } from './license-types.js';

const CLIENT_MACHINE_ID_PATH = '/etc/machine-id';
const CLIENT_MACHINE_ID_DBUS_PATH = '/var/lib/dbus/machine-id';
const CLIENT_INSTALL_ID_FILE = 'client-machine-id';
export const DEFAULT_DATASTORE = WK_DATASTORE_PATH;

/**
 * What renet accepts as a datastore identity path segment, copied from
 * `datastoreIDPattern` in renet's pkg/license/store.go. Anything else is
 * treated as "no identity" (unscoped) on both sides, so a corrupt descriptor
 * degrades to the legacy layout instead of making the store unwritable.
 */
const DATASTORE_ID_PATTERN = /^[0-9a-fA-F-]{8,64}$/;

/**
 * Whether a datastore identity is usable as a license-store scope, mirroring
 * renet's `IsDatastoreScoped` (pkg/license/store.go).
 *
 * Exported because the ISSUANCE side has to answer the same question BEFORE it
 * spends anything: a caller that resolves an identity it believes will scope
 * the write, only for `repoLicenseDirFor` to reject it as malformed and fall
 * back to the unscoped path, has burned a slot on a blob renet will never read.
 * One predicate, asked in both places.
 */
export function isDatastoreScopedId(datastoreId: string | undefined): datastoreId is string {
  return !!datastoreId && DATASTORE_ID_PATTERN.test(datastoreId);
}

/**
 * The machine's license identity, as renet computes it AS ROOT.
 *
 * Root is not a preference. renet hashes the DMI product UUID into the id and
 * that file is root-only, so the same machine has a second, equally
 * well-formed id for any other user (VM .11: c99b905a as root, a66b5f90 as
 * the SSH user). A license bound to the second id fails `machine_mismatch`
 * once its grace runs out and claims a phantom activation slot meanwhile. So
 * there is no non-root fallback: `sudo -n` never prompts, and a machine where
 * it is refused fails here with renet's or sudo's own message.
 */
export async function readRemoteMachineId(
  sftp: SFTPClient,
  remoteRenetPath?: string
): Promise<string> {
  const renetPath = remoteRenetPath ?? DEFAULTS.CONTEXT.RENET_BINARY;
  const command = `sudo -n ${shellQuote(renetPath)} machine-id`;
  let output: string;
  try {
    output = await sftp.exec(command);
  } catch (error) {
    const cause = (error instanceof Error ? error.message : String(error)).trim();
    throw new Error(
      `Failed to read the machine ID with \`${command}\` (it needs root without a password ` +
        `prompt, and renet installed): ${cause}`,
      { cause: error }
    );
  }
  const machineId = output.trim();
  if (!/^[a-f0-9]{64}$/i.test(machineId)) {
    throw new Error(
      `\`${command}\` did not print a machine ID (expected 64 hex characters, got ` +
        `${JSON.stringify(machineId.slice(0, 120))}).`
    );
  }
  return machineId;
}

export async function readLocalMachineId(): Promise<string> {
  if (process.platform === 'win32') {
    // Windows: use MachineGuid from the registry, hashed to match Linux format
    const { execSync } = await import('node:child_process');
    const { createHash } = await import('node:crypto');
    const output = execSync('reg query "HKLM\\SOFTWARE\\Microsoft\\Cryptography" /v MachineGuid', {
      encoding: 'utf-8',
    });
    const match = /MachineGuid\s+REG_SZ\s+(.+)/.exec(output);
    if (!match) throw new Error('Failed to read Windows MachineGuid from registry');
    return createHash('sha256').update(match[1].trim()).digest('hex');
  }
  if (process.platform === 'darwin') {
    // macOS: use IOPlatformUUID from I/O Kit, hashed to match Linux format
    const { execSync } = await import('node:child_process');
    const { createHash } = await import('node:crypto');
    const output = execSync('ioreg -rd1 -c IOPlatformExpertDevice | grep IOPlatformUUID', {
      encoding: 'utf-8',
    });
    const match = /"IOPlatformUUID"\s*=\s*"([^"]+)"/.exec(output);
    if (!match) throw new Error('Failed to read macOS IOPlatformUUID');
    return createHash('sha256').update(match[1].trim()).digest('hex');
  }
  return readLinuxClientMachineId();
}

export interface LinuxClientIdSources {
  /** Host identity files, tried in order. */
  hostPaths: string[];
  /** Where a generated per-install id is kept when no host file exists. */
  installIdPath: string;
}

/**
 * The client id on Linux. The account server stores `clientMachineId` as the
 * identity of the CLIENT host (it rides the signed blob and the audit log; it
 * is never compared, renet only carries the field). The licensed machine is
 * identified separately by `machineId`, read remotely as root.
 *
 * A caller without a host id is normal, not broken: a proxied command runs in
 * the executor container, which has no /etc/machine-id. It then uses a
 * generated id persisted in the CLI config dir, so the same install reports
 * the same client. When even that cannot be written, the failure is a named
 * PRECONDITION_MISMATCH, never a raw ENOENT.
 */
export async function readLinuxClientMachineId(
  sources: LinuxClientIdSources = {
    hostPaths: [CLIENT_MACHINE_ID_PATH, CLIENT_MACHINE_ID_DBUS_PATH],
    installIdPath: join(getConfigDir(), CLIENT_INSTALL_ID_FILE),
  }
): Promise<string> {
  // writeFile and mkdir are read only on the fallback path: a caller with a host id
  // (and a test that mocks node:fs/promises with readFile alone) never touches them.
  const fsp = await import('node:fs/promises');
  const { readFile } = fsp;
  let unreadable: CliExitError | undefined;
  for (const path of sources.hostPaths) {
    const id = await readFile(path, 'utf-8').then(
      (v) => v.trim(),
      (error: unknown) => {
        // Only an absent file means "no host id". An unreadable one (EACCES, EISDIR) is remembered and reported once no later candidate yields an id, since falling back to the generated id would make this host report an id other than its real one.
        if ((error as NodeJS.ErrnoException).code !== 'ENOENT') {
          unreadable ??= new CliExitError(
            ERROR_CODES.PRECONDITION_MISMATCH,
            `Cannot read the client machine id at ${path} (${error instanceof Error ? error.message : String(error)}).`
          );
        }
        return '';
      }
    );
    if (id) return id;
  }
  if (unreadable) throw unreadable;
  const existing = await readFile(sources.installIdPath, 'utf-8').then(
    (v) => v.trim(),
    () => ''
  );
  if (/^[a-f0-9]{64}$/.test(existing)) return existing;
  const generated = `${randomUUID()}${randomUUID()}`.replaceAll('-', '').slice(0, 64);
  try {
    return await persistInstallId(sources.installIdPath, generated);
  } catch (error) {
    throw new CliExitError(
      ERROR_CODES.PRECONDITION_MISMATCH,
      `No client machine id: ${sources.hostPaths.join(' and ')} are missing and a generated one could not be saved to ${sources.installIdPath} (${error instanceof Error ? error.message : String(error)}). Make the CLI config directory writable.`
    );
  }
}

/** Save a generated id with an exclusive create: of two first runs racing here, one id is persisted and both calls get it. */
async function persistInstallId(path: string, generated: string): Promise<string> {
  const fsp = await import('node:fs/promises');
  try {
    await fsp.mkdir(dirname(path), { recursive: true, mode: 0o700 });
    await fsp.writeFile(path, `${generated}\n`, { mode: 0o600, flag: 'wx' });
    return generated;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'EEXIST') {
      const persisted = await readRacedInstallId(path);
      if (persisted) return persisted;
      // Nothing valid ever appeared: the file is a corrupt leftover, not a winner's. One racer replaces it under an exclusive lock file, so two runs never both overwrite it with their own ids.
      return replaceCorruptInstallId(path, generated);
    }
    throw error;
  }
}

/** How long a replace lock may stand before it is taken for a crashed holder's. */
const REPLACE_LOCK_STALE_MS = 5000;

/**
 * One attempt at the replace lock. Undefined when the lock is now held; otherwise the id the holder persisted while
 * this run waited, or '' when the holder has not written one (a lock past REPLACE_LOCK_STALE_MS is then removed as a
 * crashed holder's, so the caller contends again).
 */
async function tryReplaceLock(path: string, lockPath: string): Promise<string | undefined> {
  const fsp = await import('node:fs/promises');
  try {
    await fsp.writeFile(lockPath, '', { mode: 0o600, flag: 'wx' });
    return undefined;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'EEXIST') throw error;
  }
  const persisted = await readRacedInstallId(path);
  if (persisted) return persisted;
  const lock = await fsp.stat(lockPath).catch(() => undefined);
  if (lock && Date.now() - lock.mtimeMs > REPLACE_LOCK_STALE_MS) {
    await fsp.rm(lockPath, { force: true });
  }
  return '';
}

/**
 * Replace a corrupt id file: the lock holder re-checks, then writes; a racer that lost the lock waits for what the
 * holder wrote. A lock older than REPLACE_LOCK_STALE_MS is taken for a crashed holder's and removed, and the racer then
 * contends for the lock again. The holder's critical section is one read and one write, so a holder stalled past that
 * age is the accepted limit of an age-based lock; the write is still the holder's own id or a valid one a racer left,
 * and the holder re-reads the file under the lock before it overwrites.
 */
async function replaceCorruptInstallId(path: string, generated: string): Promise<string> {
  const fsp = await import('node:fs/promises');
  const lockPath = `${path}.replace`;
  for (;;) {
    const outcome = await tryReplaceLock(path, lockPath);
    if (outcome === undefined) break;
    if (outcome) return outcome;
  }
  try {
    const current = (await fsp.readFile(path, 'utf-8').catch(() => '')).trim();
    if (/^[a-f0-9]{64}$/.test(current)) return current;
    await fsp.writeFile(path, `${generated}\n`, { mode: 0o600 });
    return generated;
  } finally {
    await fsp.rm(lockPath, { force: true });
  }
}

/** The id a racing first run persisted. The winner may still be writing, so a few short reads cover the gap between its create and its write. */
async function readRacedInstallId(path: string): Promise<string | undefined> {
  const { readFile } = await import('node:fs/promises');
  for (let attempt = 0; attempt < 5; attempt++) {
    const persisted = (await readFile(path, 'utf-8').catch(() => '')).trim();
    if (/^[a-f0-9]{64}$/.test(persisted)) return persisted;
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
  return undefined;
}

/**
 * Printed by the size probe when it could not measure the image. Deliberately
 * not a number: `else echo 0` made a missing image and a real zero the same
 * bytes, so the caller reported the 1 GB floor as though it had measured it.
 */
const REPO_SIZE_PROBE_UNKNOWN = 'rediacc-size-unknown';

/** Floor for a size request. renet compares `requested > limit`, so it never over-claims. */
const MIN_REQUESTED_SIZE_GB = 1;

/**
 * Measure a repo's image, or answer `null` when it could not be measured.
 *
 * `null` rather than a number, because the two are genuinely different facts
 * and the old signature could not express the second one. The caller decides
 * what an unmeasurable image is worth; this only reports what it saw.
 */
async function readRepoSizeGb(
  sftp: SFTPClient,
  datastore: string,
  repositoryGuid: string
): Promise<number | null> {
  const repoPath = `${datastore}/repositories/${repositoryGuid}`;
  const bytesOutput = await sftp.exec(
    `sudo sh -lc 'if [ -e "${repoPath}" ]; then stat -c %s "${repoPath}" 2>/dev/null || echo ${REPO_SIZE_PROBE_UNKNOWN}; else echo ${REPO_SIZE_PROBE_UNKNOWN}; fi'`
  );
  const probe = bytesOutput.trim();
  if (!/^\d+$/.test(probe)) return null;
  return Math.max(
    MIN_REQUESTED_SIZE_GB,
    Math.ceil(Number.parseInt(probe, 10) / (1024 * 1024 * 1024))
  );
}

/**
 * Measure the repo image across the candidate mounts, best answer first, and
 * say so out loud if none of them could answer.
 *
 * A list rather than one path because the three sources genuinely disagree in
 * rank: the machine's own scan knows where the repo lives, the caller knows
 * what placement it recorded, and the machine default is a guess that is only
 * right for a default-datastore repo. Trying them in order costs one extra
 * `stat` in the rare case where the better source is absent, and it removes the
 * failure mode that made this worth fixing, measuring the wrong mount and
 * reporting the floor as though it were a measurement.
 */
export async function measureRepoSizeGb(
  sftp: SFTPClient,
  repositoryGuid: string,
  candidateMounts: (string | undefined)[]
): Promise<number> {
  const mounts = [...new Set(candidateMounts.filter((m): m is string => !!m))];
  for (const mount of mounts) {
    const measured = await readRepoSizeGb(sftp, mount, repositoryGuid);
    if (measured !== null) return measured;
  }
  outputService.warn(
    `Could not measure repository ${repositoryGuid} on ${mounts.join(', ') || 'any datastore'}, ` +
      `so its license is being requested at the ${MIN_REQUESTED_SIZE_GB} GB minimum instead of ` +
      `its real size. If this repository lives on a named datastore, check that its recorded ` +
      `placement matches where the image actually is ("rdc config reconcile").`
  );
  return MIN_REQUESTED_SIZE_GB;
}

/**
 * One licence command-kind job (`license-status`, `license-scan`, `license-write`), awaited here: the caller
 * needs the answer before it goes on, so `probe` keeps `--background` from handing back a ticket in its place.
 *
 * renet passes `--all-datastores` on both reads, and that is a correctness fix rather than a convenience:
 * without it a scan sees only the machine's primary datastore, so every repo living in a NAMED datastore was
 * invisible to `subscription refresh` and to the license table. Those repos still expire, still block backups,
 * and still need renewal; they were simply never looked at. renet folds the primary and every attached named
 * datastore into one array, tagging each entry with the datastore it came from.
 */
async function runLicenseJob(
  machineName: string,
  name: 'license-scan' | 'license-status' | 'license-write',
  args: Record<string, unknown>,
  payload?: string
): Promise<string> {
  const result = await getExecutor().execute({
    functionName: name,
    machineName,
    commandKind: { name, args, ...(payload === undefined ? {} : { payload }) },
    captureOutput: true,
    probe: true,
  });
  if (!result.success) {
    throw new Error(
      `renet ${name} failed on ${machineName} (exit ${result.exitCode}): ${result.stderr ?? result.error ?? ''}`.trim()
    );
  }
  return result.stdout ?? '';
}

export async function scanRemoteLicenseStatuses(
  machineName: string,
  datastore: string
): Promise<RuntimeRepoLicenseStatus[]> {
  const output = await runLicenseJob(machineName, 'license-status', { datastore });
  const parsed = JSON.parse(output) as unknown;
  return Array.isArray(parsed) ? (parsed as RuntimeRepoLicenseStatus[]) : [];
}

/**
 * The cluster this machine belongs to, for the informational `clusterId` that
 * rides every issuance and renewal. It exists so support and analytics can see
 * cluster context; it carries no enforcement semantics.
 *
 * KNOWN LIMITATION: the design names the cluster CA fingerprint as the value,
 * but no CLI surface exposes that fingerprint yet, so this sends the cluster
 * NAME from the config. Names are unique within a config and stable in
 * practice, which is enough for the telemetry this field is for; swapping in
 * the fingerprint is a one-line change here once it has a reader.
 */
export function clusterIdFor(machine: MachineConfig): string | undefined {
  return machine.cluster?.cluster;
}

export async function writeRepoLicense(
  machineName: string,
  repositoryGuid: string,
  license: unknown,
  datastoreId?: string
): Promise<void> {
  // The license is written under a per-signer name so licenses signed by
  // different account universes (each with its own baked key in renet)
  // coexist without clobbering each other. The name is the signing key's
  // fingerprint, carried in the blob's publicKeyId.
  const publicKeyId =
    typeof license === 'object' && license !== null
      ? (license as { publicKeyId?: unknown }).publicKeyId
      : undefined;
  if (typeof publicKeyId !== 'string' || !isValidPublicKeyId(publicKeyId)) {
    throw new Error(
      `Refusing to write repo license for ${repositoryGuid}: signed blob has an invalid ` +
        `publicKeyId (${JSON.stringify(publicKeyId)}); expected a 16-char hex fingerprint. ` +
        'This usually means the account server and CLI disagree on the fingerprint format.'
    );
  }

  // renet installs the blob into the population the datastore identity selects (the scope rule is `license.InstallRepoLicense`, pkg/license/store.go): a missing or malformed identity means the legacy unscoped layout, other signers' files stay, and the legacy flat file goes. A wrong scope reads as `missing` and spins reissue forever, which is why the identity is sent only when it is usable. The blob rides as the job's payload, never an argument.
  await runLicenseJob(
    machineName,
    'license-write',
    {},
    JSON.stringify({
      repositoryGuid,
      ...(isDatastoreScopedId(datastoreId) ? { datastoreId } : {}),
      license,
    })
  );
}

export async function scanRemoteRepoLicenses(
  machineName: string,
  datastore: string
): Promise<RemoteRepoLicenseScanEntry[]> {
  const output = await runLicenseJob(machineName, 'license-scan', { datastore });
  const parsed = JSON.parse(output) as RemoteRepoLicenseScanEntry[];
  return Array.isArray(parsed) ? parsed : [];
}
