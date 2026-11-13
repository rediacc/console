/**
 * `subscription retire <guid>`: retire the license of a repository that is gone, so it leaves the
 * license counts and the notices. Retirement is sticky (a renewal does not bring the repository
 * back), so a repository the config still holds is refused unless its license is hard-expired or
 * `--force` is given.
 */

import { t } from '../i18n/index.js';
import { fetchSubscriptionLicenseReportOrThrow } from '../services/account/license.js';
import {
  expiredRetireTargets,
  LICENCE_STATE_KEYS,
  type LicenceRow,
  licenceDisplayName,
  licenceRows,
  readRepoNames,
  retireRepoLicense,
} from '../services/account/license-retire.js';
import { getSubscriptionTokenState } from '../services/account/subscription-auth.js';
import { outputService } from '../services/core/output.js';
import { setExitCode } from '../services/core/request-context.js';
import { getOutputFormat, ValidationError } from '../utils/errors.js';
import { askConfirm } from '../utils/prompt.js';
import {
  assertSubscriptionScopeMatchesConfig,
  unreadyTokenDiagnostic,
} from './subscription-actions.js';
import { printOtherLicences } from './subscription-status-view.js';

/** A GUID prefix shorter than this matches too many licenses to name one. */
const MIN_GUID_PREFIX = 8;

export interface SubscriptionRetireOptions {
  yes?: boolean;
  force?: boolean;
  expired?: boolean;
  dryRun?: boolean;
}

/** The one licence the argument names: a full GUID, or a prefix of exactly one licence in the report. */
function matchLicence<T extends { repositoryGuid: string }>(arg: string, recent: T[]): T {
  const wanted = arg.trim().toLowerCase();
  if (wanted.length < MIN_GUID_PREFIX) {
    throw new ValidationError(t('commands.subscription.retire.tooShort', { guid: arg }));
  }
  const matches = recent.filter((r) => r.repositoryGuid.toLowerCase().startsWith(wanted));
  if (matches.length === 0) {
    throw new ValidationError(t('commands.subscription.retire.notFound', { guid: arg }));
  }
  if (matches.length > 1) {
    throw new ValidationError(
      t('commands.subscription.retire.ambiguous', {
        guid: arg,
        count: matches.length,
        matches: matches.map((m) => m.repositoryGuid).join(', '),
      })
    );
  }
  return matches[0];
}

/** The batch prompt of `--expired`, refused outright when nobody can answer it. */
function confirmExpired(count: number): Promise<boolean> {
  if (process.stdin.isTTY !== true) {
    throw new ValidationError(t('commands.subscription.retire.needsYes'));
  }
  return askConfirm(t('commands.subscription.retire.expiredConfirm', { count }));
}

/** The prompt, for a run without `--yes`: refused outright when nobody can answer it. */
function confirmRetire(name: string, guid: string, state: string): Promise<boolean> {
  if (process.stdin.isTTY !== true) {
    throw new ValidationError(t('commands.subscription.retire.needsYes'));
  }
  return askConfirm(t('commands.subscription.retire.confirm', { name, guid, state }));
}

