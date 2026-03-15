import { t } from '../i18n/index.js';
import type { MachineActivationStatus, RepoBatchRefreshResult } from '../services/license.js';
import { outputService } from '../services/output.js';

export function outputSubscriptionScope(input: {
  orgName?: string;
  teamName?: string;
  serverUrl?: string;
}): void {
  if (input.serverUrl) {
    outputService.info(`Server: ${input.serverUrl}`);
  }
  if (input.orgName) {
    outputService.info(`Organization: ${input.orgName}`);
  }
  if (input.teamName) {
    outputService.info(`Team: ${input.teamName}`);
  }
}

export function renderRepoBatchRefreshSummary(batchSummary: RepoBatchRefreshResult): void {
  outputService.info(
    `Repo licenses: scanned ${batchSummary.scanned}, issued ${batchSummary.issued}, refreshed ${batchSummary.refreshed}, unchanged ${batchSummary.unchanged}, failed ${batchSummary.failed}`
  );
  for (const failure of batchSummary.failures) {
    outputService.warn(`${failure.repositoryGuid}: ${failure.error}`);
  }
}

export function renderMachineActivationStatus(
  machineName: string,
  activation: MachineActivationStatus | null
): void {
  outputService.info(t('commands.subscription.activation.status.header', { machineName }));
  if (!activation) {
    outputService.warn(t('commands.subscription.activation.status.unavailable'));
    return;
  }

  outputService.info(
    t('commands.subscription.activation.status.machineId', { machineId: activation.machineId })
  );
  if (typeof activation.activeCount === 'number' && typeof activation.maxCount === 'number') {
    outputService.info(
      t('commands.subscription.activation.status.activations', {
        active: activation.activeCount,
        max: activation.maxCount,
      })
    );
  }
  if (activation.active) {
    outputService.success(
      t('commands.subscription.activation.status.active', { lastSeenAt: activation.lastSeenAt })
    );
    return;
  }
  outputService.warn(t('commands.subscription.activation.status.inactive'));
}

export function getRepoLicenseFreshness(entry: {
  expiresAt?: string;
  refreshRecommendedAt?: string;
  hardExpiresAt?: string;
}): 'unknown' | 'hardExpired' | 'refreshRecommended' | 'valid' {
  const effectiveHardExpiry = entry.hardExpiresAt ?? entry.expiresAt;
  if (!effectiveHardExpiry) {
    return 'unknown';
  }
  if (new Date(effectiveHardExpiry) <= new Date()) {
    return 'hardExpired';
  }
  if (entry.refreshRecommendedAt && new Date(entry.refreshRecommendedAt) <= new Date()) {
    return 'refreshRecommended';
  }
  return 'valid';
}

export function formatRuntimeRepoLicenseStatus(entry: {
  status: string;
  runtimeValid: boolean;
  refreshRecommendedAt?: string;
}): string {
  if (entry.runtimeValid) {
    if (entry.refreshRecommendedAt && new Date(entry.refreshRecommendedAt) <= new Date()) {
      return 'valid (refresh recommended)';
    }
    return 'valid';
  }

  switch (entry.status) {
    case 'missing':
      return 'missing';
    case 'expired':
      return 'expired';
    case 'machine_mismatch':
      return 'machine mismatch';
    case 'repository_mismatch':
      return 'repository mismatch';
    case 'sequence_regression':
      return 'sequence regression';
    case 'invalid_signature':
      return 'invalid signature';
    case 'identity_mismatch':
      return 'identity mismatch';
    default:
      return 'unknown';
  }
}
