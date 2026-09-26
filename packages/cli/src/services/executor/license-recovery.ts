/**
 * The executor's repo-license paths: the pre-flight issuance for provisioning
 * and restore verbs, recovery when renet refuses a run for want of a license,
 * the opportunistic batch refresh, and the post-create identity refresh.
 */

import { t } from '../../i18n/index.js';
import type { SFTPClient } from '../../remote/sftp/index.js';
import { isAgentEnvironment } from '../../utils/agent-guard.js';
import { ValidationError } from '../../utils/errors.js';
import {
  issueRepoLicense,
  type RepoBatchRecoveryFailureMode,
  refreshRepoLicenseIdentity,
  refreshRepoLicensesBatch,
} from '../account/license.js';
import {
  isMachineSlotLimitError,
  machineSlotLimitMessage,
  readMachineSlotStatus,
} from '../account/license-preflight.js';
import { isRefreshDue, markRefreshAttempted } from '../account/license-refresh-state.js';
import { getSubscriptionTokenState } from '../account/subscription-auth.js';
import { authorizeSubscriptionViaDeviceCode } from '../account/subscription-device-auth.js';
import type { configService } from '../config/config-resources.js';
import { reportStateWriteRefused } from '../config/state-write-failure.js';
import { outputService } from '../core/output.js';
import { machineConnections } from '../machine/machine-connection.js';
import {
  isRepoProvisioningFunction,
  RENET_LICENSE_REQUIRED_EXIT_CODE,
  type RenetLicenseFailure,
} from '../renet/renet-license-contract.js';
import { telemetryService } from '../telemetry/telemetry.js';
import {
  type RepoLicenseContext,
  resolveRepoLicenseContext,
  resolveRestoreLicenseContext,
  resolveRestoreSizeGb,
  restoreLicenseAlreadyInstalled,
} from './repo-license-context.js';
import type { ExecuteOptions, ExecuteResult } from './types.js';

/**
 * Whether a failed run is the kind that license recovery can retry: renet
 * refused for want of a repo license, and the caller has not opted out of
 * machine activation.
 */
/*
 * Exit 10 is NO LONGER UNIQUE to the license path. renet now re-raises a child
 * process's own exit code verbatim (cmd/renet/execute_command.go), so a
 * `repo exec ... -- sh -c 'exit 10'` reports 10 too. That makes the structured
 * payload parse at the call site LOAD-BEARING rather than merely defensive:
 * this predicate answers "could this be a license refusal", and only a parsed
 * LICENSE_REQUIRED payload confirms it. Do not act on this function alone.
 */
export function needsLicenseRecovery(result: ExecuteResult): boolean {
  return (
    !result.success &&
    result.exitCode === RENET_LICENSE_REQUIRED_EXIT_CODE &&
    process.env.REDIACC_SKIP_MACHINE_ACTIVATION !== '1'
  );
}

type LicenseIssuanceOutcome =
  | { kind: 'success' }
  | { kind: 'failure'; failureMode: RepoBatchRecoveryFailureMode; serverErrorSample?: string };

export async function resolveLicenseFailure(
  result: ExecuteResult,
  failure: RenetLicenseFailure,
  options: ExecuteOptions,
  machine: Awaited<ReturnType<typeof configService.getLocalMachine>>,
  sshPrivateKey: string,
  remoteRenetPath: string,
  sftp: SFTPClient,
  startTime: number
): Promise<ExecuteResult | null> {
  const guidance = resolveLicenseRecoveryGuidance(failure, options.machineName);
  if (guidance.failFastMessage) {
    return buildRecoveryFailureResult(
      result,
      guidance,
      guidance.failFastMessage,
      failure.reason,
      startTime
    );
  }
  try {
    await maybeOnboardSubscription(failure.reason);
  } catch (error) {
    return buildRecoveryFailureResult(
      result,
      guidance,
      error instanceof Error ? error.message : String(error),
      failure.reason,
      startTime
    );
  }
  const outcome = await maybeIssueLicense(options, machine, sshPrivateKey, remoteRenetPath, sftp);
  if (outcome.kind === 'success') {
    return null;
  }
  telemetryService.trackEvent('license_recovery_failed', {
    licenseRecoveryFailureMode: String(outcome.failureMode),
  });
  const recoveryGuidance = resolveLicenseRecoveryGuidance(failure, options.machineName, outcome);
  const recoveryFailedMsg = recoveryGuidance.recoveryFailedMessage;
  if (!recoveryFailedMsg) {
    return result;
  }
  return buildRecoveryFailureResult(
    result,
    recoveryGuidance,
    recoveryFailedMsg,
    failure.reason,
    startTime
  );
}