export async function executeSubscriptionRetire(
  guidArg: string | undefined,
  options: SubscriptionRetireOptions = {}
): Promise<void> {
  if (options.expired && guidArg !== undefined) {
    throw new ValidationError(t('commands.subscription.retire.expiredWithGuid'));
  }
  if (!options.expired && guidArg === undefined) {
    throw new ValidationError(t('commands.subscription.retire.needsGuidOrExpired'));
  }
  if (!options.expired && options.dryRun) {
    throw new ValidationError(t('commands.subscription.retire.dryRunNeedsExpired'));
  }
  const tokenState = getSubscriptionTokenState();
  if (tokenState.kind !== 'ready') {
    throw new ValidationError(unreadyTokenDiagnostic(tokenState));
  }
  await assertSubscriptionScopeMatchesConfig(tokenState.token);

  const report = await fetchSubscriptionLicenseReportOrThrow();
  if (!report) {
    throw new ValidationError(t('errors.subscription.notLoggedIn'));
  }
  if (options.expired) {
    await retireExpired(report.repoLicenses.recent ?? [], options);
    return;
  }
  const licence = matchLicence(guidArg ?? '', report.repoLicenses.recent ?? []);
  const guid = licence.repositoryGuid;
  const names = await readRepoNames();
  const entry = names.get(guid);
  const name = licenceDisplayName(guid, names);
  const state = t(LICENCE_STATE_KEYS[licence.freshness]);

  if (entry && !entry.deleted && licence.freshness !== 'hard_expired' && !options.force) {
    throw new ValidationError(t('commands.subscription.retire.inConfig', { name, state }));
  }

  if (!options.yes && !(await confirmRetire(name, guid, state))) {
    outputService.info(t('status.cancelled'));
    return;
  }

  const result = await retireRepoLicense(guid);
  const format = getOutputFormat();
  if (format !== 'table') {
    outputService.print({ repositoryGuid: result.repositoryGuid, name, retired: true }, format);
    return;
  }
  outputService.success(t('commands.subscription.retire.success', { name }));
}

type RetireOutcome = { guid: string; name: string; error?: string };

/** Retire each target through the one per-GUID route, collecting the failures instead of stopping at the first. */
async function retireEach(targets: LicenceRow[]): Promise<{
  retired: RetireOutcome[];
  failed: RetireOutcome[];
}> {
  const retired: RetireOutcome[] = [];
  const failed: RetireOutcome[] = [];
  for (const row of targets) {
    const name = row.name ?? row.guid.slice(0, 8);
    try {
      await retireRepoLicense(row.guid);
      retired.push({ guid: row.guid, name });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      failed.push({ guid: row.guid, name, error: message });
      outputService.warn(t('commands.subscription.retire.expiredFailed', { name, error: message }));
    }
  }
  return { retired, failed };
}

/**
 * `subscription retire --expired`: every hard-expired licence of a deleted repository or one this
 * config does not know, never a live one. One confirmation for the batch; `--dry-run` lists and stops.
 * A failed retire sets a non-zero exit after the rest were tried.
 */
async function retireExpired(
  recent: Parameters<typeof licenceRows>[0],
  options: SubscriptionRetireOptions
): Promise<void> {
  const names = await readRepoNames();
  if (names.size === 0) {
    throw new ValidationError(t('commands.subscription.retire.expiredNeedsConfig'));
  }
  const rows = licenceRows(recent, names);
  const targets = expiredRetireTargets(rows);
  const skipped = rows.filter((r) => r.freshness === 'hard_expired' && r.presence === 'config');
  const format = getOutputFormat();
  const counts = { skipped: skipped.length, dryRun: options.dryRun === true };

  if (targets.length === 0) {
    if (format === 'table') outputService.info(t('commands.subscription.retire.expiredNone'));
    else outputService.print({ retired: [], failed: [], ...counts }, format);
    return;
  }
  if (format === 'table') {
    outputService.report(t('commands.subscription.retire.expiredList', { count: targets.length }));
    printOtherLicences(targets);
  }
  if (options.dryRun) {
    if (format === 'table') outputService.info(t('commands.subscription.retire.expiredDryRun'));
    else
      outputService.print(
        { retired: [], failed: [], would: targets.map((r) => r.guid), ...counts },
        format
      );
    return;
  }
  if (!options.yes && !(await confirmExpired(targets.length))) {
    outputService.info(t('status.cancelled'));
    return;
  }

  const { retired, failed } = await retireEach(targets);
  if (failed.length > 0) setExitCode(1);
  if (format === 'table') {
    outputService.report(
      t('commands.subscription.retire.expiredResult', {
        retired: retired.length,
        skipped: skipped.length,
        failed: failed.length,
      })
    );
    return;
  }
  outputService.print({ retired, failed, ...counts }, format);
}
