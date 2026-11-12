/**
 * `subscription retire <guid>`: retire the license of a repository that is gone, so it leaves the
 * license counts and the notices. Retirement is sticky (a renewal does not bring the repository
 * back), so a repository the config still holds is refused unless its license is hard-expired or
 * `--force` is given.
 */

import { t } from '../i18n/index.js';
import { fetchSubscriptionLicenseReportOrThrow } from '../services/account/license.js';
import {
  LICENCE_STATE_KEYS,
  licenceDisplayName,
  readRepoNames,
  retireRepoLicense,
} from '../services/account/license-retire.js';
import { getSubscriptionTokenState } from '../services/account/subscription-auth.js';
import { outputService } from '../services/core/output.js';
import { getOutputFormat, ValidationError } from '../utils/errors.js';
import { askConfirm } from '../utils/prompt.js';
import {
  assertSubscriptionScopeMatchesConfig,
  unreadyTokenDiagnostic,
} from './subscription-actions.js';

/** A GUID prefix shorter than this matches too many licenses to name one. */
const MIN_GUID_PREFIX = 8;

export interface SubscriptionRetireOptions {
  yes?: boolean;
  force?: boolean;
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

/** The prompt, for a run without `--yes`: refused outright when nobody can answer it. */
function confirmRetire(name: string, guid: string, state: string): Promise<boolean> {
  if (process.stdin.isTTY !== true) {
    throw new ValidationError(t('commands.subscription.retire.needsYes'));
  }
  return askConfirm(t('commands.subscription.retire.confirm', { name, guid, state }));
}

export async function executeSubscriptionRetire(
  guidArg: string,
  options: SubscriptionRetireOptions = {}
): Promise<void> {
  const tokenState = getSubscriptionTokenState();
  if (tokenState.kind !== 'ready') {
    throw new ValidationError(unreadyTokenDiagnostic(tokenState));
  }
  await assertSubscriptionScopeMatchesConfig(tokenState.token);

  const report = await fetchSubscriptionLicenseReportOrThrow();
  if (!report) {
    throw new ValidationError(t('errors.subscription.notLoggedIn'));
  }
  const licence = matchLicence(guidArg, report.repoLicenses.recent ?? []);
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