function buildRecoveryFailureResult(
  result: ExecuteResult,
  guidance: ReturnType<typeof resolveLicenseRecoveryGuidance>,
  error: string,
  failureReason: string,
  startTime: number
): ExecuteResult {
  return {
    ...result,
    errorCode: guidance.errorCode,
    error,
    errorGuidance: guidance.guidance,
    licenseFailureReason: failureReason,
    durationMs: Date.now() - startTime,
  };
}

async function maybeIssueLicense(
  options: ExecuteOptions,
  machine: Awaited<ReturnType<typeof configService.getLocalMachine>>,
  sshPrivateKey: string,
  remoteRenetPath: string,
  sftp: SFTPClient
): Promise<LicenseIssuanceOutcome> {
  // NOTE: recovery is deliberately NOT gated on any "is this function licensed" predicate. There used to be one (isLicensedRenetFunction, with a repository_up/down/delete deny-list); it is deleted, because it was a hand-maintained second source of truth that had already drifted from renet's tier map, and nothing consumed it but this comment.
  //
  // The reasoning it encoded still holds and is why nothing like it belongs here: such a deny-list governs PRE-FLIGHT issuance, since operate-tier ops do not issue a license before running. But this method runs during RECOVERY, after renet has already reported
  // LICENSE_REQUIRED (reason=missing) for the repo on the target machine.
  // The repo image exists on disk there, so refreshRepoLicensesBatch can scan it and issue. Skipping recovery for deny-listed functions is the root cause of rediacc/console#482: `repo push --up` to a fresh machine fails because the license was issued for the source, not the destination, and the destination's repository_up recovery never tried to issue.

  // For provisioning verbs (create-tier, per renet's tier map), re-issue the pre-provisioning repo license
  if (isRepoProvisioningFunction(options.functionName)) {
    try {
      await ensureRepoLicenseForProvisioning(
        options,
        machine,
        sshPrivateKey,
        remoteRenetPath,
        sftp
      );
      return { kind: 'success' };
    } catch (err) {
      telemetryService.trackError(err, { operation: 'executor.repo_license_recovery' });
      return {
        kind: 'failure',
        failureMode: 'server_rejected_all',
        serverErrorSample: err instanceof Error ? err.message : String(err),
      };
    }
  }
  // For all other licensed operations, batch refresh existing repo licenses
  const batchResult = await refreshRepoLicensesBatch(
    machine,
    sshPrivateKey,
    remoteRenetPath,
    sftp
  ).catch((err: unknown) => {
    telemetryService.trackError(err, { operation: 'executor.batch_refresh' });
    return {
      kind: 'failure' as const,
      failureMode: 'server_rejected_all' as const,
      serverErrorSample: String(err),
    };
  });
  if ('kind' in batchResult) {
    return batchResult;
  }
  if (batchResult.recoveryFailureMode === null) return { kind: 'success' };
  return {
    kind: 'failure',
    failureMode: batchResult.recoveryFailureMode,
    serverErrorSample: batchResult.serverErrorSample,
  };
}

/**
 * Opportunistically refresh repo licences on a machine we are already talking
 * to.
 *
 * Gated on a per-machine cooldown, NOT on whether the renet binary happened to
 * change. It used to run only `if (renetUploaded)`, which coupled licence
 * maintenance to binary churn: on a stable machine renet does not change for
 * weeks, so a daily-active operator got no refresh at all and licences drifted
 * toward expiry unattended. Binary version and licence age are unrelated.
 *
 * Best-effort throughout. A machine can never refresh its own licences (renet
 * only verifies them; issuance is CLI-side), so this is the only proactive
 * path, but it can only run where the operator's subscription token lives,
 * and it stays silent when there is none.
 */
