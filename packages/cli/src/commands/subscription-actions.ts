/**
 * Subscription execution logic: status, activation, refresh, and repo operations.
 * Extracted from subscription.ts to stay within max-lines.
 */

import { t } from '../i18n/index.js';
import {
  fetchSubscriptionLicenseReport,
  type RepoBatchRefreshResult,
  readMachineActivationStatus,
  readRuntimeRepoLicenseStatuses,
  refreshMachineActivation,
  refreshRepoLicensesBatch,
} from '../services/license.js';
import { outputService } from '../services/output.js';
import { provisionRenetToRemote, readSSHKey } from '../services/renet-execution.js';
import { configService } from '../services/config-resources.js';
import {
  getSubscriptionScopeMismatch,
  getSubscriptionTokenState,
} from '../services/subscription-auth.js';
import { ValidationError } from '../utils/errors.js';
import { withSpinner } from '../utils/spinner.js';
import {
  formatRuntimeRepoLicenseStatus,
  outputSubscriptionScope,
  renderMachineActivationStatus,
  renderRepoBatchRefreshSummary,
} from './subscription-output.js';

export interface SubscriptionCommandContext {
  machine: Awaited<ReturnType<typeof configService.getLocalMachine>>;
  sshPrivateKey: string;
  remoteRenetPath: string;
}

export function handleSubscriptionTokenState(
  tokenState: ReturnType<typeof getSubscriptionTokenState>
): boolean {
  if (tokenState.kind === 'missing') {
    outputService.info(t('errors.subscription.notLoggedIn'));
    return true;
  }
  if (tokenState.kind === 'server_mismatch') {
    outputService.warn(
      t('commands.subscription.status.serverMismatch', {
        actualServerUrl: tokenState.actualServerUrl,
        expectedServerUrl: tokenState.expectedServerUrl,
      })
    );
    return true;
  }
  return false;
}

async function assertSubscriptionScopeMatchesConfig(tokenState: {
  teamName?: string;
}): Promise<void> {
  const configTeamName = await configService.getTeam();
  const mismatch = getSubscriptionScopeMismatch(tokenState, configTeamName);
  if (mismatch) {
    throw new ValidationError(mismatch);
  }
}

export async function resolveSubscriptionCommandContext(
  machineName: string
): Promise<SubscriptionCommandContext> {
  const tokenState = getSubscriptionTokenState();
  if (tokenState.kind !== 'ready') {
    handleSubscriptionTokenState(tokenState);
    throw new ValidationError(t('errors.subscription.notLoggedIn'));
  }
  await assertSubscriptionScopeMatchesConfig(tokenState.token);
  const localConfig = await configService.getLocalConfig();
  const machine = await configService.getLocalMachine(machineName);
  const sshPrivateKey =
    localConfig.sshPrivateKey ?? (await readSSHKey(localConfig.ssh.privateKeyPath));
  const { remotePath: remoteRenetPath } = await provisionRenetToRemote(
    localConfig,
    machine,
    sshPrivateKey,
    { skipRouterRestart: true }
  );
  return { machine, sshPrivateKey, remoteRenetPath };
}

export async function executeSubscriptionStatus(): Promise<void> {
  const tokenState = getSubscriptionTokenState();
  if (tokenState.kind !== 'ready') {
    handleSubscriptionTokenState(tokenState);
    return;
  }
  await assertSubscriptionScopeMatchesConfig(tokenState.token);

  try {
    const status = await fetchSubscriptionLicenseReport();
    if (!status) return;
    outputRemoteStatus(status);
  } catch {
    // Remote status is optional
  }
}

