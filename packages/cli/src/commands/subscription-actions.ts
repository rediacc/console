/**
 * Subscription execution logic: the account view, the machine license view, and
 * the three refresh scopes (account, machine, single repo).
 *
 * Extracted from subscription.ts to stay within max-lines. The command file
 * registers four flat leaves (login, logout, status, refresh); the scope of a
 * status or a refresh is chosen here by which function the leaf dispatches to.
 */

import { t } from '../i18n/index.js';
import { renewInstalledLicenses } from '../services/account/free-license.js';
import {
  fetchSubscriptionLicenseReportOrThrow,
  type RepoBatchRefreshResult,
  type RuntimeRepoLicenseStatus,
  readMachineActivationStatus,
  refreshRepoLicenseIdentity,
  refreshRepoLicensesBatch,
} from '../services/account/license.js';
import { DEFAULT_DATASTORE } from '../services/account/license-machine.js';
import type { RemoteRepoLicenseScanEntry } from '../services/account/license-types.js';
import {
  getSubscriptionScopeMismatch,
  getSubscriptionServerUrl,
  getSubscriptionTokenState,
  type SubscriptionTokenState,
} from '../services/account/subscription-auth.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import { setExitCode } from '../services/core/request-context.js';
import { pendingExitCode, runCommandJob } from '../services/jobs/command-job.js';
import { bindStepHandler, planStep } from '../services/jobs/steps.js';
import {
  acquireRemoteRenet,
  type RenetAccess,
  readSSHKey,
} from '../services/renet/renet-execution.js';
import { getOutputFormat, ValidationError } from '../utils/errors.js';
import { recordedDatastoreMount } from '../utils/repo-executor.js';
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

type UnreadyTokenState = Exclude<SubscriptionTokenState, { kind: 'ready' }>;

/**
 * Each non-ready token kind's diagnostic: prints the kind's context line and returns the kind's message. The Record is keyed by every non-ready kind, so a new SubscriptionTokenState kind fails tsc here until it has its own entry.
 */
const UNREADY_TOKEN_DIAGNOSTICS: Record<UnreadyTokenState['kind'], () => string> = {
  missing: () => {
    outputService.info(
      t('commands.subscription.status.serverWouldUse', { server: getSubscriptionServerUrl() })
    );
    return t('errors.subscription.notLoggedIn');
  },
};

/**
 * The one diagnostic for a token that is not ready, which a failing verb throws and the best-effort activation section prints (review 8b3374e0.1: the status verb had bypassed it, so every non-ready kind read as "not logged in").
 * A kind with no entry is a programming error, never reported as "not logged in".
 */