export async function maybeRefreshRepoLicenses(
  machine: Awaited<ReturnType<typeof configService.getLocalMachine>>,
  machineName: string,
  sshPrivateKey: string,
  remoteRenetPath: string,
  sftp: SFTPClient
): Promise<void> {
  // The ENTIRE body is best-effort. This runs on every machine-touching command as a side-effect of doing something else, so nothing in here, token lookup, local state IO, the network call, may surface as a failure of the command the operator actually asked for.
  try {
    if (getSubscriptionTokenState().kind !== 'ready') return;

    if (!(await isRefreshDue(machineName))) return;
    // Marked before the attempt, not after: a refresh that throws must still consume its cooldown slot, or an unreachable machine would be retried on every single command.
    await markRefreshAttempted(machineName);

    const result = await refreshRepoLicensesBatch(machine, sshPrivateKey, remoteRenetPath, sftp);
    if (result.invalidSignatureDetected > 0) {
      const refreshed = result.issued + result.refreshed;
      if (refreshed > 0) {
        outputService.info(t('warnings.licenseSignatureRefreshed', { count: refreshed }));
      } else {
        outputService.warn(
          t('warnings.licenseSignatureRefreshFailed', {
            count: result.invalidSignatureDetected,
          })
        );
      }
    }
  } catch (error) {
    // Non-blocking: license check failure should not prevent command execution. The one failure
    // reported is a remote config refusing the cooldown write while its store is unreachable.
    reportStateWriteRefused(error);
  }
}

async function maybeOnboardSubscription(reason: string): Promise<boolean> {
  if (reason !== 'missing') {
    return false;
  }
  const tokenState = getSubscriptionTokenState();
  if (tokenState.kind === 'ready') {
    return false;
  }
  if (isAgentEnvironment()) {
    throw new ValidationError(t('errors.subscription.tokenRequired'));
  }
  await authorizeSubscriptionViaDeviceCode(undefined, {
    interactive: process.stdin.isTTY && process.stdout.isTTY,
    announceIntro: true,
  });
  return true;
}

/**
 * Pre-flight for the repo-provisioning verbs (isRepoProvisioningFunction,
 * i.e. create-tier in renet's map: repository_create / repository_fork):
 * Ensure subscription token exists (trigger device-code auth if needed)
 * and pre-issue a repo license (without identity proofs since the repo
 * doesn't exist yet). The server enforces machine slot limits during
 * issuance. After creation, maybeRefreshRepoIdentity re-issues the
 * license with identity proofs.
 */
export async function ensureRepoLicenseForProvisioning(
  options: ExecuteOptions,
  machine: Awaited<ReturnType<typeof configService.getLocalMachine>>,
  sshPrivateKey: string,
  remoteRenetPath: string,
  sftp?: SFTPClient
): Promise<void> {
  // Allow bypassing activation for nolicense/CI builds where no subscription server exists
  if (process.env.REDIACC_SKIP_MACHINE_ACTIVATION === '1') {
    return;
  }

  const tokenState = getSubscriptionTokenState();
  if (tokenState.kind !== 'ready') {
    if (isAgentEnvironment()) {
      throw new ValidationError(t('errors.subscription.tokenRequired'));
    }
    await authorizeSubscriptionViaDeviceCode(undefined, {
      interactive: process.stdin.isTTY && process.stdout.isTTY,
      announceIntro: true,
    });
  }

  const repoLicenseCtx = await resolveRepoLicenseContext(
    options.functionName,
    options.machineName,
    options.params ?? {},
    sftp!,
    { remoteRenetPath, required: true }
  );
  if (!repoLicenseCtx) {
    throw new Error(t('errors.subscription.activationFailed'));
  }

  const issued = await issueOrExplainSlotLimit(
    machine,
    sshPrivateKey,
    repoLicenseCtx,
    remoteRenetPath,
    sftp
  );
  if (!issued) {
    throw new Error(t('errors.subscription.activationFailed'));
  }
}

