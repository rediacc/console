/* eslint-disable max-lines */
import { DEFAULTS } from '@rediacc/shared/config';
import { TELEMETRY_SUBSCRIPTION_SOURCES } from '@rediacc/shared/telemetry';
import { SFTPClient } from '@rediacc/shared-desktop/sftp';
import type { MachineConfig } from '../types/index.js';
import { accountServerFetch } from './account-client.js';
import { configService } from './config-resources.js';
import { getSubscriptionTokenState } from './subscription-auth.js';
import { telemetryService } from './telemetry.js';

const LICENSE_DIR = '/var/lib/rediacc/license';
const REPO_LICENSE_DIR = `${LICENSE_DIR}/repos`;
const CLIENT_MACHINE_ID_PATH = '/etc/machine-id';
const DEFAULT_DATASTORE = '/mnt/rediacc';

interface RemoteRepoLicenseScanEntry {
  repositoryGuid: string;
  requestedSizeGb: number;
  luksUuid?: string;
  storageFingerprint?: string;
  currentRefreshRecommendedAt?: string;
  currentHardExpiresAt?: string;
}

export interface RepoBatchRefreshResult {
  scanned: number;
  issued: number;
  refreshed: number;
  unchanged: number;
  failed: number;
  valid: number;
  invalidSignatureDetected: number;
  failures: { repositoryGuid: string; error: string }[];
}

export interface RepoLicenseIssuancesUsage {
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
    machines: { machineId: string; lastSeenAt: string; activatedAt?: string }[];
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

export async function fetchSubscriptionLicenseReport(): Promise<SubscriptionLicenseReport | null> {
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
    return null;
  }
}

async function readLocalMachineId(): Promise<string> {
  const { readFile } = await import('node:fs/promises');
  return (await readFile(CLIENT_MACHINE_ID_PATH, 'utf-8')).trim();
}

async function readRepoIdentity(
  sftp: SFTPClient,
  datastore: string,
  repositoryGuid: string
): Promise<{ luksUuid?: string; storageFingerprint?: string }> {
  const repoPath = `${datastore}/repositories/${repositoryGuid}`;
  const luksUuid = (
    await sftp.exec(`sudo sh -lc 'cryptsetup luksUUID "${repoPath}" 2>/dev/null || true'`)
  ).trim();
  if (luksUuid) {
    return { luksUuid };
  }

  const storageFingerprint = (
    await sftp.exec(
      `sudo sh -lc 'if [ -e "${repoPath}" ]; then stat -c "%F:%d:%i:%s:%Y" "${repoPath}"; fi'`
    )
  ).trim();
  return storageFingerprint ? { storageFingerprint } : {};
}

async function readRepoSizeGb(
  sftp: SFTPClient,
  datastore: string,
  repositoryGuid: string
): Promise<number> {
  const repoPath = `${datastore}/repositories/${repositoryGuid}`;
  const bytesOutput = await sftp.exec(
    `sudo sh -lc 'if [ -e "${repoPath}" ]; then stat -c %s "${repoPath}" 2>/dev/null; else echo 0; fi'`
  );
  const bytes = Number.parseInt(bytesOutput.trim(), 10);
  return Math.max(1, Math.ceil((Number.isFinite(bytes) ? bytes : 0) / (1024 * 1024 * 1024)));
}

const MACHINE_LICENSE_PATH = `${LICENSE_DIR}/machine.json`;

async function refreshActivation(
  _serverUrl: string,
  _token: string,
  machineId: string
): Promise<{ ok: boolean; signedBlob?: unknown }> {
  try {
    const body = await accountServerFetch<{ activation?: unknown; signedBlob?: unknown }>(
      '/account/api/v1/licenses/activate',
      { method: 'POST', body: { machineId } }
    );
    return { ok: true, signedBlob: body.signedBlob };
  } catch (error) {
    telemetryService.trackError(error, { operation: 'license.refresh_activation' });
    return { ok: false };
  }
}

async function writeMachineLicense(sftp: SFTPClient, signedBlob: unknown): Promise<void> {
  await sftp.exec(`sudo mkdir -p ${LICENSE_DIR}`);
  await sftp.execStreaming(`sudo tee ${MACHINE_LICENSE_PATH} > /dev/null`, {
    stdin: JSON.stringify(signedBlob, null, 2),
  });
  await sftp.exec(`sudo chmod 640 ${MACHINE_LICENSE_PATH}`);
}

