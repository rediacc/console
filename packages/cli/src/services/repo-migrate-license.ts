/**
 * The repo licence `repo migrate` installs on its TARGET before starting the repo there.
 *
 * A licence is bound to one machine (its signed `machineId`), and renet enforces licensing on every
 * `repository_up`. The migrate's push lands the image on the target, but nothing lands a licence for
 * it: the source's blob is the source's, so the target's licence store holds nothing for the GUID and
 * `repository_up` exits 10 `LICENSE_REQUIRED: missing: no license data` (e2e suite 23, test 3). The
 * executor's retry cannot be relied on to answer it: for an operate-tier verb it runs the machine-wide
 * batch refresh (or, with no login, a renewal of whatever blobs are already installed), and either
 * counts as a recovery as soon as ANY repo on the machine is licensed, whether or not it is this one.
 *
 * So the migrate issues for THIS GUID on THIS machine, through the same issuance the executor's
 * provisioning pre-flight uses: a ready login issues through the account (with the identity proofs
 * renet's own scan reports for the landed image), and no login takes the FREE licence on the same terms
 * `repo create` does (an agent or `--yes` takes it, a terminal is offered a login or a free licence).
 */

import { DEFAULTS } from '@rediacc/shared/config';
import { t } from '../i18n/index.js';
import {
  issueFreeRepoLicense,
  type LicenseAuthority,
  resolveLicenseAuthority,
} from './account/free-license.js';
import { refreshRepoLicenseIdentity } from './account/license.js';
import { DEFAULT_DATASTORE, scanRemoteRepoLicenses } from './account/license-machine.js';
import type { RemoteRepoLicenseScanEntry } from './account/license-types.js';
import { authorizeSubscriptionViaDeviceCode } from './account/subscription-device-auth.js';
import { configService } from './config/config-resources.js';
import { isRenetFlagUnsupported } from './executor/job-client.js';
import { restoreLicenseAlreadyInstalled } from './executor/repo-license-context.js';
import { type MachineConnectionLease, machineConnections } from './machine/machine-connection.js';

/** The device-code login the licence paths run when a terminal operator picks "log in". */
async function loginViaDeviceCode(): Promise<void> {
  await authorizeSubscriptionViaDeviceCode(undefined, {
    interactive: process.stdin.isTTY && process.stdout.isTTY,
    announceIntro: true,
  });
}

/**
 * Whether a failed `repository license-scan` means the target's renet predates it: cobra's
 * `unknown command "license-scan"`, or an `unknown flag` (`--all-datastores`, `--output`). Cobra
 * rejects both while parsing, so nothing ran and nothing about the image is known either way.
 */
function isScanUnsupported(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error);
  return /unknown command "license-scan"/.test(message) || isRenetFlagUnsupported(message);
}

/**
 * renet's scan entry for the landed image, or undefined when the target's renet is too old to scan.
 * Any other failure (a dropped SSH channel, an SFTP error, unparseable output) propagates: issuing
 * with the default datastore and no size would licence the wrong scope, so the migrate fails before
 * `repository_up` instead.
 */
async function scanLandedImage(
  sftp: Parameters<typeof scanRemoteRepoLicenses>[0],
  datastore: string,
  repositoryGuid: string
): Promise<RemoteRepoLicenseScanEntry | undefined> {
  try {
    const scanned = await scanRemoteRepoLicenses(sftp, datastore);
    return scanned.find((entry) => entry.repositoryGuid === repositoryGuid);
  } catch (error) {
    if (isScanUnsupported(error)) return undefined;
    throw error;
  }
}

/** What identifies the licence: the GUID, its lineage, and where on the target the image landed. */
interface TargetLicenseScope {
  repositoryGuid: string;
  grandGuid: string;
  kind: 'grand' | 'fork';
  datastoreMount: string;
  datastoreId?: string;
  requestedSizeGb?: number;
}

/** Issue through the account (`token`, with renet's identity proofs) or take the FREE licence (`free`). */
async function issueTargetLicense(
  authority: LicenseAuthority,
  lease: MachineConnectionLease,
  scope: TargetLicenseScope
): Promise<void> {
  const { machine, sshPrivateKey, sftp } = lease;
  const { repositoryGuid, grandGuid, kind, datastoreId, requestedSizeGb } = scope;
  if (authority === 'free') {
    await issueFreeRepoLicense(
      machine,
      sshPrivateKey,
      { repositoryGuid, grandGuid, kind, requestedSizeGb, datastoreId },
      undefined,
      sftp
    );
    return;
  }
  // The image exists on the target, so this is a reissue for an existing repo: refreshRepoLicenseIdentity reads size, identity proofs and datastore identity from renet's own scan and issues through `/licenses/activate-repo`.
  const issued = await refreshRepoLicenseIdentity(
    machine,
    sshPrivateKey,
    { repositoryGuid, grandGuid, kind, datastoreId, datastoreMount: scope.datastoreMount },
    undefined,
    sftp
  );
  if (!issued) {
    throw new Error(t('errors.subscription.activationFailed'));
  }
}

/**
 * Install a licence for `repoKey`'s GUID on machine `to`, unless one valid for this machine is already
 * there. Throws when issuance fails, naming why (a slot limit, a FREE refusal), which says more than
 * the `LICENSE_REQUIRED` the `repository_up` would otherwise end with.
 */
export async function ensureTargetRepoLicense(repoKey: string, to: string): Promise<void> {
  const repo = await configService.getRepository(repoKey);
  const repositoryGuid = repo?.repositoryGuid;
  if (!repositoryGuid) return;
  const grandGuid = repo.grandGuid ?? repositoryGuid;

  const lease = await machineConnections.acquire(to);
  try {
    const datastore = lease.machine.datastore ?? DEFAULT_DATASTORE;
    const landed = await scanLandedImage(lease.sftp, datastore, repositoryGuid);
    const scope: TargetLicenseScope = {
      repositoryGuid,
      grandGuid,
      kind: grandGuid === repositoryGuid ? 'grand' : 'fork',
      datastoreMount: landed?.datastorePath ?? datastore,
      datastoreId: landed?.datastoreId,
      requestedSizeGb: landed?.requestedSizeGb,
    };
    // Scoped to this GUID in the datastore the image landed in, and `runtimeValid` on THIS machine: a blob that came from anywhere else does not count.
    if (
      await restoreLicenseAlreadyInstalled(
        scope,
        lease.machine,
        DEFAULTS.CONTEXT.RENET_BINARY,
        lease.sftp
      )
    ) {
      return;
    }
    await issueTargetLicense(await resolveLicenseAuthority(loginViaDeviceCode), lease, scope);
  } finally {
    lease.release();
  }
}