/**
 * Pre-flight for `backup_restore` (isRestoreLicenseFunction): install the
 * repo licence the restore needs as its chunk-store credential, on a machine
 * that may hold none at all.
 *
 * This is the disaster-recovery case, and it is the whole point: the target
 * of a real restore is a fresh replacement box. renet's `resolveRestoreLicense`
 * accepts ANY installed blob on the machine, so the pre-existing remedy was
 * to create a throwaway carrier repo first, which no operator in a DR
 * situation would know, and which is precisely what this removes. The licence
 * is issued silently, as one timed step, exactly as provisioning renders one.
 *
 * Two things it must NOT do, both load-bearing:
 *
 * - It must not route through the repo-provisioning path. `backup_restore` is
 *   TierNone in renet's map on purpose, so an expired licence can never lock a
 *   customer out of their own backed-up data. See `isRestoreLicenseFunction`.
 * - It must not issue for an arbitrary guid. The licence is minted for the
 *   SOURCE repo's guid, which the restored record already carries, so the
 *   very next `--up` (operate-tier, resolved guid-specifically with no
 *   any-repo fallback) finds it. A carrier licence would satisfy the restore
 *   and then fail the deploy: "restored, and the repo will not start".
 *
 * Structurally parallel to `ensureRepoLicenseForProvisioning`, and a COPY of
 * its shared parts rather than a shared helper. That is deliberate: the
 * provisioning version runs CONCURRENTLY with machine verification and any
 * factored-out helper would have to stay correct for both callers, which is a
 * standing tax for two short bodies that are free to diverge.
 */
export async function ensureRepoLicenseForRestore(
  options: ExecuteOptions,
  machine: Awaited<ReturnType<typeof configService.getLocalMachine>>,
  sshPrivateKey: string,
  remoteRenetPath: string,
  sftp: SFTPClient
): Promise<void> {
  // Allow bypassing activation for nolicense/CI builds where no subscription server exists
  if (process.env.REDIACC_SKIP_MACHINE_ACTIVATION === '1') {
    return;
  }

  const tokenState = getSubscriptionTokenState();
  if (tokenState.kind !== 'ready') {
    if (isAgentEnvironment()) {
      throw new ValidationError(t('errors.subscription.tokenRequired'));
    }
    await authorizeSubscriptionViaDeviceCode(undefined, {
      interactive: process.stdin.isTTY && process.stdout.isTTY,
      announceIntro: true,
    });
  }

  const params = options.params ?? {};
  const base = await resolveRestoreLicenseContext(options.machineName, params, sftp, {
    remoteRenetPath,
    required: true,
  });
  if (!base) {
    throw new Error(t('errors.subscription.activationFailed'));
  }

  if (await restoreLicenseAlreadyInstalled(base, machine, sshPrivateKey, remoteRenetPath, sftp)) {
    return;
  }

  const issued = await issueOrExplainSlotLimit(
    machine,
    sshPrivateKey,
    {
      ...base,
      requestedSizeGb: await resolveRestoreSizeGb(base.grandGuid ?? base.repositoryGuid, params.at),
    },
    remoteRenetPath,
    sftp
  );
  if (!issued) {
    throw new Error(t('errors.subscription.activationFailed'));
  }
}

/**
 * Issue, and answer the server's machine-slot refusal in the same words the
 * pre-flight uses.
 *
 * A single-machine `repo create` never reaches the multi-machine pre-flight,
 * so this is where the wall is first seen for it. The raw server message says
 * the limit was reached; what the operator needs on top of that is that the
 * repository was NOT created and that a slot frees itself on the 5-hour
 * float, which is often the whole remedy.
 */