function unreadyTokenDiagnostic(tokenState: UnreadyTokenState): string {
  const diagnostic = Object.hasOwn(UNREADY_TOKEN_DIAGNOSTICS, tokenState.kind)
    ? UNREADY_TOKEN_DIAGNOSTICS[tokenState.kind]
    : undefined;
  if (!diagnostic) {
    throw new Error(`Unhandled subscription token state: ${JSON.stringify(tokenState)}`);
  }
  return diagnostic();
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
async function resolveMachineContext(
  machineName: string,
  access: RenetAccess
): Promise<SubscriptionCommandContext> {
  const localConfig = await configService.getLocalConfig();
  const machine = await configService.getLocalMachine(machineName);
  const sshPrivateKey =
    localConfig.sshPrivateKey ?? (await readSSHKey(localConfig.ssh.privateKeyPath));
  const { remotePath: remoteRenetPath } = await acquireRemoteRenet(
    access,
    localConfig,
    machine,
    sshPrivateKey,
    { skipRouterRestart: true, machineName }
  );
  return { machine, sshPrivateKey, remoteRenetPath };
}

/** The token-gated form, for the refresh paths that must reach the account server. */
async function resolveSubscriptionCommandContext(
  machineName: string
): Promise<SubscriptionCommandContext> {
  const tokenState = getSubscriptionTokenState();
  if (tokenState.kind !== 'ready') {
    throw new ValidationError(unreadyTokenDiagnostic(tokenState));
  }
  await assertSubscriptionScopeMatchesConfig(tokenState.token);
  // Refresh writes licenses on the machine, so it may bring renet up to date first.
  return resolveMachineContext(machineName, 'provision');
}

/**
 * `subscription status` with no `-m`: the account view. No token is a failure, not a status:
 * the verb exited 0 printing "Not logged in" (empty stdout under `-o json`), so automation read
 * an absent token as a valid one, and the next `repo create` refused with tokenRequired (vm:check P4, 2026-10-15).
 */
export async function executeSubscriptionStatus(): Promise<void> {
  const tokenState = getSubscriptionTokenState();
  if (tokenState.kind !== 'ready') {
    throw new ValidationError(unreadyTokenDiagnostic(tokenState));
  }
  await assertSubscriptionScopeMatchesConfig(tokenState.token);

  // No local-only view exists: outputRemoteStatus IS this verb's entire output, so a failed report must surface the server's reason, not exit 0 in silence.
  const status = await fetchSubscriptionLicenseReportOrThrow();
  if (!status) {
    throw new ValidationError(t('errors.subscription.notLoggedIn'));
  }
  const configGuids = await readConfigRepoGuids();
  const format = getOutputFormat();
  if (format !== 'table') {
    outputService.print(subscriptionStatusData(status, configGuids), format);
    return;
  }
  outputRemoteStatus(status, configGuids);
}

/** The structured form of the account view, for `-o json|yaml|csv`: the same facts the table prints. */
function subscriptionStatusData(
  status: NonNullable<Awaited<ReturnType<typeof fetchSubscriptionLicenseReportOrThrow>>>,
  configGuids?: Set<string>
): Record<string, unknown> {
  const recent = status.repoLicenses.recent;
  return {
    organization: status.orgName ?? null,
    team: status.teamName ?? null,
    plan: status.planCode,
    status: status.status,
    machineSlots: status.machineSlots,
    repoLicenseIssuances: status.repoLicenseIssuances,
    repoLicenses:
      recent && configGuids
        ? { ...splitRepoLicensesByConfig(recent, configGuids), scope: 'config' }
        : { ...status.repoLicenses, scope: 'account' },
    overLimitCount: status.machineSlots.machines.filter((m) => m.overLimit).length,
  };
}

/** The repository GUIDs this config holds, or undefined when the config cannot be read. */
async function readConfigRepoGuids(): Promise<Set<string> | undefined> {
  try {
    const repos = await configService.listRepositories();
    return new Set(repos.map((r) => r.config.repositoryGuid).filter((g): g is string => !!g));
  } catch {
    return undefined;
  }
}

type TrackedRepo = { repositoryGuid: string; freshness: string };

/** Split the server's tracked repositories by membership in this config's GUIDs. */
export function splitRepoLicensesByConfig(recent: TrackedRepo[], configGuids: Set<string>) {
  const inConfig = recent.filter((r) => configGuids.has(r.repositoryGuid));
  return {
    totalTrackedRepos: inConfig.length,
    validCount: inConfig.filter((r) => r.freshness === 'valid').length,
    refreshRecommendedCount: inConfig.filter((r) => r.freshness === 'refresh_recommended').length,
    hardExpiredCount: inConfig.filter((r) => r.freshness === 'hard_expired').length,
    notInConfigCount: recent.length - inConfig.length,
  };
}

function outputRepoLicenseCounts(
  repoLicenses: NonNullable<
    Awaited<ReturnType<typeof fetchSubscriptionLicenseReportOrThrow>>
  >['repoLicenses'],
  configGuids?: Set<string>
) {
  const recent = repoLicenses.recent;
  if (recent && configGuids) {
    const split = splitRepoLicensesByConfig(recent, configGuids);
    outputService.info(t('commands.subscription.status.remoteRepoLicensesInConfig', split));
    outputService.info(
      t('commands.subscription.status.remoteRepoLicensesNotInConfig', {
        count: split.notInConfigCount,
      })
    );
  } else {
    outputService.info(
      t('commands.subscription.status.remoteRepoLicenses', {
        totalTrackedRepos: repoLicenses.totalTrackedRepos,
        validCount: repoLicenses.validCount,
        refreshRecommendedCount: repoLicenses.refreshRecommendedCount,
        hardExpiredCount: repoLicenses.hardExpiredCount,
      })
    );
  }
}

function outputRemoteStatus(
  status: Awaited<ReturnType<typeof fetchSubscriptionLicenseReportOrThrow>>,
  configGuids?: Set<string>
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
  outputRepoLicenseCounts(status.repoLicenses, configGuids);
  for (const machine of status.machineSlots.machines) {
    const key = machine.overLimit
      ? 'commands.subscription.status.remoteMachineOverLimit'
      : 'commands.subscription.status.remoteMachine';
    outputService.info(
      t(key, {
        id: machine.machineId.slice(0, 12),
        lastSeen: machine.lastSeenAt,
      })
    );
  }

  // Soft-claim (design decision 2): a renewal never fails for being over the cap, it just flags the row. Nothing else would tell the operator that the fleet has outgrown its plan until the next NEW repository is refused, so the count is called out rather than left to be spotted row by row.
  const overLimitCount = status.machineSlots.machines.filter((m) => m.overLimit).length;
  if (overLimitCount > 0) {
    outputService.warn(
      t('commands.subscription.status.overLimitSummary', { count: overLimitCount })
    );
  }
}

/** The per-repo license table, from the `license-status` job's output (renet's runtime state on the machine). */
function renderRepoLicenseTable(machineName: string, entries: RuntimeRepoLicenseStatus[]): void {
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
      }) +
        (entry.datastoreId
          ? t('commands.subscription.repo.status.datastoreSuffix', {
              datastoreId: entry.datastoreId,
            })
          : '')
    );
    renderLastRenewal(entry);
  }

  renderBlockedBackups(machineName, entries);
}

