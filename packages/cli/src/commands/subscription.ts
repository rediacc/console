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
import {
  authorizeSubscriptionViaDeviceCode,
  type ClaimTerms,
} from '../services/account/subscription-device-auth.js';
import {
  loginWithPassword,
  resolvePasswordLoginInput,
  wantsPasswordLogin,
} from '../services/account/subscription-password-auth.js';
import { getEffectiveConfigName } from '../services/config/config-name.js';
import { configService } from '../services/config/config-resources.js';
import { updateConfigAtPointer } from '../services/config/synced-write.js';
import { outputService } from '../services/core/output.js';
import { discoverRegions } from '../services/provision/region-discovery.js';
import { telemetryService } from '../services/telemetry/telemetry.js';
import { handleError, setOutputFormat, ValidationError } from '../utils/errors.js';
import { promptRegionSelection } from '../utils/region-prompt.js';
import { withSpinner } from '../utils/spinner.js';
import { readStdinValue } from '../utils/stdin.js';
import {
  executeMachineStatus,
  executeSubscriptionRefresh,
  executeSubscriptionStatus,
} from './subscription-actions.js';
import { executeSubscriptionNotices } from './subscription-notices.js';
import { outputSubscriptionScope } from './subscription-output.js';
import { executeProxyToken } from './subscription-proxy-token.js';
import { executeSubscriptionRetire } from './subscription-retire.js';

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
 * `cfg` with `account[field]` set. A new `accountServer` drops the saved `e2ePublicKey` in the same
 * write: a key belongs to the server it was fetched from, and getServerKeyMaterial trusts the saved
 * key only for the saved server, so the old server's key must not survive under the new one.
 */
function withAccountField<C extends { account?: Record<string, unknown> }>(
  cfg: C,
  field: AccountField,
  value: string
): C {
  const account: Record<string, unknown> = { ...(cfg.account ?? {}), [field]: value };
  const previous = cfg.account?.accountServer;
  if (
    field === 'accountServer' &&
    typeof previous === 'string' &&
    normalizeServerUrl(previous) !== normalizeServerUrl(value)
  ) {
    delete account.e2ePublicKey;
  }
  return { ...cfg, account };
}

/** The active config's name, or undefined (with a warning when a channel write is lost) when it does not exist yet. */
async function existingActiveConfigName(
  fields: Partial<Record<AccountField, string>>
): Promise<string | undefined> {
  const configName = getEffectiveConfigName();
  if (await configFileStorage.exists(configName)) return configName;
  if (fields.updateChannel !== undefined) {
    outputService.warn(`update channel not saved: config "${configName}" does not exist yet`);
  }
  return undefined;
}

/**
 * Write account fields into the active config. A config that does not exist yet is skipped; any
 * other write failure throws, because a lost `e2ePublicKey` leaves every later request to discover
 * the key again, and to refuse when the server cannot answer (2026-10-21). Each field is
 * routed by its pointer: the login fields stay on this device, `updateChannel` syncs, and is
 * written only when it changes, so a login does not push an unchanged channel.
 */
