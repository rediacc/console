/**
 * The subscription section of `rdc doctor`: license status, machine slots and repo licenses read
 * from the account server. The command is registered in doctor.ts.
 */

import { WK_SITE_ORIGIN } from '@rediacc/shared/config/well-known.generated';
import type { RepoNameEntry } from '@rediacc/shared/config-schema';
import { isSubscriptionActive, type SubscriptionStatus } from '@rediacc/shared/subscription';
import { t } from '../i18n/index.js';
import { fetchSubscriptionLicenseReport } from '../services/account/license.js';
import { renewalOrigin } from '../services/account/license-batch.js';
import { DEFAULT_DATASTORE, scanRemoteRepoLicenses } from '../services/account/license-machine.js';
import { licenceRows, readRepoNames } from '../services/account/license-retire.js';
import { getSubscriptionTokenState } from '../services/account/subscription-auth.js';
import { expectedAccountServerOrigin } from '../services/backup/backup-store-universe.js';
import { configService } from '../services/config/config-resources.js';
import type { CheckResult, CheckSection, CheckStatus } from './doctor.js';

const SUBSCRIPTION_CHECK_TIMEOUT_MS = 8000;
const TIMEOUT_SENTINEL = Symbol('timeout');
type LicenseReport = Awaited<ReturnType<typeof fetchSubscriptionLicenseReport>> & object;

function getInactiveStatusHint(status: string): string {
  if (status === 'EXPIRED') return `Subscription expired. Renew at ${WK_SITE_ORIGIN}/account`;
  if (status === 'SUSPENDED') return 'Subscription suspended. Contact the account owner or Rediacc';
  return `Subscription inactive. Activate at ${WK_SITE_ORIGIN}/account`;
}

function checkSubscriptionStatus(checks: CheckResult[], report: LicenseReport): void {
  // The report can carry the status in either case (the account server answers `active`); the shared predicates compare the upper-case enum.
  const status = String(report.status ?? '').toUpperCase() as SubscriptionStatus;
  if (!isSubscriptionActive(status)) {
    checks.push({
      name: t('commands.doctor.checks.subscriptionStatus'),
      value: `${report.planCode} (${status})`,
      status: 'fail',
      hint: getInactiveStatusHint(status),
    });
    return;
  }
  if (status === 'GRACE') {
    checks.push({
      name: t('commands.doctor.checks.subscriptionStatus'),
      value: `${report.planCode} (GRACE)`,
      status: 'warn',
      hint: `Subscription is in grace period. Renew at ${WK_SITE_ORIGIN}/account`,
    });
  } else {
    checks.push({
      name: t('commands.doctor.checks.subscriptionStatus'),
      value: `${report.planCode} (ACTIVE)`,
      status: 'ok',
    });
  }
}

function checkMachineSlots(checks: CheckResult[], report: LicenseReport): void {
  const { active, max } = report.machineSlots;
  const value = `${active}/${max}`;
  let status: CheckStatus = 'ok';
  let hint: string | undefined;
  if (active >= max && max > 0) {
    status = 'fail';
    hint =
      'All machine slots used. Ask the account owner or Rediacc to raise the plan, or deactivate unused machines';
  } else if (max > 0 && active >= max * 0.8) {
    status = 'warn';
    hint =
      'Machine slots nearly full. Ask the account owner or Rediacc to raise the plan, or deactivate unused machines';
  }
  checks.push({
    name: t('commands.doctor.checks.subscriptionMachineSlots'),
    value,
    status,
    hint,
  });
}

const REFRESH_HINT = 'rdc subscription refresh -m <machine>';
const RETIRE_HINT = 'rdc subscription retire --expired (lists them; --apply retires)';

type LiveRow = { guid: string; machine: string | null };

/** The hard-expired licences of repositories this config holds; null when the report lists no licence. */
function liveExpiredRows(report: LicenseReport, names: Map<string, RepoNameEntry>): LiveRow[] | null {
  const recent = report.repoLicenses.recent ?? [];
  if (recent.length === 0) return null;
  return licenceRows(recent, names).filter(
    (row) => row.freshness === 'hard_expired' && row.presence === 'config'
  );
}

/**
 * The issuing origin of each expired licence that another account server issued. The report does not carry it: it is
 * the origin of the installed blob's `renewalUrl`, which only the machine's `license-scan` shows (the refresh path
 * reads it the same way, through `renewalOrigin`). A machine that cannot be scanned leaves its licences counted as
 * this server's.
 */
async function foreignIssuers(rows: LiveRow[]): Promise<Map<string, string>> {
  const expected = expectedAccountServerOrigin();
  const foreign = new Map<string, string>();
  if (!expected) return foreign;
  const byMachine = new Map<string, Set<string>>();
  for (const row of rows) {
    if (!row.machine) continue;
    byMachine.set(row.machine, (byMachine.get(row.machine) ?? new Set()).add(row.guid));
  }
  for (const [machine, guids] of byMachine) {
    try {
      const datastore = await configService
        .getLocalMachine(machine)
        .then((m) => m.datastore ?? DEFAULT_DATASTORE)
        .catch(() => DEFAULT_DATASTORE);
      const scanned = await scanRemoteRepoLicenses(machine, datastore);
      for (const guid of guids) {
        const origins = scanned
          .filter((entry) => entry.repositoryGuid === guid && entry.currentRenewalUrl)
          .map((entry) => renewalOrigin(entry.currentRenewalUrl as string));
        if (origins.length > 0 && origins.every((origin) => origin !== expected)) {
          foreign.set(guid, origins[0]);
        }
      }
    } catch {
      // An unreadable machine leaves its licences counted as this server's.
    }
  }
  return foreign;
}

