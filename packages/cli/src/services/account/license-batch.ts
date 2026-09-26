/**
 * `refreshRepoLicensesBatch`: scan every repo on a machine, renew or issue
 * their licenses in one account-server call, and install the returned blobs.
 * Re-exported from `license.ts`.
 */

import { DEFAULTS } from '@rediacc/shared/config';
import type { SFTPClient } from '../../remote/sftp/index.js';
import type { MachineConfig } from '../../types/index.js';
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
import { getSubscriptionTokenState } from './subscription-auth.js';

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

export function refreshRepoLicensesBatch(
  machine: MachineConfig,
  sshPrivateKey: string,
  remoteRenetPath?: string,
  sharedSftp?: SFTPClient
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

  // Only machine_mismatch force-reissues (the documented remedy the guidance points users at). invalid_signature no longer triggers a reissue: with the per-signer license layout a foreign-universe file is simply never selected, so a genuine invalid_signature means the machine's OWN key can't validate its own file, that must fail fast, not loop reissuing (matches subscription-licensing.md).
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

  // Each blob goes back to the population its repo was scanned from. Two repos in a batch can legitimately carry the SAME guid on one machine (a same-node datastore fork does not remint guids), which is exactly why the store is scoped by datastore and why this map is keyed the way the server keys its results.
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