/**
 * renet's per-blob verdicts (pkg/license/renew.go). `renewed` and the two
 * `skipped_*` values are healthy; the other two mean this repo's licence is no
 * longer being kept alive and will hard-expire on its own schedule.
 */
const FAILED_RENEWAL_OUTCOMES = new Set(['refused', 'error']);

/**
 * The renewal detail line. `code` leads because it is the stable, branchable
 * identity of the failure (SUBSCRIPTION_LAPSED, DELEGATION_CERT_REVOKED, ...)
 * while `message` is display prose the server may reword; showing both means
 * the operator can search for the code and read the sentence.
 */
function renewalDetail(renewal: NonNullable<RuntimeRepoLicenseStatus['lastRenewal']>): string {
  const parts = [renewal.code, renewal.message].filter(Boolean);
  if (parts.length > 0) return ` (${parts.join(': ')})`;
  if (renewal.newSequence) return ` (seq ${renewal.newSequence})`;
  return '';
}

/**
 * What the last unattended renewal did for this repo, when there was one.
 *
 * A refused or errored renewal is rendered as a WARNING, not as another info
 * line. Unattended renewal is the only thing keeping a 7-day fork licence
 * alive, so a repo whose last renewal was refused is on a countdown to a dead
 * licence and, after that, to blocked backups. By the time the marker in
 * renderBlockedBackups appears it has already cost a backup window; this is the
 * same failure caught one step earlier.
 */
function renderLastRenewal(entry: RuntimeRepoLicenseStatus): void {
  const renewal = entry.lastRenewal;
  if (!renewal) return;
  const line = t('commands.subscription.repo.status.lastRenewal', {
    outcome: renewal.outcome,
    detail: renewalDetail(renewal),
  });
  if (FAILED_RENEWAL_OUTCOMES.has(renewal.outcome)) {
    outputService.warn(line);
    return;
  }
  outputService.info(line);
}

/**
 * The blocked-backup markers, rendered LAST and as errors.
 *
 * A marker means renet's backup gate refused a scheduled backup on licensing
 * grounds, and it persists until a renewal clears it. That is the one failure
 * in this table nobody is watching for: the backup timer keeps firing, systemd
 * keeps reporting whatever the unit reports, and the data silently stops being
 * copied. It gets its own block at the bottom, styled as an error, so it cannot
 * be lost in a long list of healthy repos.
 */