export async function refreshMachineActivation(
  machine: MachineConfig,
  sshPrivateKey: string,
  remoteRenetPath?: string,
  sharedSftp?: SFTPClient
): Promise<boolean> {
  const tokenState = getSubscriptionTokenState();
  if (tokenState.kind !== 'ready') return false;

  const sftp =
    sharedSftp ??
    new SFTPClient({
      host: machine.ip,
      port: machine.port ?? DEFAULTS.SSH.PORT,
      username: machine.user,
      privateKey: sshPrivateKey,
    });
  const ownsConnection = !sharedSftp;

  try {
    if (ownsConnection) await sftp.connect();
    const machineId = await readRemoteMachineId(sftp, remoteRenetPath);
    if (!machineId) return false;

    const result = await refreshActivation(tokenState.serverUrl, tokenState.token.token, machineId);
    if (!result.ok) return false;

    // Write the signed subscription blob to the remote machine for renet to validate
    if (result.signedBlob) {
      await writeMachineLicense(sftp, result.signedBlob);
    }

    return true;
  } finally {
    if (ownsConnection) sftp.close();
  }
}

export async function readMachineActivationStatus(
  machine: MachineConfig,
  sshPrivateKey: string,
  remoteRenetPath?: string
): Promise<MachineActivationStatus | null> {
  const tokenState = getSubscriptionTokenState();
  if (tokenState.kind !== 'ready') {
    return null;
  }

  const sftp = new SFTPClient({
    host: machine.ip,
    port: machine.port ?? DEFAULTS.SSH.PORT,
    username: machine.user,
    privateKey: sshPrivateKey,
  });

  try {
    await sftp.connect();
    const machineId = await readRemoteMachineId(sftp, remoteRenetPath);
    const report = await fetchSubscriptionLicenseReport();
    if (!report) {
      return null;
    }

    const activation = report.machineSlots.machines.find((entry) => entry.machineId === machineId);
    return {
      machineId,
      active: Boolean(activation),
      lastSeenAt: activation?.lastSeenAt,
      activeCount: report.machineSlots.active,
      maxCount: report.machineSlots.max,
    };
  } finally {
    sftp.close();
  }
}

async function scanRemoteLicenseStatuses(
  sftp: SFTPClient,
  datastore: string,
  remoteRenetPath?: string
): Promise<RuntimeRepoLicenseStatus[]> {
  const renetPath = remoteRenetPath ?? DEFAULTS.CONTEXT.RENET_BINARY;
  const output = await sftp.exec(
    `sudo ${renetPath} repository license-status --datastore '${datastore}' --output json`
  );
  const parsed = JSON.parse(output) as unknown;
  return Array.isArray(parsed) ? (parsed as RuntimeRepoLicenseStatus[]) : [];
}

export async function readRuntimeRepoLicenseStatuses(
  machine: MachineConfig,
  sshPrivateKey: string,
  remoteRenetPath?: string,
  sharedSftp?: SFTPClient
): Promise<RuntimeRepoLicenseStatus[]> {
  const sftp =
    sharedSftp ??
    new SFTPClient({
      host: machine.ip,
      port: machine.port ?? DEFAULTS.SSH.PORT,
      username: machine.user,
      privateKey: sshPrivateKey,
    });
  const ownsConnection = !sharedSftp;

  try {
    if (ownsConnection) await sftp.connect();
    const datastore = machine.datastore ?? DEFAULT_DATASTORE;
    return await scanRemoteLicenseStatuses(sftp, datastore, remoteRenetPath);
  } finally {
    if (ownsConnection) sftp.close();
  }
}

async function issueRepoLicense(
  machine: MachineConfig,
  sshPrivateKey: string,
  params: {
    repositoryGuid: string;
    grandGuid?: string;
    kind: 'grand' | 'fork';
    requestedSizeGb: number;
    luksUuid?: string;
    storageFingerprint?: string;
  },
  remoteRenetPath?: string
): Promise<boolean> {
  const tokenState = getSubscriptionTokenState();
  if (tokenState.kind !== 'ready') return false;

  const sftp = new SFTPClient({
    host: machine.ip,
    port: machine.port ?? DEFAULTS.SSH.PORT,
    username: machine.user,
    privateKey: sshPrivateKey,
  });

  try {
    await sftp.connect();
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
        },
      }
    );
    await sftp.exec(`sudo mkdir -p ${REPO_LICENSE_DIR}`);
    const repoLicenseFile = `${REPO_LICENSE_DIR}/${params.repositoryGuid}.json`;
    await sftp.execStreaming(`sudo tee ${repoLicenseFile} > /dev/null`, {
      stdin: JSON.stringify(license, null, 2),
    });
    await sftp.exec(`sudo chmod 640 ${repoLicenseFile}`);
    return true;
  } finally {
    sftp.close();
  }
}