async function patchActiveAccount(fields: Partial<Record<AccountField, string>>): Promise<boolean> {
  const configName = await existingActiveConfigName(fields);
  if (configName === undefined) return false;
  let saved = true;
  for (const [field, value] of Object.entries(fields) as [AccountField, string | undefined][]) {
    if (value === undefined) continue;
    if (field === 'updateChannel' && readAccountPointer(configName).updateChannel === value)
      continue;
    const write = updateConfigAtPointer(configName, `/account/${field}`, (cfg) =>
      withAccountField(cfg, field, value)
    );
    if (field !== 'updateChannel') {
      await write;
      continue;
    }
    // The channel is a synced preference, not a login field: a remote config that cannot take the
    // write right now keeps its old channel rather than failing the login.
    await write.catch((error: unknown) => {
      saved = false;
      outputService.warn(
        `update channel not saved: ${error instanceof Error ? error.message : String(error)}`
      );
    });
  }
  return saved;
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
 * Resolve the account server URL and sync the e2e key from server-info into the active config. The
 * update channel is NOT written here: the returned `applyChannel` writes it, and the caller picks
 * the moment. A synced channel write of a remote config pulls the store with the stored login
 * token, which an IP change has turned into the "enter the 6-digit code" prompt; a fresh login
 * must not run that prompt, so `subscription login` and `register` call `applyChannel` only after
 * the new token is stored.
 */
async function resolveServerDeferringChannel(options: {
  server?: string;
}): Promise<{ serverUrl: string; applyChannel: () => Promise<void> }> {
  // Resolve the server URL from --server / env / active config / default.
  const serverUrl = getSubscriptionServerUrl(options.server);

  // Pin the resolved server into the active config for per-config isolation.
  await patchActiveAccount({ accountServer: serverUrl });

  // Only the fetch is non-fatal: a server-info that cannot be read leaves the existing config, but one that was read and then could not be persisted is an error, never a silent fall back to the production key.
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
    await patchActiveAccount({ e2ePublicKey: info.e2e?.keys?.[0]?.publicKeySpki });
  }
  const channel = info?.updateChannel;
  const applyChannel = async (): Promise<void> => {
    if (!channel) return;
    // One write, one announcement: the line says "set" only when the write landed.
    if (await patchActiveAccount({ updateChannel: channel })) {
      outputService.info(t('commands.subscription.login.channelSynced', { channel }));
    }
  };
  return { serverUrl, applyChannel };
}

/**
 * Resolve the account server URL and auto-sync update channel + e2e key from server-info into the
 * active config. Returns the resolved server URL for use in subsequent requests.
 */
