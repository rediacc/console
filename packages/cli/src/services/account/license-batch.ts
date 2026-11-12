/**
 * `refreshRepoLicensesBatch`: scan every repo on a machine, renew or issue
 * their licenses in one account-server call, and install the returned blobs.
 * Re-exported from `license.ts`.
 */

import { DEFAULTS } from '@rediacc/shared/config';
import { BAKED_IN_REGIONS } from '@rediacc/shared/regions';
import { t } from '../../i18n/index.js';
import type { SFTPClient } from '../../remote/sftp/index.js';
import type { MachineConfig } from '../../types/index.js';
import { expectedAccountServerOrigin } from '../backup/backup-store-universe.js';
import { configService } from '../config/config-resources.js';
import { outputService } from '../core/output.js';
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

/** How a batch treats licences another account server issued. */
export interface RepoBatchRefreshOptions {
  /**
   * Reissue licences whose `renewalUrl` names another account server from this config's server, moving them over.
   * Only `subscription refresh --adopt-origin` sets it; every other batch leaves such a licence untouched and warns.
   */
  adoptOrigin?: boolean;
}

/** The refusal a batch that sent nothing reports: the foreign-origin skip, the required repo's own when it was one. */
function foreignSkipSample(
  failures: { repositoryGuid: string; error: string }[],
  foreignSkips: { repositoryGuid: string; error: string }[],
  requiredGuid: string | undefined
): string | undefined {
  if (foreignSkips.length === 0) return undefined;
  if (requiredGuid) return requiredRepoErrorSample(failures, requiredGuid);
  return foreignSkips[0].error.slice(0, 200);
}

export function refreshRepoLicensesBatch(
  machineName: string,
  machine: MachineConfig,
  sshPrivateKey: string,
  remoteRenetPath?: string,
  sharedSftp?: SFTPClient,
  requiredGuid?: string,
  scanned?: RemoteRepoLicenseScanEntry[],
  options: RepoBatchRefreshOptions = {}
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
    runRepoLicenseBatch(
      sftp,
      machineName,
      machine,
      remoteRenetPath,
      requiredGuid,
      scanned,
      options.adoptOrigin === true
    )
  );
}

/**
 * The config's account-server origin. A server URL that does not parse as a URL is refused: comparing a raw URL with
 * bare origins would count every licence as foreign and reissue all.
 */
function configAccountOrigin(machineName: string): string {
  const origin = expectedAccountServerOrigin();
  if (origin) return origin;
  throw new Error(
    `Cannot compare the licences on ${machineName} with this config's account server: "${getSubscriptionServerUrl()}" is not a URL`
  );
}

/** The origin of a licence's `renewalUrl`; one that does not parse stays as itself, so it is never the config's origin. */
function renewalOrigin(renewalUrl: string): string {
  try {
    return new URL(renewalUrl).origin;
  } catch {
    return renewalUrl;
  }
}

/**
 * The scanned repos whose installed licence names an account-server origin other than the config's, from the
 * `currentRenewalUrl` the `license-scan` entry carries. The server compares dates only, so a fresh licence from another
 * origin (the config's account server moved) is never reissued unless the request drops its current dates. A licence
 * without a `renewalUrl` names no origin and is not counted.
 */
export function reposWithForeignLicenseOrigin(
  remoteRepos: RemoteRepoLicenseScanEntry[],
  machineName: string
): Set<string> {
  const expected = configAccountOrigin(machineName);
  const guids = new Set<string>();
  for (const repo of remoteRepos) {
    if (repo.currentRenewalUrl && renewalOrigin(repo.currentRenewalUrl) !== expected) {
      guids.add(repo.repositoryGuid);
    }
  }
  return guids;
}

/** The prefix of a FREE licence's subscription id (private/account free-license.service.ts). */
const FREE_SUBSCRIPTION_ID_PREFIX = 'free:';

/** A production account server: one of the regions in regions.json. Bench and every other server are not. */
function isProductionOrigin(origin: string): boolean {
  return BAKED_IN_REGIONS.some((region) => `https://${region.domain}` === origin);
}

