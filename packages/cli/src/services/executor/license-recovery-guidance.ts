/**
 * The operator-facing text of a license refusal (see license-recovery.ts): the
 * error code, guidance line and fail-fast or recovery-failed message per reason.
 */

import { t } from '../../i18n/index.js';
import type { RepoBatchRecoveryFailureMode } from '../account/license.js';
import type { RenetLicenseFailure } from '../renet/renet-license-contract.js';

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
  return base;
}

export function resolveLicenseRecoveryGuidance(
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
