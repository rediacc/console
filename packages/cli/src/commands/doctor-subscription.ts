/**
 * The subscription section of `rdc doctor`: license status, machine slots and repo licenses read
 * from the account server. The command is registered in doctor.ts.
 */

import { WK_SITE_ORIGIN } from '@rediacc/shared/config/well-known.generated';
import { isSubscriptionActive, type SubscriptionStatus } from '@rediacc/shared/subscription';
import { t } from '../i18n/index.js';
import { fetchSubscriptionLicenseReport } from '../services/account/license.js';
import { getSubscriptionTokenState } from '../services/account/subscription-auth.js';
import type { CheckResult, CheckSection, CheckStatus } from './doctor.js';

const SUBSCRIPTION_CHECK_TIMEOUT_MS = 8000;
const TIMEOUT_SENTINEL = Symbol('timeout');
type LicenseReport = Awaited<ReturnType<typeof fetchSubscriptionLicenseReport>> & object;

function getInactiveStatusHint(status: string): string {
  if (status === 'EXPIRED') return `Subscription expired. Renew at ${WK_SITE_ORIGIN}/account`;
  if (status === 'SUSPENDED') return 'Subscription suspended. Contact support or check billing';
  return `Subscription inactive. Activate at ${WK_SITE_ORIGIN}/account`;
}

function checkSubscriptionStatus(checks: CheckResult[], report: LicenseReport): void {
  const status = report.status as SubscriptionStatus;
  if (!isSubscriptionActive(status)) {
    checks.push({
      name: t('commands.doctor.checks.subscriptionStatus'),
      value: `${report.planCode} (${report.status})`,
      status: 'fail',
      hint: getInactiveStatusHint(report.status),
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
    hint = 'All machine slots used. Upgrade plan or deactivate unused machines';
  } else if (max > 0 && active >= max * 0.8) {
    status = 'warn';
    hint = 'Machine slots nearly full. Upgrade plan or deactivate unused machines';
  }
  checks.push({ name: t('commands.doctor.checks.subscriptionMachineSlots'), value, status, hint });
}

function checkRepoLicenses(checks: CheckResult[], report: LicenseReport): void {
  const { totalTrackedRepos, validCount, refreshRecommendedCount, hardExpiredCount } =
    report.repoLicenses;
  const name = t('commands.doctor.checks.subscriptionRepoLicenses');
  let value: string, status: CheckStatus, hint: string | undefined;
  if (totalTrackedRepos === 0) {
    value = 'no tracked repos';
    status = 'ok';
  } else if (hardExpiredCount > 0) {
    value = `${validCount} valid, ${refreshRecommendedCount} need refresh, ${hardExpiredCount} expired`;
    status = 'fail';
    hint = 'Run: rdc subscription refresh -m <machine> to fix expired repo licenses';
  } else if (refreshRecommendedCount > 0) {
    value = `${validCount} valid, ${refreshRecommendedCount} need refresh`;
    status = 'warn';
    hint = 'Run: rdc subscription refresh -m <machine> to refresh repo licenses';
  } else {
    value = `${validCount}/${totalTrackedRepos} valid`;
    status = 'ok';
  }
  checks.push({ name, value, status, hint });
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
  checkRepoLicenses(checks, result);

  return { title: t('commands.doctor.sections.subscription'), checks };
}