async function issueOrExplainSlotLimit(
  machine: Awaited<ReturnType<typeof configService.getLocalMachine>>,
  sshPrivateKey: string,
  repoLicenseCtx: RepoLicenseContext,
  remoteRenetPath: string,
  sftp?: SFTPClient
): Promise<boolean> {
  try {
    return await issueRepoLicense(
      machine,
      sshPrivateKey,
      {
        repositoryGuid: repoLicenseCtx.repositoryGuid,
        grandGuid: repoLicenseCtx.grandGuid,
        kind: repoLicenseCtx.kind,
        requestedSizeGb: repoLicenseCtx.requestedSizeGb,
        // Both halves of the scope, from one resolution: the server embeds it in the signed payload and the writer puts the blob on the path renet reads for this datastore. Sending one without the other is how the license ends up somewhere nothing looks.
        datastoreId: repoLicenseCtx.datastoreId,
      },
      remoteRenetPath,
      sftp
    );
  } catch (error) {
    if (!isMachineSlotLimitError(error)) throw error;
    const slots = await readMachineSlotStatus();
    const detail = slots
      ? machineSlotLimitMessage({
          needed: 1,
          active: slots.activeMachineCount,
          max: slots.maxMachines,
        })
      : (error as Error).message;
    throw new ValidationError(`${detail} ${t('errors.license.nothingProvisioned')}`);
  }
}

function buildMissingLicenseMessage(
  outcome: { failureMode: RepoBatchRecoveryFailureMode; serverErrorSample?: string } | undefined,
  machineName: string
): string {
  const base = ((): string => {
    switch (outcome?.failureMode) {
      case 'token_not_ready':
        return t('errors.license.recoveryFailedTokenNotReady');
      case 'no_known_repos':
        return t('errors.license.recoveryFailedNoKnownRepos', { machine: machineName });
      case 'server_rejected_all': {
        const errorDetail = outcome.serverErrorSample ?? '';
        return t('errors.license.recoveryFailedServerRejected', {
          error: errorDetail,
          machine: machineName,
        });
      }
      default:
        return (
          `A repo license is required for this operation, and automatic issuance did not succeed. ` +
          `Run: rdc subscription refresh -m ${machineName}`
        );
    }
  })();
  // Name the dev/test escape here (read by needsLicenseRecovery): it has bitten three agents who hit a license wall on a throwaway machine and did not know they could bypass activation entirely.
  return `${base} ${t('errors.license.skipActivationHint')}`;
}

