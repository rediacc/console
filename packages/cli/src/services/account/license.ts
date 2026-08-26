/* eslint-disable max-lines */
import { DEFAULTS } from '@rediacc/shared/config';
import { isValidPublicKeyId } from '@rediacc/shared/subscription';
import { TELEMETRY_SUBSCRIPTION_SOURCES } from '@rediacc/shared/telemetry';
import type { SFTPClient } from '../../remote/sftp/index.js';
import type { MachineConfig } from '../../types/index.js';
import { configService } from '../config/config-resources.js';
import { outputService } from '../core/output.js';
import { sftpConfigForMachine, withSharedOrPooledSftp } from '../machine/machine-connection.js';
import { telemetryService } from '../telemetry/telemetry.js';
import { accountServerFetch } from './account-client.js';
import { getSubscriptionTokenState } from './subscription-auth.js';

const LICENSE_DIR = '/var/lib/rediacc/license';
const REPO_LICENSE_DIR = `${LICENSE_DIR}/repos`;
const DATASTORE_LICENSE_DIR = `${LICENSE_DIR}/datastores`;
const CLIENT_MACHINE_ID_PATH = '/etc/machine-id';
const DEFAULT_DATASTORE = '/mnt/rediacc';

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

interface RemoteRepoLicenseScanEntry {
  repositoryGuid: string;
  /**
   * Identity of the datastore holding this repo, minted at datastore create
   * and REMINTED at fork. It scopes both the signed payload and the on-machine
   * license store, which is what makes a same-node datastore fork re-meter.
   * Absent for the plain default datastore, which carries no descriptor.
   */
  datastoreId?: string;
  datastorePath?: string;
  requestedSizeGb: number;
  luksUuid?: string;
  storageFingerprint?: string;
  currentRefreshRecommendedAt?: string;
  currentHardExpiresAt?: string;
}

/** The persistent marker renet's backup gate writes when licensing refuses a backup. */
interface RepoLicenseBlockedBackup {
  repositoryGuid: string;
  code: string;
  reason: string;
  message: string;
  at: string;
  source: string;
}

/** One repo's slice of the last unattended `renet license renew` run. */
interface RepoLicenseRenewal {
  repositoryGuid: string;
  datastoreId?: string;
  keyId: string;
  outcome: string;
  newKeyId?: string;
  newSequence?: number;
  code?: string;
  message?: string;
}

export type RepoBatchRecoveryFailureMode =
  | 'token_not_ready'
  | 'no_known_repos'
  | 'server_rejected_all'
  | null; // null = success or partial success (valid > 0)

export interface RepoBatchRefreshResult {
  scanned: number;
  issued: number;
  refreshed: number;
  unchanged: number;
  failed: number;
  valid: number;
  invalidSignatureDetected: number;
  failures: { repositoryGuid: string; error: string }[];
  recoveryFailureMode: RepoBatchRecoveryFailureMode;
  serverErrorSample?: string;
}

interface RepoLicenseIssuancesUsage {
  used: number;
  limit: number;
  windowStart: string;
  windowEnd: string;
}

export interface SubscriptionLicenseReport {
  subscriptionId: string;
  orgId?: string;
  orgName?: string;
  teamId?: string;
  teamName?: string;
  planCode: string;
  status: string;
  machineSlots: {
    active: number;
    max: number;
    machines: {
      machineId: string;
      lastSeenAt: string;
      activatedAt?: string;
      /** A renewal soft-claimed this slot beyond the machine-slot limit. */
      overLimit?: boolean;
      clusterId?: string;
    }[];
  };
  repoLicenseIssuances: RepoLicenseIssuancesUsage;
  repoLicenses: {
    totalTrackedRepos: number;
    validCount: number;
    refreshRecommendedCount: number;
    hardExpiredCount: number;
  };
}

export interface MachineActivationStatus {
  machineId: string;
  active: boolean;
  lastSeenAt?: string;
  activeCount?: number;
  maxCount?: number;
}

export interface RuntimeRepoLicenseStatus {
  repositoryGuid: string;
  status:
    | 'valid'
    | 'missing'
    | 'expired'
    | 'machine_mismatch'
    | 'repository_mismatch'
    | 'sequence_regression'
    | 'invalid_signature'
    | 'identity_mismatch'
    | 'cert_expired'
    | 'cert_invalid'
    | 'unknown';
  message?: string;
  runtimeValid: boolean;
  installed: boolean;
  issuedAt?: string;
  refreshRecommendedAt?: string;
  hardExpiresAt?: string;
  expiresAt?: string;
  machineId?: string;
  kind?: string;
  grandGuid?: string;
  datastoreId?: string;
  datastorePath?: string;
  /** Present = unattended backups for this repo have been failing on licensing. */
  blockedBackup?: RepoLicenseBlockedBackup;
  lastRenewal?: RepoLicenseRenewal;
}

