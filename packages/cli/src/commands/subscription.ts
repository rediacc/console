import { SUBSCRIPTION_DEFAULTS } from '@rediacc/shared/config';
import { TELEMETRY_SUBSCRIPTION_SOURCES } from '@rediacc/shared/telemetry';
import { Command } from 'commander';
import { configFileStorage } from '../adapters/config-file-storage.js';
import { t } from '../i18n/index.js';
import { accountServerFetch, fetchServerInfo } from '../services/account/account-client.js';
import { readAccountPointer } from '../services/account/account-pointer.js';
import {
  deleteStoredSubscriptionToken,
  getSubscriptionScopeMismatch,
  getSubscriptionServerUrl,
  normalizeServerUrl,
  saveStoredSubscriptionToken,
} from '../services/account/subscription-auth.js';
import { authorizeSubscriptionViaDeviceCode } from '../services/account/subscription-device-auth.js';
import { getEffectiveConfigName } from '../services/config/config-name.js';
import { configService } from '../services/config/config-resources.js';
import { updateConfigAtPointer } from '../services/config/synced-write.js';
import { outputService } from '../services/core/output.js';
import { discoverRegions } from '../services/provision/region-discovery.js';
import { telemetryService } from '../services/telemetry/telemetry.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { promptRegionSelection } from '../utils/region-prompt.js';
import { withSpinner } from '../utils/spinner.js';
import { readStdinValue } from '../utils/stdin.js';
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

type AccountField = 'accountServer' | 'e2ePublicKey' | 'updateChannel';

/**
 * The login fields: per device (operator ruling 2026-09-25, "Logout is per device"), so they are
 * DEVICE_LOCAL_POINTERS and `updateConfigAtPointer` writes them to this device's file only, never
 * to a remote config's store.
 */
const LOGIN_FIELDS = ['accountServer', 'e2ePublicKey'] as const;

/**
 * Write account fields into the active config. A config that does not exist yet is skipped; any
 * other write failure throws, because a lost `e2ePublicKey` makes every later request decrypt with
 * the production key and fail as "Decryption failed", naming nothing (2026-10-21). Each field is
 * routed by its pointer: the login fields stay on this device, `updateChannel` syncs, and is
 * written only when it changes, so a login does not push an unchanged channel.
 */
async function patchActiveAccount(fields: Partial<Record<AccountField, string>>): Promise<void> {
  const configName = getEffectiveConfigName();
  if (!(await configFileStorage.exists(configName))) return;
  for (const [field, value] of Object.entries(fields) as [AccountField, string | undefined][]) {
    if (value === undefined) continue;
    if (field === 'updateChannel' && readAccountPointer(configName).updateChannel === value)
      continue;
    const write = updateConfigAtPointer(configName, `/account/${field}`, (cfg) => ({
      ...cfg,
      account: { ...(cfg.account ?? {}), [field]: value },
    }));
    if (field !== 'updateChannel') {
      await write;
      continue;
    }
    // The channel is a synced preference, not a login field: a remote config that cannot take the
    // write right now keeps its old channel rather than failing the login.
    await write.catch((error: unknown) => {
      outputService.warn(
        `update channel not saved: ${error instanceof Error ? error.message : String(error)}`
      );
    });
  }
}

/** Persist explicit --server flag and detect server changes. */
async function persistExplicitServer(server: string): Promise<void> {
  handleServerChange(readAccountPointer().accountServer, server);
  await patchActiveAccount({ accountServer: server });
}