/**
 * The foreign-origin repos whose licence is a FREE one that moves without `--adopt-origin`: an unregistered machine
 * takes FREE licences from the default region, and the user who later subscribes in another region must not be left
 * with them guarded. Only production to production counts: a bench-issued FREE licence, or a config that is not a
 * production region, keeps the guard, since bench shares the production signing key. A paid licence is never in it.
 * The scan entry's `currentSubscriptionId` decides FREE; an entry without it is not FREE.
 */
export function freeLicensesToAdopt(
  remoteRepos: RemoteRepoLicenseScanEntry[],
  foreignOrigin: Set<string>,
  machineName: string
): Set<string> {
  const guids = new Set<string>();
  if (!isProductionOrigin(configAccountOrigin(machineName))) return guids;
  for (const repo of remoteRepos) {
    if (
      foreignOrigin.has(repo.repositoryGuid) &&
      repo.currentSubscriptionId?.startsWith(FREE_SUBSCRIPTION_ID_PREFIX) &&
      repo.currentRenewalUrl &&
      isProductionOrigin(renewalOrigin(repo.currentRenewalUrl))
    ) {
      guids.add(repo.repositoryGuid);
    }
  }
  return guids;
}

// `identity_mismatch` joins `machine_mismatch`: after `backup snapshot --accept-identity-change` the image's UUID is new, an unexpired licence answers `unchanged` to a plain refresh, and the repository stays unmountable until the refresh window opens. Only a forced GUID is reissued.
// machine_mismatch force-reissues (the documented remedy the guidance points users at). invalid_signature no longer triggers a reissue: with the per-signer license layout a foreign-universe file is simply never selected, so a genuine invalid_signature means the machine's OWN key can't validate its own file, that must fail fast, not loop reissuing (matches subscription-licensing.md).
// A foreign-origin licence joins only when `adopted` names it (all of them under `adoptOrigin`, else just the FREE ones freeLicensesToAdopt moves): its dates are fresh, so the server would answer `unchanged` unless the request drops them.
function forceReissueSet(
  licenseStatuses: { repositoryGuid: string; status: string }[],
  foreignOrigin: Set<string>,
  adopted: Set<string>
): Set<string> {
  const guids = new Set(
    licenseStatuses
      .filter((s) => s.status === 'machine_mismatch' || s.status === 'identity_mismatch')
      .map((s) => s.repositoryGuid)
  );
  // A foreign-origin licence that is not adopted is skipped whole, so it is no pending reissue either, whatever its status.
  for (const guid of foreignOrigin) {
    if (adopted.has(guid)) guids.add(guid);
    else guids.delete(guid);
  }
  return guids;
}

/**
 * Leave every foreign-origin licence out of the batch, warning once per repository with both servers named.
 *
 * Bench and production sign with one key, so renet accepts either server's blob and keeps one chain per
 * (key, subscription, repo): a bench blob written over a production one carries a lower sequence and renet then refuses
 * the repository as `sequence_regression` (2026-11-11: eleven hostinger licences, mail backups refused for two hours,
 * written by the background refresh of a health read under `--config eu-bench`). Moving licences between account
 * servers is `subscription refresh --adopt-origin`, never a side effect.
 */
function skipForeignOrigin<T extends RemoteRepoLicenseScanEntry>(
  machineName: string,
  repos: T[],
  foreignOrigin: Set<string>,
  nameByGuid: Map<string, string>
): { kept: T[]; skipped: { repositoryGuid: string; error: string }[] } {
  const configOrigin = configAccountOrigin(machineName);
  const skipped: { repositoryGuid: string; error: string }[] = [];
  const warned = new Set<string>();
  const kept = repos.filter((repo) => {
    if (!foreignOrigin.has(repo.repositoryGuid)) return true;
    // Entry by entry: a same-origin copy of a guid (another datastore) is kept beside its foreign sibling.
    if (!repo.currentRenewalUrl || renewalOrigin(repo.currentRenewalUrl) === configOrigin) {
      return true;
    }
    if (warned.has(repo.repositoryGuid)) return false;
    warned.add(repo.repositoryGuid);
    const vars = {
      repo: nameByGuid.get(repo.repositoryGuid) ?? repo.repositoryGuid,
      machine: machineName,
      licenseOrigin: renewalOrigin(repo.currentRenewalUrl ?? ''),
      configOrigin,
    };
    outputService.warn(t('warnings.licenseForeignOriginSkipped', vars));
    skipped.push({
      repositoryGuid: repo.repositoryGuid,
      error: t('errors.license.foreignOriginSkipped', vars),
    });
    return false;
  });
  return { kept, skipped };
}

