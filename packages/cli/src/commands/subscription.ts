import { SUBSCRIPTION_DEFAULTS } from '@rediacc/shared/config';
import { TELEMETRY_SUBSCRIPTION_SOURCES } from '@rediacc/shared/telemetry';
import { Command } from 'commander';
import { t } from '../i18n/index.js';
import { accountServerFetch, fetchServerInfo } from '../services/account/account-client.js';
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
} from '../services/account/subscription-auth.js';
import { authorizeSubscriptionViaDeviceCode } from '../services/account/subscription-device-auth.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import { discoverRegions } from '../services/provision/region-discovery.js';
import { telemetryService } from '../services/telemetry/telemetry.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { promptRegionSelection } from '../utils/region-prompt.js';
import { withSpinner } from '../utils/spinner.js';
import {
  executeAccountRefresh,
  executeMachineRefresh,
  executeMachineStatus,
  executeRepoLicenseRefresh,
  executeSubscriptionStatus,
} from './subscription-actions.js';
import { outputSubscriptionScope } from './subscription-output.js';

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
    configAccountServer = currentRdcConfig?.account?.accountServer;
  } catch {
    /* config might not exist yet */
  }
  const serverUrl = getSubscriptionServerUrl(options.server, configAccountServer);

  // Save accountServer to active config for per-config isolation
  try {
    const configName = configService.getCurrentName();
    const currentRdcConfig = await configService.getCurrent();
    if (currentRdcConfig && currentRdcConfig.account?.accountServer !== serverUrl) {
      const { configFileStorage } = await import('../adapters/config-file-storage.js');
      await configFileStorage.update(configName, (cfg) => ({
        ...cfg,
        account: { ...(cfg.account ?? {}), accountServer: serverUrl },
      }));
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

  // subscription status [-m <machine>]
  // No -m = the account view. With -m = that machine's activation state plus its
  // per-repo license table (what `activation status` and `repo status` used to be).
  sub
    .command('status')
    .description(t('commands.subscription.status.description'))
    .option('-m, --machine <name>', t('options.machine'))
    .action(async (options) => {
      try {
        if (options.machine) {
          await executeMachineStatus(options.machine);
          return;
        }
        await executeSubscriptionStatus();
      } catch (error) {
        handleError(error);
      }
    });

  // subscription refresh [-m <machine>] [--repo <ref>]
  //
  // A PLAIN LEAF: it carries an .action() and MUST NOT grow subcommands. It used
  // to be an actionable parent (an .action() plus `activation`/`repos`/`repo`
  // children) with a .requiredOption('-m'), and Commander walks the parent chain
  // in _checkForMissingMandatoryOptions(), so that required flag fired for every
  // child too and bound to the parent even when typed after the subcommand.
  // Scope is chosen by flags now: none = account, -m = machine, --repo = one repo.
  sub
    .command('refresh')
    .description(t('commands.subscription.refresh.description'))
    .option('-m, --machine <name>', t('options.machine'))
    .option('--repo <ref>', t('options.repoRef'))
    .action(async (options) => {
      try {
        if (options.machine && options.repo) {
          throw new ValidationError(t('commands.subscription.refresh.targetExclusive'));
        }
        if (options.repo) {
          // --repo derives its own machine from the ref, so it never needs -m.
          await executeRepoLicenseRefresh(options.repo);
          return;
        }
        if (options.machine) {
          await executeMachineRefresh(options.machine);
          return;
        }
        await executeAccountRefresh();
      } catch (error) {
        handleError(error);
      }
    });
}

// Re-export execution functions so existing consumers (tests) continue to work
export {
  executeAccountRefresh,
  executeMachineRefresh,
  executeMachineStatus,
  executeRepoLicenseRefresh,
  executeSubscriptionStatus,
} from './subscription-actions.js';
