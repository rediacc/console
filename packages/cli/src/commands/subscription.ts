import { SUBSCRIPTION_DEFAULTS } from '@rediacc/shared/config';
import { TELEMETRY_SUBSCRIPTION_SOURCES } from '@rediacc/shared/telemetry';
import { Command } from 'commander';
import { t } from '../i18n/index.js';
import { accountServerFetch } from '../services/account-client.js';
import { configService } from '../services/config-resources.js';
import {
  fetchSubscriptionLicenseReport,
  type RepoBatchRefreshResult,
  readMachineActivationStatus,
  readRuntimeRepoLicenseStatuses,
  refreshMachineActivation,
  refreshRepoLicenseIdentity,
  refreshRepoLicensesBatch,
} from '../services/license.js';
import { outputService } from '../services/output.js';
import { provisionRenetToRemote, readSSHKey } from '../services/renet-execution.js';
import {
  deleteStoredSubscriptionToken,
  getSubscriptionScopeMismatch,
  getSubscriptionServerUrl,
  getSubscriptionTokenState,
  saveServerConfig,
  saveStoredSubscriptionToken,
} from '../services/subscription-auth.js';
import { authorizeSubscriptionViaDeviceCode } from '../services/subscription-device-auth.js';
import { telemetryService } from '../services/telemetry.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { withSpinner } from '../utils/spinner.js';
import {
  formatRuntimeRepoLicenseStatus,
  outputSubscriptionScope,
  renderMachineActivationStatus,
  renderRepoBatchRefreshSummary,
} from './subscription-output.js';

function setSubscriptionTelemetryContext(input: {
  subscriptionId?: string;
  planCode?: string;
  status?: string;
  source: string;
}): void {
  if (!input.subscriptionId && !input.planCode && !input.status) {
    return;
  }

  telemetryService.setUserContext({
    subscriptionId: input.subscriptionId,
    subscriptionPlanCode: input.planCode,
    subscriptionStatus: input.status,
    subscriptionSource: input.source,
  });
}