/**
 * The repos a batch sends: the scanned ones the config tracks, minus every foreign-origin licence unless `adoptOrigin`,
 * and the GUIDs whose current dates the request drops.
 */
function selectBatchRepos(
  machineName: string,
  remoteRepos: RemoteRepoLicenseScanEntry[],
  localRepos: { name: string; config: { repositoryGuid: string; grandGuid?: string } }[],
  licenseStatuses: { repositoryGuid: string; status: string }[],
  adoptOrigin: boolean
): {
  knownRemoteRepos: ReturnType<typeof resolveKnownRemoteRepos>['knownRemoteRepos'];
  unknownRepoFailures: { repositoryGuid: string; error: string }[];
  foreignSkips: { repositoryGuid: string; error: string }[];
  forceReissueGuids: Set<string>;
} {
  const foreignOrigin = reposWithForeignLicenseOrigin(remoteRepos, machineName);
  const freeAdopted = freeLicensesToAdopt(remoteRepos, foreignOrigin, machineName);
  const forceReissueGuids = forceReissueSet(
    licenseStatuses,
    foreignOrigin,
    adoptOrigin ? foreignOrigin : freeAdopted
  );
  const repoByGuid = new Map(
    localRepos.map((entry) => [entry.config.repositoryGuid, { grandGuid: entry.config.grandGuid }])
  );
  const { knownRemoteRepos: resolvedRepos, unknownRepoFailures } = resolveKnownRemoteRepos(
    remoteRepos,
    repoByGuid
  );
  if (adoptOrigin) {
    return {
      knownRemoteRepos: resolvedRepos,
      unknownRepoFailures,
      foreignSkips: [],
      forceReissueGuids,
    };
  }
  const { kept, skipped } = skipForeignOrigin(
    machineName,
    resolvedRepos,
    new Set([...foreignOrigin].filter((guid) => !freeAdopted.has(guid))),
    new Map(localRepos.map((entry) => [entry.config.repositoryGuid, entry.name]))
  );
  return { knownRemoteRepos: kept, unknownRepoFailures, foreignSkips: skipped, forceReissueGuids };
}

/** The answer of a batch that sends nothing: no tracked repo, or every tracked repo licensed by another server. */
function emptyBatchResult(
  scanned: number,
  unknownRepoFailures: { repositoryGuid: string; error: string }[],
  foreignSkips: { repositoryGuid: string; error: string }[],
  invalidSignatureDetected: number,
  requiredGuid: string | undefined
): RepoBatchRefreshResult {
  const failures = [...unknownRepoFailures, ...foreignSkips];
  const recoveryFailureMode: RepoBatchRecoveryFailureMode =
    foreignSkips.length === 0 && scanned > 0 ? 'no_known_repos' : 'server_rejected_all';
  return {
    scanned,
    issued: 0,
    refreshed: 0,
    unchanged: 0,
    failed: failures.length,
    valid: 0,
    invalidSignatureDetected,
    failures,
    recoveryFailureMode,
    serverErrorSample: foreignSkipSample(failures, foreignSkips, requiredGuid),
  };
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
  remoteRenetPath: string | undefined,
  requiredGuid: string | undefined,
  scanned: RemoteRepoLicenseScanEntry[] | undefined,
  adoptOrigin: boolean
): Promise<RepoBatchRefreshResult> {
  const datastore = machine.datastore ?? DEFAULT_DATASTORE;
  const [machineId, clientMachineId, remoteRepos, localRepos, licenseStatuses] = await Promise.all([
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
  ]);

  const { knownRemoteRepos, unknownRepoFailures, foreignSkips, forceReissueGuids } =
    selectBatchRepos(machineName, remoteRepos, localRepos, licenseStatuses, adoptOrigin);

  if (knownRemoteRepos.length === 0) {
    return emptyBatchResult(
      remoteRepos.length,
      unknownRepoFailures,
      foreignSkips,
      forceReissueGuids.size,
      requiredGuid
    );
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

  const failures: { repositoryGuid: string; error: string }[] = [
    ...unknownRepoFailures,
    ...foreignSkips,
  ];
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
