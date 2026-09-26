import { TELEMETRY_SUBSCRIPTION_SOURCES } from '@rediacc/shared/telemetry';
import type { SFTPClient } from '../../remote/sftp/index.js';
import type { MachineConfig } from '../../types/index.js';
import { sftpConfigForMachine, withSharedOrPooledSftp } from '../machine/machine-connection.js';
import { telemetryService } from '../telemetry/telemetry.js';
import { accountServerFetch } from './account-client.js';
import {
  clusterIdFor,
  DEFAULT_DATASTORE,
  measureRepoSizeGb,
  readLocalMachineId,
  readRemoteMachineId,
  scanRemoteLicenseStatuses,
  scanRemoteRepoLicenses,
  writeRepoLicense,
} from './license-machine.js';
import type {
  MachineActivationStatus,
  RuntimeRepoLicenseStatus,
  SubscriptionLicenseReport,
} from './license-types.js';
import { getSubscriptionTokenState } from './subscription-auth.js';

export { refreshRepoLicensesBatch } from './license-batch.js';
export { isDatastoreScopedId } from './license-machine.js';
export type {
  MachineActivationStatus,
  RepoBatchRecoveryFailureMode,
  RepoBatchRefreshResult,
  RuntimeRepoLicenseStatus,
  SubscriptionLicenseReport,
} from './license-types.js';

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

export function readMachineActivationStatus(
  machine: MachineConfig,
  sshPrivateKey: string,
  remoteRenetPath?: string,
  sharedSftp?: SFTPClient
): Promise<MachineActivationStatus | null> {
  const tokenState = getSubscriptionTokenState();
  if (tokenState.kind !== 'ready') {
    return Promise.resolve(null);
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

export function readRuntimeRepoLicenseStatuses(
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

export function issueRepoLicense(
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
  if (tokenState.kind !== 'ready') return Promise.resolve(false);

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
        // The mount the machine itself reports for this repo. Better than anything the client can derive, and it is the datastore the size probe below must measure when the scan could not price the repo.
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

export function refreshRepoLicenseIdentity(
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
     * the scan cannot answer at all, an older renet, or a datastore it failed
     * to read, where dropping to no identity would write the reissue to the
     * unscoped path that renet does not read for a datastore-resident repo.
     */
    datastoreId?: string;
    /**
     * Mount of the datastore this repo's image lives on, as the CALLER recorded
     * it (`repo.placement`). A fallback, on the same terms as `datastoreId`
     * above: the scan reports the machine's own `datastorePath` and that wins.
     *
     * It matters when the scan cannot price the repo, no licence installed
     * yet, or a scan that failed, and the size probe has to measure the image
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
  if (tokenState.kind !== 'ready') return Promise.resolve(false);

  return withSharedOrPooledSftp(
    sharedSftp,
    sftpConfigForMachine(machine, sshPrivateKey),
    async (sftp) => {
      // The PRIMARY datastore for the scan below, not the repo's home: the scan command passes --all-datastores, so it walks every attached named datastore too and reports each repo tagged with its own datastorePath. That is why the scan half of this function was never the bug.
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
          // Most authoritative first: the machine's own answer, then the placement the caller recorded, then the machine default, which is right only for a repo that really is on the default datastore.
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