export function outputRemoteStatus(
  status: Awaited<ReturnType<typeof fetchSubscriptionLicenseReport>>
) {
  if (!status) return;
  outputService.info(t('commands.subscription.status.remote'));
  outputSubscriptionScope({
    orgName: status.orgName,
    teamName: status.teamName,
  });
  outputService.info(t('commands.subscription.status.remotePlan', { plan: status.planCode }));
  outputService.info(t('commands.subscription.status.remoteStatus', { status: status.status }));
  outputService.info(
    t('commands.subscription.status.remoteMachineActivations', {
      active: status.machineSlots.active,
      max: status.machineSlots.max,
    })
  );
  outputService.info(
    t('commands.subscription.status.remoteRepoLicenseIssuances', {
      used: status.repoLicenseIssuances.used,
      limit: status.repoLicenseIssuances.limit,
    })
  );
  const issuanceUsage =
    status.repoLicenseIssuances.limit > 0
      ? status.repoLicenseIssuances.used / status.repoLicenseIssuances.limit
      : 0;
  if (issuanceUsage >= 1) {
    outputService.warn(t('commands.subscription.status.issuanceLimitReached'));
  } else if (issuanceUsage >= 0.95) {
    outputService.warn(t('commands.subscription.status.issuanceUsageHigh95'));
  } else if (issuanceUsage >= 0.8) {
    outputService.warn(t('commands.subscription.status.issuanceUsageHigh80'));
  }
  outputService.info(
    t('commands.subscription.status.remoteRepoLicenses', {
      totalTrackedRepos: status.repoLicenses.totalTrackedRepos,
      validCount: status.repoLicenses.validCount,
      refreshRecommendedCount: status.repoLicenses.refreshRecommendedCount,
      hardExpiredCount: status.repoLicenses.hardExpiredCount,
    })
  );
  for (const machine of status.machineSlots.machines) {
    outputService.info(
      t('commands.subscription.status.remoteMachine', {
        id: machine.machineId.slice(0, 12),
        lastSeen: machine.lastSeenAt,
      })
    );
  }
}

export async function executeRepoStatus(machineName: string): Promise<void> {
  const localConfig = await configService.getLocalConfig();
  const machine = await configService.getLocalMachine(machineName);
  const sshPrivateKey =
    localConfig.sshPrivateKey ?? (await readSSHKey(localConfig.ssh.privateKeyPath));
  const { remotePath: remoteRenetPath } = await provisionRenetToRemote(
    localConfig,
    machine,
    sshPrivateKey,
    { skipRouterRestart: true }
  );
  const entries = await readRuntimeRepoLicenseStatuses(machine, sshPrivateKey, remoteRenetPath);

  outputService.info(t('commands.subscription.repo.status.header', { machineName }));
  if (entries.length === 0) {
    outputService.info(t('commands.subscription.repo.status.empty'));
    return;
  }

  for (const entry of entries) {
    const effectiveHardExpiry = entry.hardExpiresAt ?? entry.expiresAt;
    outputService.info(
      t('commands.subscription.repo.status.entry', {
        repositoryGuid: entry.repositoryGuid,
        freshness: formatRuntimeRepoLicenseStatus(entry),
        hardExpirySuffix: effectiveHardExpiry
          ? t('commands.subscription.repo.status.hardExpirySuffix', {
              effectiveHardExpiry,
            })
          : '',
      })
    );
  }
}

export async function executeActivationStatus(machineName: string): Promise<void> {
  try {
    const context = await resolveSubscriptionCommandContext(machineName);
    const activation = await readMachineActivationStatus(
      context.machine,
      context.sshPrivateKey,
      context.remoteRenetPath
    );
    renderMachineActivationStatus(machineName, activation);
  } catch {
    outputService.warn(t('commands.subscription.status.parseFailed'));
  }
}

export async function runMachineActivationRefresh(
  context: SubscriptionCommandContext
): Promise<void> {
  await withSpinner(
    t('commands.subscription.refresh.refreshing'),
    async () => {
      const issued = await refreshMachineActivation(
        context.machine,
        context.sshPrivateKey,
        context.remoteRenetPath
      );
      if (!issued) {
        throw new ValidationError(t('commands.subscription.refresh.failed'));
      }
    },
    t('commands.subscription.refresh.refreshed')
  );
}

export async function runRepoBatchRefresh(
  context: SubscriptionCommandContext
): Promise<RepoBatchRefreshResult> {
  return withSpinner(
    t('commands.subscription.refresh.repos.refreshing'),
    () => refreshRepoLicensesBatch(context.machine, context.sshPrivateKey, context.remoteRenetPath),
    t('commands.subscription.refresh.repos.refreshed')
  );
}

export async function executeSubscriptionRefresh(machineName: string): Promise<void> {
  const context = await resolveSubscriptionCommandContext(machineName);
  await runMachineActivationRefresh(context);
  const batchSummary = await runRepoBatchRefresh(context);
  outputService.success(t('commands.subscription.refresh.success'));
  renderRepoBatchRefreshSummary(batchSummary);
}

export async function executeActivationRefresh(machineName: string): Promise<void> {
  const context = await resolveSubscriptionCommandContext(machineName);
  await runMachineActivationRefresh(context);
  outputService.success(t('commands.subscription.refresh.refreshed'));
}

export async function executeRepoRefresh(machineName: string): Promise<void> {
  const context = await resolveSubscriptionCommandContext(machineName);
  const batchSummary = await runRepoBatchRefresh(context);
  outputService.success(t('commands.subscription.refresh.repos.success'));
  renderRepoBatchRefreshSummary(batchSummary);
}
