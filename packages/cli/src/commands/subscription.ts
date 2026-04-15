import { SUBSCRIPTION_DEFAULTS } from '@rediacc/shared/config';
import { TELEMETRY_SUBSCRIPTION_SOURCES } from '@rediacc/shared/telemetry';
import { Command } from 'commander';
import { t } from '../i18n/index.js';
import { accountServerFetch, fetchServerInfo } from '../services/account-client.js';
import { configService } from '../services/config-resources.js';
import { refreshRepoLicenseIdentity } from '../services/license.js';
import { outputService } from '../services/output.js';
import { readSSHKey } from '../services/renet-execution.js';
import {
  deleteServerConfig,
  deleteStoredSubscriptionToken,
  getSubscriptionScopeMismatch,
  getSubscriptionServerUrl,
  isDevelopmentSubscriptionMode,
  loadServerConfig,
  normalizeServerUrl,
  saveServerConfig,
  saveStoredSubscriptionToken,
} from '../services/subscription-auth.js';
import { authorizeSubscriptionViaDeviceCode } from '../services/subscription-device-auth.js';
import { discoverRegions } from '../services/region-discovery.js';
import { promptRegionSelection } from '../utils/region-prompt.js';
import { telemetryService } from '../services/telemetry.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { withSpinner } from '../utils/spinner.js';
import { outputSubscriptionScope } from './subscription-output.js';
import {
  executeActivationRefresh,
  executeActivationStatus,
  executeRepoRefresh,
  executeRepoStatus,
  executeSubscriptionRefresh,
  executeSubscriptionStatus,
} from './subscription-actions.js';

/** Clear session and notify when the server URL has changed. */
function handleServerChange(currentServer: string | undefined, newServer: string): void {
  if (currentServer && normalizeServerUrl(currentServer) !== normalizeServerUrl(newServer)) {
    deleteStoredSubscriptionToken();
    outputService.info(t('commands.subscription.login.serverChanged'));
  }
}

/** Persist explicit --server flag and detect server changes. */
function persistExplicitServer(server: string): void {
  handleServerChange(loadServerConfig()?.accountServer, server);
  saveServerConfig({ accountServer: server });
}

/** Prompt user for a data region when no server is configured yet. */
async function promptRegionIfNeeded(): Promise<void> {
  if (isDevelopmentSubscriptionMode() || loadServerConfig()?.accountServer) return;

  const regions = await withSpinner(
    t('commands.subscription.login.discoveringRegions'),
    () => discoverRegions(),
    t('commands.subscription.login.regionsDiscovered')
  );
  const selection = await promptRegionSelection(regions);
  const newServer = `https://${selection.domain}`;
  handleServerChange(loadServerConfig()?.accountServer, newServer);
  saveServerConfig({ accountServer: newServer, region: selection.region.id });
  outputService.info(
    t('commands.subscription.login.regionSelected', {
      region: selection.region.label,
      domain: selection.domain,
    })
  );
}

/**
 * Resolve the account server URL and auto-sync update channel + e2e key from server-info.
 * Returns the resolved server URL for use in subsequent requests.
 */
async function resolveAndSyncServer(options: { server?: string }): Promise<string> {
  // Resolve server URL. See getSubscriptionServerUrl() for the precedence
  // order — server.json wins over rediacc.json so the region picker's most
  // recent choice takes effect on the next login.
  let configAccountServer: string | undefined;
  try {
    const currentRdcConfig = await configService.getCurrent();
    configAccountServer = currentRdcConfig?.accountServer;
  } catch {
    /* config might not exist yet */
  }
  const serverUrl = getSubscriptionServerUrl(options.server, configAccountServer);

  // Save accountServer to active config for per-config isolation
  try {
    const configName = configService.getCurrentName();
    const currentRdcConfig = await configService.getCurrent();
    if (currentRdcConfig && currentRdcConfig.accountServer !== serverUrl) {
      await configService.update(configName, { accountServer: serverUrl });
    }
  } catch {
    /* config might not exist yet */
  }

  // Auto-sync update channel and e2e key from server-info
  try {
    const info = await fetchServerInfo(serverUrl);
    const currentServerConfig = loadServerConfig();
    saveServerConfig({
      ...currentServerConfig,
      accountServer: serverUrl,
      updateChannel: info.updateChannel ?? currentServerConfig?.updateChannel,
      e2ePublicKey: info.e2e.keys[0]?.publicKeySpki ?? currentServerConfig?.e2ePublicKey,
    });
    if (info.updateChannel) {
      outputService.info(
        t('commands.subscription.login.channelSynced', { channel: info.updateChannel })
      );
    }
  } catch {
    // server-info fetch failed -- non-fatal, continue with existing config
  }

  return serverUrl;
}

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
        if (options.server) {
          persistExplicitServer(options.server);
        } else {
          await promptRegionIfNeeded();
        }

        const serverUrl = await resolveAndSyncServer(options);

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
        // Also clear the saved server config so the next `login` shows the
        // region picker again. Without this, a user who logged in once would
        // be permanently pinned to that region with no way to switch short
        // of manually deleting ~/.config/rediacc/server.json.
        deleteServerConfig();
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
    .command('repo')
    .description(t('commands.subscription.refresh.repo.description'))
    .requiredOption('--name <name>', t('options.name'))
    .requiredOption('-m, --machine <name>', t('options.machine'))
    .action(async (options) => {
      try {
        const repoName = options.name;
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

// Re-export execution functions so existing consumers (tests) continue to work
export {
  executeActivationRefresh,
  executeActivationStatus,
  executeRepoRefresh,
  executeRepoStatus,
  executeSubscriptionRefresh,
  executeSubscriptionStatus,
  handleSubscriptionTokenState,
  outputRemoteStatus,
  resolveSubscriptionCommandContext,
  runRepoBatchRefresh,
  type SubscriptionCommandContext,
} from './subscription-actions.js';