export async function resolveAndSyncServer(options: { server?: string }): Promise<string> {
  const { serverUrl, applyChannel } = await resolveServerDeferringChannel(options);
  await applyChannel();
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

/** The one terms line of the login summary: accepted, pending with an accept URL, or pending. */
function termsSummaryLine(terms: ClaimTerms): string {
  if (terms.accepted) {
    return t('commands.subscription.login.termsAccepted', { version: terms.accepted });
  }
  if (terms.acceptUrl) {
    return t('commands.subscription.login.termsPendingAccept', {
      url: terms.url,
      acceptUrl: terms.acceptUrl,
    });
  }
  return t('commands.subscription.login.termsPending', { url: terms.url });
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
  serverUrl: string,
  terms?: ClaimTerms
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
  if (terms) {
    outputService.info(termsSummaryLine(terms));
  }
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

/** Headless login input: REDIACC_LOGIN_EMAIL + REDIACC_LOGIN_PASSWORD (or --password-stdin). Read before any prompt or server rewrite so a refusal leaves nothing behind. */
function readPasswordLoginInput(options: {
  token?: string;
  passwordStdin?: boolean;
}): Promise<Awaited<ReturnType<typeof resolvePasswordLoginInput>> | undefined> {
  const stdin = Boolean(options.passwordStdin);
  if (options.token !== undefined && stdin) {
    return Promise.reject(new ValidationError(t('commands.subscription.login.tokenAndPassword')));
  }
  if (options.token !== undefined || !wantsPasswordLogin(stdin)) return Promise.resolve(undefined);
  return resolvePasswordLoginInput(stdin);
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
    .option('--password-stdin', t('commands.subscription.login.optionPasswordStdin'))
    .option('--server <url>', t('options.serverUrl'))
    .action(async (options) => {
      try {
        const passwordLogin = await readPasswordLoginInput(options);
        // Read and validate the token FIRST: a refused token (empty stdin, whitespace) must not leave a region prompt or a server rewrite behind it. `--token ""` is a token given and refused, not the device-code flow.
        let token =
          options.token === undefined ? undefined : await resolveLoginToken(String(options.token));

        if (options.server) {
          await persistExplicitServer(options.server);
        } else {
          await promptRegionIfNeeded();
        }

        const { serverUrl, applyChannel } = await resolveServerDeferringChannel(options);

        if (passwordLogin) {
          token = await withSpinner(
            t('commands.subscription.login.passwordSigningIn'),
            () => loginWithPassword(serverUrl, passwordLogin),
            t('commands.subscription.login.passwordSignedIn')
          );
        }

        if (token === undefined) {
          const { status, terms } = await authorizeSubscriptionViaDeviceCode(serverUrl, {
            interactive: true,
            teamName: await configService.getTeam(),
          });
          setSubscriptionTelemetryContext({
            subscriptionId: status.subscriptionId,
            planCode: status.planCode,
            source: TELEMETRY_SUBSCRIPTION_SOURCES.storedToken,
          });
          renderLoginSummary(status, status.teamName, serverUrl, terms);
        } else {
          await loginWithToken(token, serverUrl);
        }
        await applyChannel();
      } catch (error) {
        handleError(error);
      }
    });

  // subscription register --email <addr>
  sub
    .command('register')
    .description(t('commands.subscription.register.description'))
    .requiredOption('--email <address>', t('commands.subscription.register.optionEmail'))
    .option('--server <url>', t('options.serverUrl'))
    .action(async (options) => {
      try {
        const email = String(options.email).trim();
        if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
          throw new ValidationError(t('commands.subscription.register.invalidEmail'));
        }
        if (options.server) {
          await persistExplicitServer(options.server);
        } else {
          await promptRegionIfNeeded();
        }
        const { serverUrl, applyChannel } = await resolveServerDeferringChannel(options);
        const { status, terms } = await authorizeSubscriptionViaDeviceCode(serverUrl, {
          interactive: true,
          teamName: await configService.getTeam(),
          email,
        });
        setSubscriptionTelemetryContext({
          subscriptionId: status.subscriptionId,
          planCode: status.planCode,
          source: TELEMETRY_SUBSCRIPTION_SOURCES.storedToken,
        });
        renderLoginSummary(status, status.teamName, serverUrl, terms);
        await applyChannel();
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

  // subscription proxy-token [--json]
  // Mints a short-lived proxy:exec token from this device's login, for `rdc --proxy`. Stdout carries
  // only the token (with --json, the token and its expiresAt), so `$(...)` captures it whole.
  sub
    .command('proxy-token')
    .description(t('commands.subscription.proxyToken.description'))
    .option('--json', t('commands.subscription.proxyToken.jsonOption'))
    .action(async (options: { json?: boolean }) => {
      // Inside `$(...)` stdout is no TTY, so the root hook picks JSON output, and a JSON error envelope lands on stdout where the substitution captures it as a "token". The refusal goes to stderr as text instead, whatever the format.
      setOutputFormat('table');
      try {
        await executeProxyToken(options);
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

  // subscription notices [--all] [--unread] [--mark-read]
  sub
    .command('notices')
    .description(t('commands.subscription.notices.description'))
    .option('--all', t('commands.subscription.notices.optionAll'))
    .option('--unread', t('commands.subscription.notices.optionUnread'))
    .option('--mark-read', t('commands.subscription.notices.optionMarkRead'))
    .action(async (options) => {
      try {
        await executeSubscriptionNotices(options);
      } catch (error) {
        handleError(error);
      }
    });

  // subscription retire <guid> [--force]; -y/--yes is the global option.
  sub
    .command('retire')
    .description(t('commands.subscription.retire.description'))
    .argument('<guid>', t('commands.subscription.retire.argGuid'))
    .option('--force', t('commands.subscription.retire.optionForce'))
    .action(async (guid: string, options) => {
      try {
        await executeSubscriptionRetire(guid, options);
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
    .option('--adopt-origin', t('commands.subscription.refresh.adoptOrigin'))
    .action(async (options) => {
      try {
        await executeSubscriptionRefresh(options);
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