export async function refreshRepoLicenseIdentity(
  machine: MachineConfig,
  sshPrivateKey: string,
  params: {
    repositoryGuid: string;
    grandGuid?: string;
    kind: 'grand' | 'fork';
    requestedSizeGb?: number;
  },
  remoteRenetPath?: string
): Promise<boolean> {
  const tokenState = getSubscriptionTokenState();
  if (tokenState.kind !== 'ready') return false;

  const sftp = new SFTPClient({
    host: machine.ip,
    port: machine.port ?? DEFAULTS.SSH.PORT,
    username: machine.user,
    privateKey: sshPrivateKey,
  });

  try {
    await sftp.connect();
    const datastore = machine.datastore ?? DEFAULT_DATASTORE;
    const [identity, requestedSizeGb] = await Promise.all([
      readRepoIdentity(sftp, datastore, params.repositoryGuid),
      params.requestedSizeGb
        ? Promise.resolve(params.requestedSizeGb)
        : readRepoSizeGb(sftp, datastore, params.repositoryGuid),
    ]);
    return issueRepoLicense(
      machine,
      sshPrivateKey,
      {
        ...params,
        requestedSizeGb,
        ...identity,
      },
      remoteRenetPath
    );
  } finally {
    sftp.close();
  }
}

async function writeRepoLicense(
  sftp: SFTPClient,
  repositoryGuid: string,
  license: unknown
): Promise<void> {
  await sftp.exec(`sudo mkdir -p ${REPO_LICENSE_DIR}`);
  const repoLicenseFile = `${REPO_LICENSE_DIR}/${repositoryGuid}.json`;
  await sftp.execStreaming(`sudo tee ${repoLicenseFile} > /dev/null`, {
    stdin: JSON.stringify(license, null, 2),
  });
  await sftp.exec(`sudo chmod 640 ${repoLicenseFile}`);
}

async function scanRemoteRepoLicenses(
  sftp: SFTPClient,
  datastore: string,
  remoteRenetPath?: string
): Promise<RemoteRepoLicenseScanEntry[]> {
  const renetPath = remoteRenetPath ?? DEFAULTS.CONTEXT.RENET_BINARY;
  const output = await sftp.exec(
    `sudo ${renetPath} repository license-scan --datastore '${datastore}' --output json`
  );
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
  failures: { repositoryGuid: string; error: string }[]
): Promise<{ issued: number; refreshed: number; unchanged: number; failed: number }> {
  let issued = 0;
  let refreshed = 0;
  let unchanged = 0;
  let failed = failures.length;

  for (const result of results) {
    const counts = await applySingleBatchRefreshResult(sftp, result, failures);
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
  failures: { repositoryGuid: string; error: string }[]
): Promise<{ issued: number; refreshed: number; unchanged: number; failed: number }> {
  if ((result.status === 'issued' || result.status === 'refreshed') && result.license) {
    await writeRepoLicense(sftp, result.repositoryGuid, result.license);
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
    };
  }

  const sftp =
    sharedSftp ??
    new SFTPClient({
      host: machine.ip,
      port: machine.port ?? DEFAULTS.SSH.PORT,
      username: machine.user,
      privateKey: sshPrivateKey,
    });
  const ownsConnection = !sharedSftp;

  try {
    if (ownsConnection) await sftp.connect();
    const datastore = machine.datastore ?? DEFAULT_DATASTORE;
    const [machineId, clientMachineId, remoteRepos, localRepos, licenseStatuses] =
      await Promise.all([
        readRemoteMachineId(sftp, remoteRenetPath),
        readLocalMachineId(),
        scanRemoteRepoLicenses(sftp, datastore, remoteRenetPath),
        configService.listRepositories().catch((err: unknown) => {
          telemetryService.trackError(err, { operation: 'license.list_repositories' });
          return [];
        }),
        scanRemoteLicenseStatuses(sftp, datastore, remoteRenetPath).catch(() => []),
      ]);

    const forceReissueGuids = new Set(
      licenseStatuses
        .filter((s) => s.status === 'invalid_signature' || s.status === 'machine_mismatch')
        .map((s) => s.repositoryGuid)
    );

    const repoByGuid = new Map(
      localRepos.map((entry) => [
        entry.config.repositoryGuid,
        { grandGuid: entry.config.grandGuid },
      ])
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
            currentRefreshRecommendedAt: forceReissue
              ? undefined
              : repo.currentRefreshRecommendedAt,
            currentHardExpiresAt: forceReissue ? undefined : repo.currentHardExpiresAt,
          };
        }),
      },
    });

    const failures: { repositoryGuid: string; error: string }[] = [...unknownRepoFailures];
    const { issued, refreshed, unchanged, failed } = await applyBatchRefreshResults(
      sftp,
      body.results,
      failures
    );

    return {
      scanned: remoteRepos.length,
      issued,
      refreshed,
      unchanged,
      failed,
      valid: issued + refreshed + unchanged,
      invalidSignatureDetected: forceReissueGuids.size,
      failures,
    };
  } finally {
    if (ownsConnection) sftp.close();
  }
}