function resolveLicenseRecoveryGuidance(
  failure: RenetLicenseFailure,
  machineName: string,
  outcome?: { failureMode: RepoBatchRecoveryFailureMode; serverErrorSample?: string }
): {
  errorCode?: string;
  guidance?: string;
  failFastMessage?: string;
  recoveryFailedMessage?: string;
} {
  switch (failure.reason) {
    case 'missing': {
      const recoveryFailedMessage = buildMissingLicenseMessage(outcome, machineName);
      return {
        errorCode: 'REPO_LICENSE_ISSUANCE_REQUIRED',
        guidance: `Issue repo licenses explicitly with: rdc subscription refresh -m ${machineName}`,
        recoveryFailedMessage,
      };
    }
    case 'expired':
      return {
        errorCode: 'REPO_LICENSE_REFRESH_REQUIRED',
        guidance: `Refresh repo licenses explicitly with: rdc subscription refresh -m ${machineName}`,
        recoveryFailedMessage:
          `The installed repo license must be refreshed before this operation can continue. ` +
          `Run: rdc subscription refresh -m ${machineName}`,
      };
    case 'machine_mismatch':
      return {
        errorCode: 'REPO_LICENSE_MACHINE_MISMATCH',
        guidance: `Reissue repo licenses from this machine context with: rdc subscription refresh -m ${machineName}`,
        failFastMessage:
          `The installed repo license belongs to a different machine. ` +
          `Reissue it from this machine context with: rdc subscription refresh -m ${machineName}`,
      };
    case 'repository_mismatch':
      return {
        errorCode: 'REPO_LICENSE_REPOSITORY_MISMATCH',
        guidance: `Refresh repo licenses explicitly with: rdc subscription refresh -m ${machineName}`,
        failFastMessage:
          `The installed repo license does not match the target repository. ` +
          `Refresh repo licenses explicitly with: rdc subscription refresh -m ${machineName}`,
      };
    case 'sequence_regression':
      return {
        errorCode: 'REPO_LICENSE_INTEGRITY_ERROR',
        guidance: `Replace the installed repo license with: rdc subscription refresh -m ${machineName}`,
        failFastMessage:
          `The installed repo license is older than the latest accepted sequence. ` +
          `Replace it with a newer repo license using: rdc subscription refresh -m ${machineName}`,
      };
    case 'invalid_signature':
      return {
        errorCode: 'REPO_LICENSE_INTEGRITY_ERROR',
        guidance: `Replace the installed repo license with: rdc subscription refresh -m ${machineName}`,
        failFastMessage:
          `The installed repo license could not be trusted. ` +
          `Replace it with a newly issued repo license using: rdc subscription refresh -m ${machineName}`,
      };
    case 'identity_mismatch':
      return {
        errorCode: 'REPO_LICENSE_IDENTITY_MISMATCH',
        guidance: `Reissue repo licenses with: rdc subscription refresh -m ${machineName}`,
        failFastMessage:
          `The repository identity does not match the installed repo license. ` +
          `Reissue repo licenses with: rdc subscription refresh -m ${machineName}`,
      };
    case 'cert_expired':
      return {
        errorCode: 'REPO_LICENSE_DELEGATION_CERT_EXPIRED',
        guidance: `Renew the on-prem delegation cert, then: rdc subscription refresh -m ${machineName}`,
        failFastMessage:
          `The on-prem delegation cert covering this license has expired. ` +
          `Renew it on the on-prem account server (auto-renew or the portal renew flow), ` +
          `then run: rdc subscription refresh -m ${machineName}`,
      };
    case 'cert_invalid':
      return {
        errorCode: 'REPO_LICENSE_DELEGATION_CERT_INVALID',
        guidance: `Fix the on-prem delegation cert, then: rdc subscription refresh -m ${machineName}`,
        failFastMessage:
          `The delegation cert attached to the installed repo license could not be trusted. ` +
          `Fix the on-prem cert, then reissue with: rdc subscription refresh -m ${machineName}`,
      };
    default:
      return {};
  }
}

export async function maybeRefreshRepoIdentity(
  options: ExecuteOptions,
  machine: Awaited<ReturnType<typeof configService.getLocalMachine>>,
  sshPrivateKey: string,
  remoteRenetPath: string,
  sftp: SFTPClient
): Promise<void> {
  if (process.env.REDIACC_SKIP_MACHINE_ACTIVATION === '1') return;
  if (!isRepoProvisioningFunction(options.functionName)) return;
  const repoLicense = await resolveRepoLicenseContext(
    options.functionName,
    options.machineName,
    options.params ?? {},
    sftp,
    { remoteRenetPath, required: false }
  );
  if (repoLicense) {
    await refreshRepoLicenseIdentity(machine, sshPrivateKey, repoLicense, remoteRenetPath, sftp);
  }
}

/**
 * Re-issue a repo license with identity proofs, for callers that ran a
 * create/fork with deferIdentityRefresh. Resolves the machine and SSH key
 * from the active config, reuses a pooled connection, and shares the SFTP
 * session with license issuance.
 */
export async function refreshRepoIdentityFor(
  functionName: string,
  machineName: string,
  params: Record<string, unknown>
): Promise<void> {
  if (process.env.REDIACC_SKIP_MACHINE_ACTIVATION === '1') return;
  const lease = await machineConnections.acquire(machineName);
  try {
    const repoLicense = await resolveRepoLicenseContext(
      functionName,
      machineName,
      params,
      lease.sftp,
      { required: false }
    );
    if (repoLicense) {
      await refreshRepoLicenseIdentity(
        lease.machine,
        lease.sshPrivateKey,
        repoLicense,
        undefined,
        lease.sftp
      );
    }
  } finally {
    lease.release();
  }
}