function renderBlockedBackups(machineName: string, entries: RuntimeRepoLicenseStatus[]): void {
  const blocked = entries.filter((entry) => entry.blockedBackup);
  if (blocked.length === 0) return;

  for (const entry of blocked) {
    const marker = entry.blockedBackup;
    if (!marker) continue;
    outputService.error(
      t('commands.subscription.repo.status.blockedBackup', {
        repositoryGuid: entry.repositoryGuid,
        at: marker.at,
        reason: marker.reason,
        message: marker.message,
      })
    );
  }
  outputService.error(t('commands.subscription.repo.status.blockedBackupRemedy', { machineName }));
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
  try {
    const tokenState = getSubscriptionTokenState();
    if (tokenState.kind !== 'ready') {
      outputService.info(unreadyTokenDiagnostic(tokenState));
      return;
    }
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

/** A `license-status` / `license-scan` answer: a JSON array. Anything else fails with the job's name, as the awaited probe form did. */
function parseJsonArray<T>(name: string, output: string | undefined): T[] {
  let parsed: unknown;
  try {
    parsed = JSON.parse(output ?? '');
  } catch {
    throw new Error(`renet ${name} returned output that is not JSON`);
  }
  if (!Array.isArray(parsed)) throw new Error(`renet ${name} returned no JSON array`);
  return parsed as T[];
}

/** The failure of a licence job the command ran: the same text the awaited probe form threw. */
function licenseJobFailure(
  name: string,
  machineName: string,
  result: { exitCode: number; stderr?: string; error?: string }
): Error {
  return new Error(
    `renet ${name} failed on ${machineName} (exit ${result.exitCode}): ${result.stderr ?? result.error ?? ''}`.trim()
  );
}

/**
 * `subscription status -m <machine>`: one `license-status` job on the machine. The activation section and the
 * per-repo license table are its `renderSubscriptionStatus` step, so a ticket handed back early prints nothing
 * half-done. The step is best-effort for the activation part, as the section always was.
 */
export async function executeMachineStatus(machineName: string): Promise<void> {
  const machine = await configService.getLocalMachine(machineName);
  const outcome = await runCommandJob(
    'subscription status',
    {
      functionName: 'license-status',
      machineName,
      commandKind: {
        name: 'license-status',
        args: { datastore: machine.datastore ?? DEFAULT_DATASTORE },
      },
      captureOutput: true,
    },
    [planStep('renderSubscriptionStatus', { machine: machineName })]
  );
  if (outcome.kind === 'pending') {
    const code = pendingExitCode(outcome);
    if (code !== undefined) setExitCode(code);
    return;
  }
  if (!outcome.result.success)
    throw licenseJobFailure('license-status', machineName, outcome.result);
}

bindStepHandler('renderSubscriptionStatus', async ({ machine, output }) => {
  const context = await resolveMachineContext(machine, 'read-only');
  // The activation section goes first: an unusable licence answer fails the step after it, not before it.
  await renderActivationSection(machine, context);
  renderRepoLicenseTable(
    machine,
    parseJsonArray<RuntimeRepoLicenseStatus>('license-status', output)
  );
});

function runRepoBatchRefresh(
  machineName: string,
  context: SubscriptionCommandContext,
  scanned: RemoteRepoLicenseScanEntry[]
): Promise<RepoBatchRefreshResult> {
  return withSpinner(
    t('commands.subscription.refresh.repos.refreshing'),
    () =>
      refreshRepoLicensesBatch(
        machineName,
        context.machine,
        context.sshPrivateKey,
        context.remoteRenetPath,
        undefined,
        undefined,
        scanned
      ),
    t('commands.subscription.refresh.repos.refreshed')
  );
}

/** `subscription refresh` with no flags: re-read the account state from the server. */
export async function executeAccountRefresh(): Promise<void> {
  const tokenState = getSubscriptionTokenState();
  if (tokenState.kind !== 'ready') {
    throw new ValidationError(unreadyTokenDiagnostic(tokenState));
  }
  await assertSubscriptionScopeMatchesConfig(tokenState.token);

  const status = await withSpinner(
    t('commands.subscription.refresh.account.refreshing'),
    () => fetchSubscriptionLicenseReportOrThrow(),
    t('commands.subscription.refresh.account.refreshed')
  );
  if (!status) {
    throw new ValidationError(t('commands.subscription.refresh.account.failed'));
  }
  outputRemoteStatus(status);
}

/**
 * `subscription refresh -m <machine>`: reissue every repo license on the machine. The token gate and the renet upload
 * come first, outside the job. The machine read is one `license-scan` job; the account call and the license writes are
 * its `renderSubscriptionRefresh` step, so a ticket handed back early issues nothing.
 */
export async function executeMachineRefresh(machineName: string): Promise<void> {
  // No login: a FREE licence is issued and renewed without one, so the refresh runs renet's blob-authenticated renewal instead of failing on the missing token.
  if (getSubscriptionTokenState().kind === 'missing') {
    await executeTokenFreeMachineRefresh(machineName);
    return;
  }
  const context = await resolveSubscriptionCommandContext(machineName);
  const outcome = await runCommandJob(
    'subscription refresh',
    {
      functionName: 'license-scan',
      machineName,
      commandKind: {
        name: 'license-scan',
        args: { datastore: context.machine.datastore ?? DEFAULT_DATASTORE },
      },
      captureOutput: true,
    },
    [planStep('renderSubscriptionRefresh', { machine: machineName })]
  );
  if (outcome.kind === 'pending') {
    const code = pendingExitCode(outcome);
    if (code !== undefined) setExitCode(code);
    return;
  }
  if (!outcome.result.success) throw licenseJobFailure('license-scan', machineName, outcome.result);
}

/**
 * `subscription refresh -m <machine>` with no login: renet renews each installed blob that is due, the blob itself being the credential (the same renewal `renewWithoutToken` runs for an expired licence). One line per repo. A blob the server will not renew without an account (a paid licence) is reported as needing login, and a run that renewed nothing for that reason still fails with the login message.
 */
async function executeTokenFreeMachineRefresh(machineName: string): Promise<void> {
  const context = await resolveMachineContext(machineName, 'provision');
  const { results } = await withSpinner(
    t('commands.subscription.refresh.noLogin.renewing'),
    () =>
      renewInstalledLicenses(context.machine, context.sshPrivateKey, {
        remoteRenetPath: context.remoteRenetPath,
      }),
    t('commands.subscription.refresh.noLogin.renewed')
  );
  if (results.length === 0) {
    outputService.info(t('commands.subscription.refresh.noLogin.none'));
    return;
  }
  const tally = { handled: 0, needsLogin: 0, failed: 0 };
  for (const r of results) reportTokenFreeRenewal(r, tally);
  if (tally.needsLogin > 0) outputService.info(t('commands.subscription.refresh.noLogin.paidNote'));
  if (tally.failed > 0) {
    throw new ValidationError(
      t('commands.subscription.refresh.noLogin.failed', { count: tally.failed })
    );
  }
  if (tally.handled === 0) throw new ValidationError(t('errors.subscription.notLoggedIn'));
}

/** One repo's line of the token-free refresh, counted into `tally`. */
function reportTokenFreeRenewal(
  r: { repositoryGuid: string; outcome: string; code?: string; message?: string },
  tally: { handled: number; needsLogin: number; failed: number }
): void {
  const repositoryGuid = r.repositoryGuid;
  const detail = [r.code, r.message].filter(Boolean).join(': ') || r.outcome;
  if (r.outcome === 'renewed') {
    tally.handled++;
    outputService.info(t('commands.subscription.refresh.noLogin.repoRenewed', { repositoryGuid }));
  } else if (r.outcome === 'skipped_fresh') {
    tally.handled++;
    outputService.info(t('commands.subscription.refresh.noLogin.repoNotDue', { repositoryGuid }));
  } else if (r.outcome === 'refused') {
    // The server answered 4xx for the blob alone: a licence that needs an account.
    tally.needsLogin++;
    outputService.warn(
      t('commands.subscription.refresh.noLogin.repoNeedsLogin', { repositoryGuid, detail })
    );
  } else {
    // A transport or server failure, or a blob renet cannot renew: a login would not change it.
    tally.failed++;
    outputService.warn(
      t('commands.subscription.refresh.noLogin.repoFailed', { repositoryGuid, detail })
    );
  }
}

bindStepHandler('renderSubscriptionRefresh', async ({ machine, output }) => {
  const context = await resolveSubscriptionCommandContext(machine);
  const batchSummary = await runRepoBatchRefresh(
    machine,
    context,
    parseJsonArray<RemoteRepoLicenseScanEntry>('license-scan', output)
  );
  outputService.success(t('commands.subscription.refresh.success'));
  renderRepoBatchRefreshSummary(batchSummary);
});

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

      // #74: declare the datastore the repo is RECORDED on. This is the only caller that passes no requestedSizeGb, so it is the one that reaches the size probe, and without this it measured the machine's default datastore for a repo that lives on a named one, found nothing, and
      // reissued at the 1 GB floor. Undefined for a {machine} placement, which
      // correctly leaves the machine's own default in place.
      const datastoreMount = await recordedDatastoreMount(repoKey);

      const refreshed = await refreshRepoLicenseIdentity(machineName, machine, sshPrivateKey, {
        repositoryGuid: repoConfig.repositoryGuid,
        grandGuid: repoConfig.grandGuid,
        kind:
          repoConfig.grandGuid && repoConfig.grandGuid !== repoConfig.repositoryGuid
            ? 'fork'
            : 'grand',
        ...(datastoreMount !== undefined && { datastoreMount }),
      });
      if (!refreshed) {
        throw new ValidationError(t('commands.subscription.refresh.repo.failed'));
      }
    },
    t('commands.subscription.refresh.repo.refreshed')
  );

  outputService.success(t('commands.subscription.refresh.repo.success', { repoName: repoKey }));
}