/** Prompt user for a data region when no server is configured yet. */
async function promptRegionIfNeeded(): Promise<void> {
  if (readAccountPointer().accountServer) return;

  const regions = await withSpinner(
    t('commands.subscription.login.discoveringRegions'),
    () => discoverRegions(),
    t('commands.subscription.login.regionsDiscovered')
  );
  const selection = await promptRegionSelection(regions);
  const newServer = `https://${selection.domain}`;
  handleServerChange(readAccountPointer().accountServer, newServer);
  await patchActiveAccount({ accountServer: newServer });
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
export async function resolveAndSyncServer(options: { server?: string }): Promise<string> {
  // Resolve the server URL from --server / env / active config / default.
  const serverUrl = getSubscriptionServerUrl(options.server);

  // Pin the resolved server into the active config for per-config isolation.
  await patchActiveAccount({ accountServer: serverUrl });

  // Auto-sync update channel and e2e key from server-info into the active config. Only the fetch is
  // non-fatal: a server-info that cannot be read leaves the existing config, but one that was read
  // and then could not be persisted is an error, never a silent fall back to the production key.
  let info: Awaited<ReturnType<typeof fetchServerInfo>> | undefined;
  try {
    info = await fetchServerInfo(serverUrl);
  } catch (error) {
    info = undefined;
    outputService.warn(
      `server-info unreachable at ${serverUrl}; the saved channel and e2e key are kept: ${error instanceof Error ? error.message : String(error)}`
    );
  }
  if (info) {
    await patchActiveAccount({
      updateChannel: info.updateChannel,
      e2ePublicKey: info.e2e?.keys?.[0]?.publicKeySpki,
    });
    if (info.updateChannel) {
      outputService.info(
        t('commands.subscription.login.channelSynced', { channel: info.updateChannel })
      );
    }
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

/**
 * The post-login summary. One renderer for both login paths (an explicit
 * `--token` and the device-code flow), which had drifted into two copies of the
 * same four lines.
 */
function renderLoginSummary(
  status: {
    orgName?: string;
    planCode?: string;
    activeMachineCount?: number;
    maxMachines?: number;
    overLimitCount?: number;
  },
  teamName: string | undefined,
  serverUrl: string
): void {
  outputService.success(t('commands.subscription.login.success'));
  outputSubscriptionScope({ orgName: status.orgName, teamName, serverUrl });
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
  // Soft-claimed slots: renewals still succeed, but new repositories cannot be licensed, so say it at login rather than at the next `repo create`.
  if ((status.overLimitCount ?? 0) > 0) {
    outputService.warn(
      t('commands.subscription.login.machinesOverLimit', { count: status.overLimitCount })
    );
  }
}

/** The `--token` value, or, for `-`, the token read from stdin: that form keeps the token off argv and out of the process list. Either form is trimmed, and an empty or whitespace-only token is refused. */
export async function resolveLoginToken(option: string): Promise<string> {
  const token = (option === '-' ? await readStdinValue() : option).trim();
  if (token.length === 0) {
    throw new ValidationError(t('commands.subscription.login.emptyToken'));
  }
  return token;
}

/** `subscription login --token`: validate the token against the server, check its scope against the current team, store it and report the plan. */
async function loginWithToken(token: string, serverUrl: string): Promise<void> {
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
        overLimitCount?: number;
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

  setSubscriptionTelemetryContext({
    subscriptionId: status.subscriptionId,
    planCode: status.planCode,
    status: status.status,
    source: TELEMETRY_SUBSCRIPTION_SOURCES.storedToken,
  });
  renderLoginSummary(status, status.teamName ?? currentTeamName, serverUrl);
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
        // Read and validate the token FIRST: a refused token (empty stdin, whitespace) must not leave a region prompt or a server rewrite behind it. `--token ""` is a token given and refused, not the device-code flow.
        const token =
          options.token === undefined ? undefined : await resolveLoginToken(String(options.token));

        if (options.server) {
          await persistExplicitServer(options.server);
        } else {
          await promptRegionIfNeeded();
        }

        const serverUrl = await resolveAndSyncServer(options);

        if (token === undefined) {
          const { status } = await authorizeSubscriptionViaDeviceCode(serverUrl, {
            interactive: true,
            teamName: await configService.getTeam(),
          });
          setSubscriptionTelemetryContext({
            subscriptionId: status.subscriptionId,
            planCode: status.planCode,
            source: TELEMETRY_SUBSCRIPTION_SOURCES.storedToken,
          });
          renderLoginSummary(status, status.teamName, serverUrl);
        } else {
          await loginWithToken(token, serverUrl);
        }
      } catch (error) {
        handleError(error);
      }
    });

  // subscription logout
  sub
    .command('logout')
    .description(t('commands.subscription.logout.description'))
    .action(async () => {
      try {
        deleteStoredSubscriptionToken();
        // Also clear the active config's server identity, on THIS device only (the login fields are device-local), so the next `login` asks again: for a region on a local config, while a remote config falls back to its store's server (readAccountPointer). updateChannel and releasesUrl (update preferences, not server identity) survive.
        const configName = getEffectiveConfigName();
        for (const field of LOGIN_FIELDS) {
          try {
            await updateConfigAtPointer(configName, `/account/${field}`, (cfg) => {
              if (!cfg.account) return cfg;
              const account = { ...cfg.account };
              delete account[field];
              return { ...cfg, account };
            });
          } catch {
            /* config might not exist */
          }
        }
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
  // A PLAIN LEAF: it carries an .action() and MUST NOT grow subcommands. It used to be an actionable parent (an .action() plus `activation`/`repos`/`repo` children) with a .requiredOption('-m'), and Commander walks the parent chain in _checkForMissingMandatoryOptions(), so that required flag fired for every child too and bound to the parent even when typed after the subcommand.
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
