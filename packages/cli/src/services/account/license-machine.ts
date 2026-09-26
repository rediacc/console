/**
 * The machine side of repo licensing: the on-machine license store layout,
 * machine identity, renet's license scans and the size probe. Everything here
 * talks to one machine over an established SFTP connection; the account-server
 * calls that consume it live in `license.ts` and `license-batch.ts`.
 */

import { DEFAULTS } from '@rediacc/shared/config';
import { isValidPublicKeyId } from '@rediacc/shared/subscription';
import type { SFTPClient } from '../../remote/sftp/index.js';
import type { MachineConfig } from '../../types/index.js';
import { outputService } from '../core/output.js';
import type { RemoteRepoLicenseScanEntry, RuntimeRepoLicenseStatus } from './license-types.js';

const LICENSE_DIR = '/var/lib/rediacc/license';
const REPO_LICENSE_DIR = `${LICENSE_DIR}/repos`;
const DATASTORE_LICENSE_DIR = `${LICENSE_DIR}/datastores`;
const CLIENT_MACHINE_ID_PATH = '/etc/machine-id';
export const DEFAULT_DATASTORE = '/mnt/rediacc';

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

export async function readRemoteMachineId(
  sftp: SFTPClient,
  remoteRenetPath?: string
): Promise<string> {
  const command = remoteRenetPath
    ? `sudo ${remoteRenetPath} machine-id 2>/dev/null`
    : 'sudo renet machine-id 2>/dev/null || renet machine-id 2>/dev/null';
  const machineId = (await sftp.exec(command)).trim();
  if (!/^[a-f0-9]{64}$/i.test(machineId)) {
    throw new Error(
      'Failed to resolve remote renet machine ID. Ensure renet is installed and accessible for the SSH user.'
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
  // Linux
  const { readFile } = await import('node:fs/promises');
  return (await readFile(CLIENT_MACHINE_ID_PATH, 'utf-8')).trim();
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
 * `--all-datastores` on every scan, and it is a correctness fix rather than a
 * convenience: without it a scan sees only the machine's primary datastore, so
 * every repo living in a NAMED datastore was invisible to `subscription
 * refresh` and to the license table. Those repos still expire, still block
 * backups, and still need renewal; they were simply never looked at. renet
 * folds the primary and every attached named datastore into one array, tagging
 * each entry with the datastore it came from.
 */
function licenseScanCommand(
  verb: 'license-scan' | 'license-status',
  renetPath: string,
  datastore: string
): string {
  return `sudo ${renetPath} repository ${verb} --datastore '${datastore}' --all-datastores --output json`;
}

export async function scanRemoteLicenseStatuses(
  sftp: SFTPClient,
  datastore: string,
  remoteRenetPath?: string
): Promise<RuntimeRepoLicenseStatus[]> {
  const renetPath = remoteRenetPath ?? DEFAULTS.CONTEXT.RENET_BINARY;
  const output = await sftp.exec(licenseScanCommand('license-status', renetPath, datastore));
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

/**
 * Where a repo's license files live on the machine, mirroring THE SCOPE RULE in
 * renet's `RepoLicenseBaseDir` (pkg/license/store.go):
 *
 *   - no datastore identity (the plain default datastore, which carries no
 *     descriptor) → the legacy unscoped `repos/<guid>/` population;
 *   - an identity → ONLY `datastores/<id>/repos/<guid>/`.
 *
 * Getting this wrong is silent and expensive rather than loud: renet reads one
 * population and one only, so a license written to the other path reads as
 * `missing`, the CLI auto-reissues, and the pair spins reissuing forever while
 * burning the monthly issuance quota. A malformed identity degrades to unscoped
 * exactly as renet's does, so both sides agree on where a corrupt descriptor
 * puts the file.
 */
function repoLicenseDirFor(repositoryGuid: string, datastoreId?: string): string {
  if (!isDatastoreScopedId(datastoreId)) {
    return `${REPO_LICENSE_DIR}/${repositoryGuid}`;
  }
  return `${DATASTORE_LICENSE_DIR}/${datastoreId}/repos/${repositoryGuid}`;
}

export async function writeRepoLicense(
  sftp: SFTPClient,
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

  const repoDir = repoLicenseDirFor(repositoryGuid, datastoreId);
  const repoLicenseFile = `${repoDir}/${publicKeyId}.json`;
  await sftp.exec(`sudo mkdir -p "${repoDir}"`);
  await sftp.execStreaming(`sudo tee "${repoLicenseFile}" > /dev/null`, {
    stdin: JSON.stringify(license, null, 2),
  });
  await sftp.exec(`sudo chmod 640 "${repoLicenseFile}"`);
  // GC the legacy flat file only. Files for other keyIds are never touched ,
  // that no-clobber property is what lets universes coexist. The flat file
  // predates both the per-key layout and datastore scoping, so it is removed
  // from the unscoped root regardless of which population we just wrote to:
  // renet reads it in neither case, and leaving it behind only confuses the
  // next person to look in that directory.
  await sftp.exec(`sudo rm -f "${REPO_LICENSE_DIR}/${repositoryGuid}.json"`);
}

export async function scanRemoteRepoLicenses(
  sftp: SFTPClient,
  datastore: string,
  remoteRenetPath?: string
): Promise<RemoteRepoLicenseScanEntry[]> {
  const renetPath = remoteRenetPath ?? DEFAULTS.CONTEXT.RENET_BINARY;
  const output = await sftp.exec(licenseScanCommand('license-scan', renetPath, datastore));
  const parsed = JSON.parse(output) as RemoteRepoLicenseScanEntry[];
  return Array.isArray(parsed) ? parsed : [];
}