async function readRemoteMachineId(sftp: SFTPClient, remoteRenetPath?: string): Promise<string> {
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

/**
 * Fetch the account license report, propagating the server's own failure.
 *
 * The account view of `subscription status` renders nothing BUT this report, so
 * a swallowed error there is indistinguishable from success: the verb exits 0
 * having printed nothing, and a real, actionable reason ("Token is bound to a
 * different IP address" on a token minted on another machine) is lost. Callers
 * whose output depends on the report use this variant so the reason reaches the
 * user; `fetchSubscriptionLicenseReport` below keeps the tolerant contract for
 * the one caller that degrades gracefully instead (`doctor`).
 */
export async function fetchSubscriptionLicenseReportOrThrow(): Promise<SubscriptionLicenseReport | null> {
  const tokenState = getSubscriptionTokenState();
  if (tokenState.kind !== 'ready') {
    return null;
  }

  try {
    const report = await accountServerFetch<SubscriptionLicenseReport>(
      '/account/api/v1/licenses/report'
    );
    telemetryService.setUserContext({
      subscriptionId: report.subscriptionId,
      subscriptionPlanCode: report.planCode,
      subscriptionStatus: report.status,
      subscriptionSource: TELEMETRY_SUBSCRIPTION_SOURCES.licenseReport,
    });
    return report;
  } catch (error) {
    telemetryService.trackError(error, { operation: 'license.fetch_report' });
    throw error;
  }
}

/**
 * Null-on-error view of the license report, for callers that render a degraded
 * result rather than an error (`doctor` races this against a timeout and shows
 * a warn row). Anything whose output IS the report must use the throwing
 * variant above instead.
 */
export async function fetchSubscriptionLicenseReport(): Promise<SubscriptionLicenseReport | null> {
  try {
    return await fetchSubscriptionLicenseReportOrThrow();
  } catch {
    return null;
  }
}

async function readLocalMachineId(): Promise<string> {
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
 * failure mode that made this worth fixing — measuring the wrong mount and
 * reporting the floor as though it were a measurement.
 */
async function measureRepoSizeGb(
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

export async function readMachineActivationStatus(
  machine: MachineConfig,
  sshPrivateKey: string,
  remoteRenetPath?: string,
  sharedSftp?: SFTPClient
): Promise<MachineActivationStatus | null> {
  const tokenState = getSubscriptionTokenState();
  if (tokenState.kind !== 'ready') {
    return null;
  }

  return withSharedOrPooledSftp(
    sharedSftp,
    sftpConfigForMachine(machine, sshPrivateKey),
    async (sftp) => {
      const machineId = await readRemoteMachineId(sftp, remoteRenetPath);
      const report = await fetchSubscriptionLicenseReport();
      if (!report) {
        return null;
      }

      const activation = report.machineSlots.machines.find(
        (entry) => entry.machineId === machineId
      );
      return {
        machineId,
        active: Boolean(activation),
        lastSeenAt: activation?.lastSeenAt,
        activeCount: report.machineSlots.active,
        maxCount: report.machineSlots.max,
      };
    }
  );
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

async function scanRemoteLicenseStatuses(
  sftp: SFTPClient,
  datastore: string,
  remoteRenetPath?: string
): Promise<RuntimeRepoLicenseStatus[]> {
  const renetPath = remoteRenetPath ?? DEFAULTS.CONTEXT.RENET_BINARY;
  const output = await sftp.exec(licenseScanCommand('license-status', renetPath, datastore));
  const parsed = JSON.parse(output) as unknown;
  return Array.isArray(parsed) ? (parsed as RuntimeRepoLicenseStatus[]) : [];
}

export async function readRuntimeRepoLicenseStatuses(
  machine: MachineConfig,
  sshPrivateKey: string,
  remoteRenetPath?: string,
  sharedSftp?: SFTPClient
): Promise<RuntimeRepoLicenseStatus[]> {
  return withSharedOrPooledSftp(
    sharedSftp,
    sftpConfigForMachine(machine, sshPrivateKey),
    async (sftp) => {
      const datastore = machine.datastore ?? DEFAULT_DATASTORE;
      return await scanRemoteLicenseStatuses(sftp, datastore, remoteRenetPath);
    }
  );
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
function clusterIdFor(machine: MachineConfig): string | undefined {
  return machine.cluster?.cluster;
}

export async function issueRepoLicense(
  machine: MachineConfig,
  sshPrivateKey: string,
  params: {
    repositoryGuid: string;
    grandGuid?: string;
    kind: 'grand' | 'fork';
    requestedSizeGb: number;
    luksUuid?: string;
    storageFingerprint?: string;
    datastoreId?: string;
  },
  remoteRenetPath?: string,
  sharedSftp?: SFTPClient
): Promise<boolean> {
  const tokenState = getSubscriptionTokenState();
  if (tokenState.kind !== 'ready') return false;

  return withSharedOrPooledSftp(
    sharedSftp,
    sftpConfigForMachine(machine, sshPrivateKey),
    async (sftp) => {
      const [machineId, clientMachineId] = await Promise.all([
        readRemoteMachineId(sftp, remoteRenetPath),
        readLocalMachineId(),
      ]);
      if (!machineId || !clientMachineId) return false;

      const { license } = await accountServerFetch<{ license: unknown }>(
        '/account/api/v1/licenses/activate-repo',
        {
          method: 'POST',
          body: {
            machineId,
            clientMachineId,
            repositoryGuid: params.repositoryGuid,
            grandGuid: params.grandGuid,
            kind: params.kind,
            requestedSizeGb: params.requestedSizeGb,
            luksUuid: params.luksUuid,
            storageFingerprint: params.storageFingerprint,
            datastoreId: params.datastoreId,
            clusterId: clusterIdFor(machine),
          },
        }
      );
      // The blob must land in the population renet reads for THIS datastore,
      // which is the same identity that was just stamped into the payload.
      await writeRepoLicense(sftp, params.repositoryGuid, license, params.datastoreId);
      return true;
    }
  );
}

/**
 * Identity proofs, size and datastore identity for ONE repo, read from renet's
 * own license scan.
 *
 * The scan is the source rather than a `stat` of our own, and that is a
 * correctness requirement, not a tidiness one. `storageFingerprint` is a signed
 * payload field whose exact bytes renet re-derives and compares
 * (pkg/license/identity.go); its format is `kind:size:mtime:mode` with Go's
 * FileMode bits, which no `stat -c` format string reproduces. The CLI used to
 * mint `%F:%d:%i:%s:%Y` here, a string that can never equal renet's, so every
 * non-LUKS repo (kube repos are directories, not LUKS images) carried a
 * fingerprint that would fail the moment renet's comparison started firing.
 * Reading the scan means there is exactly one producer of those bytes.
 *
 * It also answers WHICH datastore the repo lives in, which the machine's
 * primary-datastore path cannot: a repo in a named datastore needs that
 * datastore's identity both in the payload and in the store path.
 */
async function readRepoLicenseInputs(
  sftp: SFTPClient,
  datastore: string,
  repositoryGuid: string,
  remoteRenetPath?: string
): Promise<{
  luksUuid?: string;
  storageFingerprint?: string;
  datastoreId?: string;
  datastorePath?: string;
  requestedSizeGb?: number;
}> {
  try {
    const scanned = await scanRemoteRepoLicenses(sftp, datastore, remoteRenetPath);
    const entry = scanned.find((repo) => repo.repositoryGuid === repositoryGuid);
    if (entry) {
      return {
        luksUuid: entry.luksUuid,
        storageFingerprint: entry.storageFingerprint,
        datastoreId: entry.datastoreId,
        // The mount the machine itself reports for this repo. Better than
        // anything the client can derive, and it is the datastore the size
        // probe below must measure when the scan could not price the repo.
        datastorePath: entry.datastorePath,
        requestedSizeGb: entry.requestedSizeGb,
      };
    }
  } catch {
    // An older renet, or a scan that cannot read a datastore, must not stop a
    // reissue: an unproven license still beats no license.
  }
  return {};
}

export async function refreshRepoLicenseIdentity(
  machine: MachineConfig,
  sshPrivateKey: string,
  params: {
    repositoryGuid: string;
    grandGuid?: string;
    kind: 'grand' | 'fork';
    requestedSizeGb?: number;
    /**
     * The datastore identity the CALLER already resolved (the placement it just
     * provisioned into). A fallback, not an override: the scan below is the
     * better answer because it reads the repo's actual home. It matters when
     * the scan cannot answer at all — an older renet, or a datastore it failed
     * to read — where dropping to no identity would write the reissue to the
     * unscoped path that renet does not read for a datastore-resident repo.
     */
    datastoreId?: string;
    /**
     * Mount of the datastore this repo's image lives on, as the CALLER recorded
     * it (`repo.placement`). A fallback, on the same terms as `datastoreId`
     * above: the scan reports the machine's own `datastorePath` and that wins.
     *
     * It matters when the scan cannot price the repo — no licence installed
     * yet, or a scan that failed — and the size probe has to measure the image
     * itself. The machine's DEFAULT datastore is the wrong guess there for any
     * repo created with `repo create --datastore <d>`: the image is at
     * `/mnt/rediacc-ds/<d>/repositories/<guid>`, the probe found nothing, and
     * the reissue silently asked for the 1 GB floor.
     */
    datastoreMount?: string;
  },
  remoteRenetPath?: string,
  sharedSftp?: SFTPClient
): Promise<boolean> {
  const tokenState = getSubscriptionTokenState();
  if (tokenState.kind !== 'ready') return false;

  return withSharedOrPooledSftp(
    sharedSftp,
    sftpConfigForMachine(machine, sshPrivateKey),
    async (sftp) => {
      // The PRIMARY datastore for the scan below, not the repo's home: the scan
      // command passes --all-datastores, so it walks every attached named
      // datastore too and reports each repo tagged with its own datastorePath.
      // That is why the scan half of this function was never the bug.
      const datastore = machine.datastore ?? DEFAULT_DATASTORE;
      const scanned = await readRepoLicenseInputs(
        sftp,
        datastore,
        params.repositoryGuid,
        remoteRenetPath
      );
      const { datastoreMount, ...issueParams } = params;
      const requestedSizeGb =
        params.requestedSizeGb ??
        scanned.requestedSizeGb ??
        (await measureRepoSizeGb(sftp, params.repositoryGuid, [
          // Most authoritative first: the machine's own answer, then the
          // placement the caller recorded, then the machine default — which is
          // right only for a repo that really is on the default datastore.
          scanned.datastorePath,
          datastoreMount,
          datastore,
        ]));
      return issueRepoLicense(
        machine,
        sshPrivateKey,
        {
          ...issueParams,
          requestedSizeGb,
          luksUuid: scanned.luksUuid,
          storageFingerprint: scanned.storageFingerprint,
          datastoreId: scanned.datastoreId ?? params.datastoreId,
        },
        remoteRenetPath,
        sftp
      );
    }
  );
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

async function writeRepoLicense(
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
  // GC the legacy flat file only. Files for other keyIds are never touched —
  // that no-clobber property is what lets universes coexist. The flat file
  // predates both the per-key layout and datastore scoping, so it is removed
  // from the unscoped root regardless of which population we just wrote to:
  // renet reads it in neither case, and leaving it behind only confuses the
  // next person to look in that directory.
  await sftp.exec(`sudo rm -f "${REPO_LICENSE_DIR}/${repositoryGuid}.json"`);
}

async function scanRemoteRepoLicenses(
  sftp: SFTPClient,
  datastore: string,
  remoteRenetPath?: string
): Promise<RemoteRepoLicenseScanEntry[]> {
  const renetPath = remoteRenetPath ?? DEFAULTS.CONTEXT.RENET_BINARY;
  const output = await sftp.exec(licenseScanCommand('license-scan', renetPath, datastore));
  const parsed = JSON.parse(output) as RemoteRepoLicenseScanEntry[];
  return Array.isArray(parsed) ? parsed : [];
}

function resolveKnownRemoteRepos(
  remoteRepos: RemoteRepoLicenseScanEntry[],
  repoByGuid: Map<string, { grandGuid?: string }>
): {
  knownRemoteRepos: (RemoteRepoLicenseScanEntry & {
    grandGuid?: string;
    kind: 'grand' | 'fork';
  })[];
  unknownRepoFailures: { repositoryGuid: string; error: string }[];
} {
  const unknownRepoFailures: { repositoryGuid: string; error: string }[] = [];
  const knownRemoteRepos = remoteRepos.flatMap((repo) => {
    const resolved = resolveRepoBatchKind(repo.repositoryGuid, repoByGuid);
    if (!resolved) {
      unknownRepoFailures.push({
        repositoryGuid: repo.repositoryGuid,
        error: 'Repository exists on target machine but is not tracked in local config',
      });
      return [];
    }
    return [{ ...repo, grandGuid: resolved.grandGuid, kind: resolved.kind }];
  });
  return { knownRemoteRepos, unknownRepoFailures };
}

async function applyBatchRefreshResults(
  sftp: SFTPClient,
  results: {
    repositoryGuid: string;
    status: 'issued' | 'refreshed' | 'unchanged' | 'failed';
    license?: unknown;
    error?: string;
  }[],
  failures: { repositoryGuid: string; error: string }[],
  datastoreIdByGuid: Map<string, string | undefined>
): Promise<{ issued: number; refreshed: number; unchanged: number; failed: number }> {
  let issued = 0;
  let refreshed = 0;
  let unchanged = 0;
  let failed = failures.length;

  for (const result of results) {
    const counts = await applySingleBatchRefreshResult(
      sftp,
      result,
      failures,
      datastoreIdByGuid.get(result.repositoryGuid)
    );
    issued += counts.issued;
    refreshed += counts.refreshed;
    unchanged += counts.unchanged;
    failed += counts.failed;
  }

  return { issued, refreshed, unchanged, failed };
}

async function applySingleBatchRefreshResult(
  sftp: SFTPClient,
  result: {
    repositoryGuid: string;
    status: 'issued' | 'refreshed' | 'unchanged' | 'failed';
    license?: unknown;
    error?: string;
  },
  failures: { repositoryGuid: string; error: string }[],
  datastoreId: string | undefined
): Promise<{ issued: number; refreshed: number; unchanged: number; failed: number }> {
  if ((result.status === 'issued' || result.status === 'refreshed') && result.license) {
    await writeRepoLicense(sftp, result.repositoryGuid, result.license, datastoreId);
  }
  if (result.status === 'issued') {
    return { issued: 1, refreshed: 0, unchanged: 0, failed: 0 };
  }
  if (result.status === 'refreshed') {
    return { issued: 0, refreshed: 1, unchanged: 0, failed: 0 };
  }
  if (result.status === 'unchanged') {
    return { issued: 0, refreshed: 0, unchanged: 1, failed: 0 };
  }
  failures.push({
    repositoryGuid: result.repositoryGuid,
    error: result.error ?? DEFAULTS.CLOUD.UNKNOWN_ERROR,
  });
  return { issued: 0, refreshed: 0, unchanged: 0, failed: 1 };
}

function resolveRepoBatchKind(
  repositoryGuid: string,
  repoByGuid: Map<string, { grandGuid?: string }>
): { kind: 'grand' | 'fork'; grandGuid?: string } | null {
  const repo = repoByGuid.get(repositoryGuid);
  if (!repo) {
    return null;
  }
  const grandGuid = repo.grandGuid;
  if (grandGuid && grandGuid !== repositoryGuid) {
    return { kind: 'fork', grandGuid };
  }
  return { kind: 'grand', grandGuid: grandGuid ?? repositoryGuid };
}

function pickServerErrorSample(
  failures: { repositoryGuid: string; error: string }[],
  serverFailuresStart: number
): string | undefined {
  if (failures.length === 0) return undefined;
  const idx = serverFailuresStart < failures.length ? serverFailuresStart : 0;
  return failures[idx].error.slice(0, 200);
}

export async function refreshRepoLicensesBatch(
  machine: MachineConfig,
  sshPrivateKey: string,
  remoteRenetPath?: string,
  sharedSftp?: SFTPClient
): Promise<RepoBatchRefreshResult> {
  const tokenState = getSubscriptionTokenState();
  if (tokenState.kind !== 'ready') {
    return {
      scanned: 0,
      issued: 0,
      refreshed: 0,
      unchanged: 0,
      failed: 0,
      valid: 0,
      invalidSignatureDetected: 0,
      failures: [{ repositoryGuid: '*', error: 'Subscription token is not ready' }],
      recoveryFailureMode: 'token_not_ready',
      serverErrorSample: undefined,
    };
  }

  return withSharedOrPooledSftp(sharedSftp, sftpConfigForMachine(machine, sshPrivateKey), (sftp) =>
    runRepoLicenseBatch(sftp, machine, remoteRenetPath)
  );
}

/** Scan, batch-refresh and install repo licenses over an established connection. */
async function runRepoLicenseBatch(
  sftp: SFTPClient,
  machine: MachineConfig,
  remoteRenetPath?: string
): Promise<RepoBatchRefreshResult> {
  const datastore = machine.datastore ?? DEFAULT_DATASTORE;
  const [machineId, clientMachineId, remoteRepos, localRepos, licenseStatuses] = await Promise.all([
    readRemoteMachineId(sftp, remoteRenetPath),
    readLocalMachineId(),
    scanRemoteRepoLicenses(sftp, datastore, remoteRenetPath),
    configService.listRepositories().catch((err: unknown) => {
      telemetryService.trackError(err, { operation: 'license.list_repositories' });
      return [];
    }),
    scanRemoteLicenseStatuses(sftp, datastore, remoteRenetPath).catch(() => []),
  ]);

  // Only machine_mismatch force-reissues (the documented remedy the guidance
  // points users at). invalid_signature no longer triggers a reissue: with the
  // per-signer license layout a foreign-universe file is simply never selected,
  // so a genuine invalid_signature means the machine's OWN key can't validate
  // its own file — that must fail fast, not loop reissuing (matches
  // subscription-licensing.md).
  const forceReissueGuids = new Set(
    licenseStatuses.filter((s) => s.status === 'machine_mismatch').map((s) => s.repositoryGuid)
  );

  const repoByGuid = new Map(
    localRepos.map((entry) => [entry.config.repositoryGuid, { grandGuid: entry.config.grandGuid }])
  );
  const { knownRemoteRepos, unknownRepoFailures } = resolveKnownRemoteRepos(
    remoteRepos,
    repoByGuid
  );

  if (knownRemoteRepos.length === 0) {
    return {
      scanned: remoteRepos.length,
      issued: 0,
      refreshed: 0,
      unchanged: 0,
      failed: unknownRepoFailures.length,
      valid: 0,
      invalidSignatureDetected: forceReissueGuids.size,
      failures: unknownRepoFailures,
      recoveryFailureMode: remoteRepos.length > 0 ? 'no_known_repos' : 'server_rejected_all',
      serverErrorSample: undefined,
    };
  }

  const body = await accountServerFetch<{
    results: {
      repositoryGuid: string;
      status: 'issued' | 'refreshed' | 'unchanged' | 'failed';
      license?: unknown;
      error?: string;
    }[];
  }>('/account/api/v1/licenses/activate-repo-batch', {
    method: 'POST',
    body: {
      machineId,
      clientMachineId,
      clusterId: clusterIdFor(machine),
      repos: knownRemoteRepos.map((repo) => {
        const forceReissue = forceReissueGuids.has(repo.repositoryGuid);
        return {
          machineId,
          clientMachineId,
          repositoryGuid: repo.repositoryGuid,
          grandGuid: repo.grandGuid,
          kind: repo.kind,
          requestedSizeGb: repo.requestedSizeGb,
          luksUuid: repo.luksUuid,
          storageFingerprint: repo.storageFingerprint,
          datastoreId: repo.datastoreId,
          clusterId: clusterIdFor(machine),
          currentRefreshRecommendedAt: forceReissue ? undefined : repo.currentRefreshRecommendedAt,
          currentHardExpiresAt: forceReissue ? undefined : repo.currentHardExpiresAt,
        };
      }),
    },
  });

  // Each blob goes back to the population its repo was scanned from. Two repos
  // in a batch can legitimately carry the SAME guid on one machine (a same-node
  // datastore fork does not remint guids), which is exactly why the store is
  // scoped by datastore and why this map is keyed the way the server keys its
  // results.
  const datastoreIdByGuid = new Map(
    knownRemoteRepos.map((repo) => [repo.repositoryGuid, repo.datastoreId])
  );

  const failures: { repositoryGuid: string; error: string }[] = [...unknownRepoFailures];
  const serverFailuresBefore = failures.length;
  const { issued, refreshed, unchanged, failed } = await applyBatchRefreshResults(
    sftp,
    body.results,
    failures,
    datastoreIdByGuid
  );

  const validCount = issued + refreshed + unchanged;
  const recoveryFailureMode: RepoBatchRecoveryFailureMode =
    validCount > 0 ? null : 'server_rejected_all';
  const serverErrorSample =
    validCount === 0 ? pickServerErrorSample(failures, serverFailuresBefore) : undefined;
  return {
    scanned: remoteRepos.length,
    issued,
    refreshed,
    unchanged,
    failed,
    valid: validCount,
    invalidSignatureDetected: forceReissueGuids.size,
    failures,
    recoveryFailureMode,
    serverErrorSample,
  };
}