/**
 * The repo-licence row. A hard-expired licence of a repository this config holds fails: that repository needs a
 * refresh. One of a repository that is gone (deleted, or never in this config) only warns, and the hint names the
 * one command that clears it from the account's counts: `subscription refresh` re-issues licences of repositories
 * on a machine and never touches a deleted one. A licence another account server issued is never counted here: that
 * server keeps it alive, and an info row names it.
 */
function checkRepoLicenses(
  checks: CheckResult[],
  report: LicenseReport,
  rows: LiveRow[] | null,
  foreign: Map<string, string>
): void {
  const { totalTrackedRepos, validCount, refreshRecommendedCount, hardExpiredCount } =
    report.repoLicenses;
  const name = t('commands.doctor.checks.subscriptionRepoLicenses');
  const expiredHere = hardExpiredCount - foreign.size;
  let value: string, status: CheckStatus, hint: string | undefined;
  if (totalTrackedRepos === 0) {
    value = 'no tracked repos';
    status = 'ok';
  } else if (expiredHere > 0) {
    const live = rows === null ? null : rows.filter((row) => !foreign.has(row.guid)).length;
    value = `${validCount} valid, ${refreshRecommendedCount} need refresh, ${expiredHere} expired`;
    if (live === 0) {
      value += ` (none in this config)`;
      status = 'warn';
      hint = `Run: ${RETIRE_HINT} to retire the expired licenses of deleted repositories`;
    } else {
      if (live !== null) value += ` (${live} in this config)`;
      status = 'fail';
      hint = `Run: ${REFRESH_HINT} for repositories still on a machine, and ${RETIRE_HINT} for deleted ones`;
    }
  } else if (refreshRecommendedCount > 0) {
    value = `${validCount} valid, ${refreshRecommendedCount} need refresh`;
    status = 'warn';
    hint = `Run: ${REFRESH_HINT} to refresh repo licenses`;
  } else {
    value = `${validCount}/${totalTrackedRepos} valid`;
    status = 'ok';
  }
  checks.push({ name, value, status, hint });
  if (foreign.size > 0) {
    const origins = [...new Set(foreign.values())].join(', ');
    checks.push({
      name,
      value: `info: ${foreign.size} expired, issued by another account server (${origins}), not counted`,
      status: 'ok',
      hint: 'That server keeps them alive. `rdc subscription refresh -m <machine> --adopt-origin` moves them to this config deliberately',
    });
  }
}

/** The active config's GUID-to-name join; an unreadable config knows no names, so every licence reads as not in it. */
async function readNamesForDoctor(): Promise<Map<string, RepoNameEntry>> {
  try {
    return await readRepoNames();
  } catch {
    return new Map();
  }
}

export async function checkSubscription(): Promise<CheckSection> {
  const checks: CheckResult[] = [];
  const tokenState = getSubscriptionTokenState();

  if (tokenState.kind === 'missing') {
    checks.push({
      name: t('commands.doctor.checks.subscriptionToken'),
      value: t('commands.doctor.notLoggedIn'),
      status: 'warn',
      hint: 'Run: rdc subscription login',
    });
    return { title: t('commands.doctor.sections.subscription'), checks };
  }

  const { token } = tokenState;
  const scopeParts = [token.orgName, token.teamName].filter(Boolean).join(' / ');
  checks.push({
    name: t('commands.doctor.checks.subscriptionToken'),
    value: scopeParts ? `authenticated (${scopeParts})` : 'authenticated',
    status: 'ok',
  });

  const result = await Promise.race([
    fetchSubscriptionLicenseReport(),
    new Promise<typeof TIMEOUT_SENTINEL>((resolve) =>
      setTimeout(() => resolve(TIMEOUT_SENTINEL), SUBSCRIPTION_CHECK_TIMEOUT_MS)
    ),
  ]);

  if (!result || result === TIMEOUT_SENTINEL) {
    const hint =
      result === TIMEOUT_SENTINEL
        ? 'Subscription server did not respond in time. Check network connectivity'
        : 'Check network connectivity or try again later';
    checks.push({
      name: t('commands.doctor.checks.subscriptionStatus'),
      value: t('commands.doctor.subscriptionUnreachable'),
      status: 'warn',
      hint,
    });
    return { title: t('commands.doctor.sections.subscription'), checks };
  }

  checkSubscriptionStatus(checks, result);
  checkMachineSlots(checks, result);
  const rows = liveExpiredRows(result, await readNamesForDoctor());
  const foreign = await foreignIssuers(rows ?? []);
  checkRepoLicenses(checks, result, rows, foreign);

  return { title: t('commands.doctor.sections.subscription'), checks };
}
