/**
 * `refreshRepoLicensesBatch`: scan every repo on a machine, renew or issue
 * their licenses in one account-server call, and install the returned blobs.
 * Re-exported from `license.ts`.
 */

import { DEFAULTS } from '@rediacc/shared/config';
import type { SFTPClient } from '../../remote/sftp/index.js';
import type { MachineConfig } from '../../types/index.js';
import { shellQuote } from '../../utils/shell-quote.js';
import {
  expectedAccountServerOrigin,
  LICENSE_DIR,
  LISTING_COMPLETE_MARKER,
  licenseOriginsFromListing,
} from '../backup/backup-store-universe.js';
import { configService } from '../config/config-resources.js';
import { sftpConfigForMachine, withSharedOrPooledSftp } from '../machine/machine-connection.js';
import { telemetryService } from '../telemetry/telemetry.js';
import { accountServerFetch } from './account-client.js';
import {
  clusterIdFor,
  DEFAULT_DATASTORE,
  readLocalMachineId,
  readRemoteMachineId,
  scanRemoteLicenseStatuses,
  scanRemoteRepoLicenses,
  writeRepoLicense,
} from './license-machine.js';
import type {
  RemoteRepoLicenseScanEntry,
  RepoBatchRecoveryFailureMode,
  RepoBatchRefreshResult,
} from './license-types.js';
import { getSubscriptionServerUrl, getSubscriptionTokenState } from './subscription-auth.js';

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
  machineName: string,
  results: {
    repositoryGuid: string;
    status: 'issued' | 'refreshed' | 'unchanged' | 'failed';
    license?: unknown;
    error?: string;
  }[],
  failures: { repositoryGuid: string; error: string }[],
  datastoreIdByGuid: Map<string, string | undefined>
): Promise<{
  issued: number;
  refreshed: number;
  unchanged: number;
  failed: number;
}> {
  let issued = 0;
  let refreshed = 0;
  let unchanged = 0;
  let failed = failures.length;

  for (const result of results) {
    const counts = await applySingleBatchRefreshResult(
      machineName,
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
  machineName: string,
  result: {
    repositoryGuid: string;
    status: 'issued' | 'refreshed' | 'unchanged' | 'failed';
    license?: unknown;
    error?: string;
  },
  failures: { repositoryGuid: string; error: string }[],
  datastoreId: string | undefined
): Promise<{
  issued: number;
  refreshed: number;
  unchanged: number;
  failed: number;
}> {
  if ((result.status === 'issued' || result.status === 'refreshed') && result.license) {
    await writeRepoLicense(machineName, result.repositoryGuid, result.license, datastoreId);
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

function requiredRepoErrorSample(
  failures: { repositoryGuid: string; error: string }[],
  requiredGuid: string
): string {
  const own = failures.find((f) => f.repositoryGuid.toLowerCase() === requiredGuid.toLowerCase());
  return (own?.error ?? `Repository ${requiredGuid} was not licensed by the account server`).slice(
    0,
    200
  );
}

export function refreshRepoLicensesBatch(
  machineName: string,
  machine: MachineConfig,
  sshPrivateKey: string,
  remoteRenetPath?: string,
  sharedSftp?: SFTPClient,
  requiredGuid?: string,
  scanned?: RemoteRepoLicenseScanEntry[]
): Promise<RepoBatchRefreshResult> {
  const tokenState = getSubscriptionTokenState();
  if (tokenState.kind !== 'ready') {
    return Promise.resolve({
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
    });
  }

  return withSharedOrPooledSftp(sharedSftp, sftpConfigForMachine(machine, sshPrivateKey), (sftp) =>
    runRepoLicenseBatch(sftp, machineName, machine, remoteRenetPath, requiredGuid, scanned)
  );
}

/**
 * The guids whose installed licence names an account-server origin other than `expectedOrigin`, from a listing of
 * `<guid>\t<base64 licence file>` lines. The server compares dates only, so a fresh licence from another origin
 * (the config's account server moved) is never reissued unless the request drops its current dates. A licence
 * without a `renewalUrl` names no origin and is not counted.
 */
export function guidsWithForeignLicenseOrigin(
  listing: string,
  expectedOrigin: string
): Set<string> {
  const guids = new Set<string>();
  for (const line of listing.split('\n')) {
    const [guid, encoded] = line.trim().split('\t');
    if (!guid || !encoded) continue;
    if (licenseOriginsFromListing(encoded).some((origin) => origin !== expectedOrigin)) {
      guids.add(guid.toLowerCase());
    }
  }
  return guids;
}

/**
 * Reads every installed repo licence on the machine and returns the guids issued by another account server than
 * this config's. Throws when the listing cannot be read: an empty answer would leave the stale licence unchanged
 * and report a clean refresh.
 */
export async function foreignOriginLicenseGuids(
  sftp: Pick<SFTPClient, 'exec'>,
  machineName: string
): Promise<Set<string>> {
  const script =
    `set -e; for f in ${LICENSE_DIR}/repos/*/*.json ${LICENSE_DIR}/datastores/*/repos/*/*.json; ` +
    `do if [ -f "$f" ]; then printf '%s\\t' "$(basename "$(dirname "$f")")"; base64 -w0 "$f"; echo; fi; done; echo ${LISTING_COMPLETE_MARKER}`;
  let listing: string;
  try {
    listing = await sftp.exec(`sudo -n sh -c ${shellQuote(script)}`);
  } catch (err) {
    throw new Error(
      `Cannot read the installed licences on ${machineName} to compare their issuing origin: ${err instanceof Error ? err.message : String(err)}`
    );
  }
  if (!listing.split('\n').some((line) => line.trim() === LISTING_COMPLETE_MARKER)) {
    throw new Error(
      `Cannot read the installed licences on ${machineName} to compare their issuing origin: the listing was cut short`
    );
  }
  const expected = expectedAccountServerOrigin() ?? getSubscriptionServerUrl();
  return guidsWithForeignLicenseOrigin(listing, expected);
}

/** Adds each scanned repo whose guid is in the lowercase `foreignGuids` set to `target`, under the scan's own spelling. */
function addForeignOriginRepos(
  target: Set<string>,
  foreignGuids: Set<string>,
  remoteRepos: RemoteRepoLicenseScanEntry[]
): void {
  for (const repo of remoteRepos) {
    if (foreignGuids.has(repo.repositoryGuid.toLowerCase())) target.add(repo.repositoryGuid);
  }
}

/** The caller's `license-scan` answer when it holds one, else a scan job of its own. */
function remoteScan(
  machineName: string,
  datastore: string,
  scanned?: RemoteRepoLicenseScanEntry[]
): Promise<RemoteRepoLicenseScanEntry[]> {
  return scanned ? Promise.resolve(scanned) : scanRemoteRepoLicenses(machineName, datastore);
}

/**
 * Scan, batch-refresh and install repo licenses over an established connection.
 * With `requiredGuid` (the repo renet refused) the batch only counts as a
 * recovery when THAT repo came back licensed; without it any licensed repo does.
 * `scanned` is a `license-scan` answer the caller already holds (the `subscription refresh` job's output), which
 * spares a second scan job.
 */
async function runRepoLicenseBatch(
  sftp: SFTPClient,
  machineName: string,
  machine: MachineConfig,
  remoteRenetPath?: string,
  requiredGuid?: string,
  scanned?: RemoteRepoLicenseScanEntry[]
): Promise<RepoBatchRefreshResult> {
  const datastore = machine.datastore ?? DEFAULT_DATASTORE;
  const [machineId, clientMachineId, remoteRepos, localRepos, licenseStatuses, foreignOriginGuids] =
    await Promise.all([
      readRemoteMachineId(sftp, remoteRenetPath),
      readLocalMachineId(),
      remoteScan(machineName, datastore, scanned),
      configService.listRepositories().catch((err: unknown) => {
        telemetryService.trackError(err, {
          operation: 'license.list_repositories',
        });
        return [];
      }),
      scanRemoteLicenseStatuses(machineName, datastore).catch(() => []),
      foreignOriginLicenseGuids(sftp, machineName),
    ]);

  // `identity_mismatch` joins it: after `backup snapshot --accept-identity-change` the image's UUID is new, an unexpired licence answers `unchanged` to a plain refresh, and the repository stays unmountable until the refresh window opens. Only a forced GUID is reissued.
  // machine_mismatch force-reissues (the documented remedy the guidance points users at). invalid_signature no longer triggers a reissue: with the per-signer license layout a foreign-universe file is simply never selected, so a genuine invalid_signature means the machine's OWN key can't validate its own file, that must fail fast, not loop reissuing (matches subscription-licensing.md).
  const forceReissueGuids = new Set(
    licenseStatuses
      .filter((s) => s.status === 'machine_mismatch' || s.status === 'identity_mismatch')
      .map((s) => s.repositoryGuid)
  );
  // A licence issued by another account server (the config's server moved) is reissued here too: its dates are fresh, so the server would answer `unchanged`.
  addForeignOriginRepos(forceReissueGuids, foreignOriginGuids, remoteRepos);

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

  // Each blob goes back to the population its repo was scanned from. Two repos in a batch can legitimately carry the SAME guid on one machine (a same-node datastore fork does not remint guids), which is exactly why the store is scoped by datastore and why this map is keyed the way the server keys its results.
  const datastoreIdByGuid = new Map(
    knownRemoteRepos.map((repo) => [repo.repositoryGuid, repo.datastoreId])
  );

  const failures: { repositoryGuid: string; error: string }[] = [...unknownRepoFailures];
  const serverFailuresBefore = failures.length;
  const { issued, refreshed, unchanged, failed } = await applyBatchRefreshResults(
    machineName,
    body.results,
    failures,
    datastoreIdByGuid
  );

  const validCount = issued + refreshed + unchanged;
  const recovered = requiredGuid
    ? body.results.some(
        (r) =>
          r.repositoryGuid.toLowerCase() === requiredGuid.toLowerCase() &&
          (r.status === 'issued' || r.status === 'refreshed' || r.status === 'unchanged')
      )
    : validCount > 0;
  const recoveryFailureMode: RepoBatchRecoveryFailureMode = recovered
    ? null
    : 'server_rejected_all';
  const serverErrorSample = recovered
    ? undefined
    : ((requiredGuid ? requiredRepoErrorSample(failures, requiredGuid) : undefined) ??
      pickServerErrorSample(failures, serverFailuresBefore));
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
