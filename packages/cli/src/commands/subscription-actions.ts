/**
 * Subscription execution logic: the account view, the machine license view, and
 * the three refresh scopes (account, machine, single repo).
 *
 * Extracted from subscription.ts to stay within max-lines. The command file
 * registers four flat leaves (login, logout, status, refresh); the scope of a
 * status or a refresh is chosen here by which function the leaf dispatches to.
 */

import { t } from '../i18n/index.js';
import {
  fetchSubscriptionLicenseReport,
  type RepoBatchRefreshResult,
  readMachineActivationStatus,
  readRuntimeRepoLicenseStatuses,
  refreshRepoLicenseIdentity,
  refreshRepoLicensesBatch,
} from '../services/account/license.js';
import {
  getSubscriptionScopeMismatch,
  getSubscriptionServerUrl,
  getSubscriptionTokenState,
} from '../services/account/subscription-auth.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import { provisionRenetToRemote, readSSHKey } from '../services/renet/renet-execution.js';
import { ValidationError } from '../utils/errors.js';
import { resolveRepoRef } from '../utils/repo-target.js';
import { withSpinner } from '../utils/spinner.js';
import {
  formatRuntimeRepoLicenseStatus,
  outputSubscriptionScope,
  renderMachineActivationStatus,
  renderRepoBatchRefreshSummary,
} from './subscription-output.js';

interface SubscriptionCommandContext {
  machine: Awaited<ReturnType<typeof configService.getLocalMachine>>;
  sshPrivateKey: string;
  remoteRenetPath: string;
}

function handleSubscriptionTokenState(
  tokenState: ReturnType<typeof getSubscriptionTokenState>
): boolean {
  if (tokenState.kind === 'missing') {
    outputService.info(t('errors.subscription.notLoggedIn'));
    outputService.info(
      t('commands.subscription.status.serverWouldUse', { server: getSubscriptionServerUrl() })
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

/**
 * SSH context for a machine-scoped subscription command. Deliberately NOT
 * token-gated: the per-repo license table is read out of renet's runtime state
 * on the machine, so it must still render when the account server is
 * unreachable or nobody is signed in.
 */
async function resolveMachineContext(machineName: string): Promise<SubscriptionCommandContext> {
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

/** The token-gated form, for the refresh paths that must reach the account server. */
async function resolveSubscriptionCommandContext(
  machineName: string
): Promise<SubscriptionCommandContext> {
  const tokenState = getSubscriptionTokenState();
  if (tokenState.kind !== 'ready') {
    handleSubscriptionTokenState(tokenState);
    throw new ValidationError(t('errors.subscription.notLoggedIn'));
  }
  await assertSubscriptionScopeMatchesConfig(tokenState.token);
  return resolveMachineContext(machineName);
}

/** `subscription status` with no `-m`: the account view. */
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

function outputRemoteStatus(status: Awaited<ReturnType<typeof fetchSubscriptionLicenseReport>>) {
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

/** The per-repo license table read out of renet's runtime state on the machine. */
async function renderRepoLicenseTable(
  machineName: string,
  context: SubscriptionCommandContext
): Promise<void> {
  const entries = await readRuntimeRepoLicenseStatuses(
    context.machine,
    context.sshPrivateKey,
    context.remoteRenetPath
  );

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

/**
 * The machine activation section. Best-effort by design: it needs the account
 * server, and a failure there must not suppress the repo license table that
 * follows it.
 */
async function renderActivationSection(
  machineName: string,
  context: SubscriptionCommandContext
): Promise<void> {
  const tokenState = getSubscriptionTokenState();
  if (tokenState.kind !== 'ready') {
    handleSubscriptionTokenState(tokenState);
    return;
  }

  try {
    await assertSubscriptionScopeMatchesConfig(tokenState.token);
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

/**
 * `subscription status -m <machine>`: activation state plus the per-repo license
 * table. One renet provisioning serves both sections.
 */
export async function executeMachineStatus(machineName: string): Promise<void> {
  const context = await resolveMachineContext(machineName);
  await renderActivationSection(machineName, context);
  await renderRepoLicenseTable(machineName, context);
}

async function runRepoBatchRefresh(
  context: SubscriptionCommandContext
): Promise<RepoBatchRefreshResult> {
  return withSpinner(
    t('commands.subscription.refresh.repos.refreshing'),
    () => refreshRepoLicensesBatch(context.machine, context.sshPrivateKey, context.remoteRenetPath),
    t('commands.subscription.refresh.repos.refreshed')
  );
}

/** `subscription refresh` with no flags: re-read the account state from the server. */
export async function executeAccountRefresh(): Promise<void> {
  const tokenState = getSubscriptionTokenState();
  if (tokenState.kind !== 'ready') {
    handleSubscriptionTokenState(tokenState);
    throw new ValidationError(t('errors.subscription.notLoggedIn'));
  }
  await assertSubscriptionScopeMatchesConfig(tokenState.token);

  const status = await withSpinner(
    t('commands.subscription.refresh.account.refreshing'),
    () => fetchSubscriptionLicenseReport(),
    t('commands.subscription.refresh.account.refreshed')
  );
  if (!status) {
    throw new ValidationError(t('commands.subscription.refresh.account.failed'));
  }
  outputRemoteStatus(status);
}

/** `subscription refresh -m <machine>`: reissue every repo license on the machine. */
export async function executeMachineRefresh(machineName: string): Promise<void> {
  const context = await resolveSubscriptionCommandContext(machineName);
  const batchSummary = await runRepoBatchRefresh(context);
  outputService.success(t('commands.subscription.refresh.success'));
  renderRepoBatchRefreshSummary(batchSummary);
}

/**
 * `subscription refresh --repo <ref>`: reissue one repo's license. The machine
 * is derived from the ref (spec/03 §2.3), so this verb never takes `-m`.
 */
export async function executeRepoLicenseRefresh(ref: string): Promise<void> {
  const { repoKey, machineName } = await resolveRepoRef(ref, { readOnly: true });

  await withSpinner(
    t('commands.subscription.refresh.repo.refreshing'),
    async () => {
      const localConfig = await configService.getLocalConfig();
      const machine = await configService.getLocalMachine(machineName);
      const repoConfig = await configService.getRepository(repoKey);
      if (!repoConfig) {
        throw new ValidationError(
          t('commands.subscription.refresh.repo.notFound', { repoName: repoKey })
        );
      }
      const sshPrivateKey =
        localConfig.sshPrivateKey ?? (await readSSHKey(localConfig.ssh.privateKeyPath));

      const refreshed = await refreshRepoLicenseIdentity(machine, sshPrivateKey, {
        repositoryGuid: repoConfig.repositoryGuid,
        grandGuid: repoConfig.grandGuid,
        kind:
          repoConfig.grandGuid && repoConfig.grandGuid !== repoConfig.repositoryGuid
            ? 'fork'
            : 'grand',
      });
      if (!refreshed) {
        throw new ValidationError(t('commands.subscription.refresh.repo.failed'));
      }
    },
    t('commands.subscription.refresh.repo.refreshed')
  );

  outputService.success(t('commands.subscription.refresh.repo.success', { repoName: repoKey }));
}
