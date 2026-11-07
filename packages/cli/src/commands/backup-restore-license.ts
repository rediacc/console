import { DEFAULTS } from '@rediacc/shared/config';
import type { Placement } from '@rediacc/shared/config-schema';
import { t } from '../i18n/index.js';
import { issueFreeRepoLicense, resolveLicenseAuthority } from '../services/account/free-license.js';
import { issueRepoLicense } from '../services/account/license.js';
import { DEFAULT_DATASTORE, measureRepoSizeGb } from '../services/account/license-machine.js';
import { authorizeSubscriptionViaDeviceCode } from '../services/account/subscription-device-auth.js';
import { namedDatastoreMount } from '../services/cluster/cluster-target.js';
import { outputService } from '../services/core/output.js';
import {
  resolveRestoreLicenseContext,
  restoreLicenseAlreadyInstalled,
} from '../services/executor/repo-license-context.js';
import { machineConnections } from '../services/machine/machine-connection.js';

/**
 * Install the licence the pull's destination needs, BEFORE `backup_pull` runs.
 *
 * Every restore mints a fresh GUID (restoredIdentity), and `backup_pull` is
 * full-tier: renet validates the licence for the DESTINATION GUID, which no
 * machine holds yet. The executor's recovery cannot answer that refusal: for
 * a non-provisioning verb it runs the image-scanning batch refresh, and the
 * destination has no image until the pull lands it. So the licence is issued
 * here, for the minted GUID on the target machine, the way `repo create`'s
 * pre-flight issues one for a repo that does not exist yet: no identity proofs
 * (renet's later scans add them), and the same context and skip probe the
 * `--at` route's pre-flight uses for the same restored record.
 *
 * The requested size is the source image's, measured on the source machine:
 * that is what will arrive. A cluster source names no machine to measure on,
 * so it requests the floor; renet still enforces the licence's limit against
 * the staged image before committing it.
 */
export async function ensureRestorePullLicense(args: {
  targetName: string;
  targetMachine: string;
  source: { machine: string; guid: string; placement?: Placement } | undefined;
}): Promise<void> {
  const renet = DEFAULTS.CONTEXT.RENET_BINARY;
  const lease = await machineConnections.acquire(args.targetMachine);
  try {
    const base = await resolveRestoreLicenseContext(
      args.targetMachine,
      { repository: args.targetName },
      lease.sftp,
      { remoteRenetPath: renet, required: true }
    );
    if (!base) throw new Error(t('errors.subscription.activationFailed'));
    if (await restoreLicenseAlreadyInstalled(base, lease.machine, renet, lease.sftp)) return;

    const requestedSizeGb = args.source ? await sourceImageSizeGb(args.source) : 1;
    const params = { ...base, requestedSizeGb };
    const authority = await resolveLicenseAuthority(() =>
      authorizeSubscriptionViaDeviceCode(undefined, {
        interactive: process.stdin.isTTY && process.stdout.isTTY,
        announceIntro: true,
      })
    );
    if (authority === 'free') {
      await issueFreeRepoLicense(
        args.targetMachine,
        lease.machine,
        lease.sshPrivateKey,
        params,
        renet,
        lease.sftp
      );
      return;
    }
    const issued = await issueRepoLicense(
      args.targetMachine,
      lease.machine,
      lease.sshPrivateKey,
      params,
      renet,
      lease.sftp
    );
    if (!issued) {
      throw new Error(t('errors.subscription.activationFailed'));
    }
  } finally {
    lease.release();
  }
}

/** The source image's size in GB on its machine (the floor, with a warning, when it cannot be measured). */
async function sourceImageSizeGb(source: {
  machine: string;
  guid: string;
  placement?: Placement;
}): Promise<number> {
  let lease: Awaited<ReturnType<typeof machineConnections.acquire>>;
  try {
    lease = await machineConnections.acquire(source.machine);
  } catch {
    outputService.warn(
      `Could not reach ${source.machine} to size the source image; requesting the 1 GB floor.`
    );
    return 1;
  }
  try {
    const placed =
      source.placement && 'datastore' in source.placement
        ? namedDatastoreMount(source.placement.datastore)
        : undefined;
    return await measureRepoSizeGb(lease.sftp, source.guid, [
      placed,
      lease.machine.datastore ?? DEFAULT_DATASTORE,
    ]);
  } catch {
    outputService.warn(
      `Could not measure the source image on ${source.machine}; requesting the 1 GB floor.`
    );
    return 1;
  } finally {
    lease.release();
  }
}