export function registerSubscriptionCommands(program: Command): void {
  const sub = program
    .command('subscription')
    .summary(t('commands.subscription.descriptionShort'))
    .description(t('commands.subscription.description'));

  // subscription login
  sub
    .command('login')
    .description(t('commands.subscription.login.description'))
    .option('-t, --token <token>', t('options.apiToken'))
    .option('--server <url>', t('options.serverUrl'))
    .action(async (options) => {
      try {
        // Persist server config when --server is explicitly provided
        if (options.server) {
          saveServerConfig({ accountServer: options.server });
        }
        const serverUrl = getSubscriptionServerUrl(options.server);

        if (options.token) {
          // Direct token mode (fallback)
          const token = options.token;
          const status = await withSpinner(
            t('commands.subscription.login.validating'),
            () =>
              accountServerFetch<{
                subscriptionId?: string;
                orgId?: string;
                orgName?: string;
                planCode?: string;
                status?: string;
                activeMachineCount?: number;
                maxMachines?: number;
                teamId?: string;
                teamName?: string;
              }>('/account/api/v1/licenses/status', { token, serverUrl }),
            t('commands.subscription.login.validated')
          );
          const currentTeamName = await configService.getTeam();
          const storedToken = {
            token,
            serverUrl,
            subscriptionId: status.subscriptionId,
            orgId: status.orgId,
            orgName: status.orgName,
            teamId: status.teamId,
            teamName: status.teamName ?? currentTeamName,
          };
          const mismatch = getSubscriptionScopeMismatch(storedToken, currentTeamName);
          if (mismatch) {
            throw new ValidationError(mismatch);
          }

          saveStoredSubscriptionToken(storedToken);

          const s = status;
          setSubscriptionTelemetryContext({
            subscriptionId: s.subscriptionId,
            planCode: s.planCode,
            status: s.status,
            source: TELEMETRY_SUBSCRIPTION_SOURCES.storedToken,
          });
          outputService.success(t('commands.subscription.login.success'));
          outputSubscriptionScope({
            orgName: s.orgName,
            teamName: s.teamName ?? currentTeamName,
            serverUrl,
          });
          outputService.info(
            t('commands.subscription.login.plan', {
              plan: s.planCode ?? SUBSCRIPTION_DEFAULTS.UNKNOWN_PLAN,
            })
          );
          outputService.info(
            t('commands.subscription.login.machines', {
              active: s.activeMachineCount ?? 0,
              max: s.maxMachines ?? SUBSCRIPTION_DEFAULTS.UNKNOWN_QUOTA,
            })
          );
        } else {
          const { status } = await authorizeSubscriptionViaDeviceCode(serverUrl, {
            interactive: true,
            teamName: await configService.getTeam(),
          });
          setSubscriptionTelemetryContext({
            subscriptionId: status.subscriptionId,
            planCode: status.planCode,
            source: TELEMETRY_SUBSCRIPTION_SOURCES.storedToken,
          });
          outputService.success(t('commands.subscription.login.success'));
          outputSubscriptionScope({
            orgName: status.orgName,
            teamName: status.teamName,
            serverUrl,
          });
          outputService.info(
            t('commands.subscription.login.plan', {
              plan: status.planCode ?? SUBSCRIPTION_DEFAULTS.UNKNOWN_PLAN,
            })
          );
          outputService.info(
            t('commands.subscription.login.machines', {
              active: status.activeMachineCount ?? 0,
              max: status.maxMachines ?? SUBSCRIPTION_DEFAULTS.UNKNOWN_QUOTA,
            })
          );
        }
      } catch (error) {
        handleError(error);
      }
    });

  // subscription logout
  sub
    .command('logout')
    .description(t('commands.subscription.logout.description'))
    .action(() => {
      try {
        deleteStoredSubscriptionToken();
        outputService.success(t('commands.subscription.logout.success'));
      } catch (error) {
        handleError(error);
      }
    });

  // subscription status
  sub
    .command('status')
    .description(t('commands.subscription.status.description'))
    .action(async () => {
      try {
        await executeSubscriptionStatus();
      } catch (error) {
        handleError(error);
      }
    });

  // subscription activation (subgroup)
  const activation = sub
    .command('activation')
    .description(t('commands.subscription.activation.description'));

  activation
    .command('status')
    .description(t('commands.subscription.activation.status.description'))
    .requiredOption('-m, --machine <name>', t('options.machine'))
    .action(async (options) => {
      try {
        await executeActivationStatus(options.machine);
      } catch (error) {
        handleError(error);
      }
    });

  // subscription repo (subgroup)
  const repo = sub.command('repo').description(t('commands.subscription.repo.description'));

  repo
    .command('status')
    .description(t('commands.subscription.repo.status.description'))
    .requiredOption('-m, --machine <name>', t('options.machine'))
    .action(async (options) => {
      try {
        await executeRepoStatus(options.machine);
      } catch (error) {
        handleError(error);
      }
    });

  // subscription refresh (subgroup — no subcommand = refresh all)
  const refresh = sub
    .command('refresh')
    .description(t('commands.subscription.refresh.description'))
    .requiredOption('-m, --machine <name>', t('options.machine'))
    .action(async (options) => {
      try {
        await executeSubscriptionRefresh(options.machine);
      } catch (error) {
        handleError(error);
      }
    });

  refresh
    .command('activation')
    .description(t('commands.subscription.refresh.activation.description'))
    .requiredOption('-m, --machine <name>', t('options.machine'))
    .action(async (options) => {
      try {
        await executeActivationRefresh(options.machine);
      } catch (error) {
        handleError(error);
      }
    });

  refresh
    .command('repos')
    .description(t('commands.subscription.refresh.repos.description'))
    .requiredOption('-m, --machine <name>', t('options.machine'))
    .action(async (options) => {
      try {
        await executeRepoRefresh(options.machine);
      } catch (error) {
        handleError(error);
      }
    });

  refresh
    .command('repo <repo>')
    .description(t('commands.subscription.refresh.repo.description'))
    .requiredOption('-m, --machine <name>', t('options.machine'))
    .action(async (repoName, options) => {
      try {
        await withSpinner(
          t('commands.subscription.refresh.repo.refreshing'),
          async () => {
            const localConfig = await configService.getLocalConfig();
            const machine = await configService.getLocalMachine(options.machine);
            const repoConfig = await configService.getRepository(repoName);
            if (!repoConfig) {
              throw new ValidationError(
                t('commands.subscription.refresh.repo.notFound', { repoName })
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

        outputService.success(t('commands.subscription.refresh.repo.success', { repoName }));
      } catch (error) {
        handleError(error);
      }
    });
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

interface SubscriptionCommandContext {
  machine: Awaited<ReturnType<typeof configService.getLocalMachine>>;
  sshPrivateKey: string;
  remoteRenetPath: string;
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

async function assertSubscriptionScopeMatchesConfig(tokenState: {
  teamName?: string;
}): Promise<void> {
  const configTeamName = await configService.getTeam();
  const mismatch = getSubscriptionScopeMismatch(tokenState, configTeamName);
  if (mismatch) {
    throw new ValidationError(mismatch);
  }
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
