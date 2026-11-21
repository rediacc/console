/**
 * `subscription refresh -m <machine>` without a login, split out of subscription-actions.ts to stay within max-lines.
 */

import { t } from '../i18n/index.js';
import { renewInstalledLicenses } from '../services/account/free-license.js';
import { outputService } from '../services/core/output.js';
import { ValidationError } from '../utils/errors.js';
import { withSpinner } from '../utils/spinner.js';
import type { SubscriptionCommandContext } from './subscription-actions.js';

/**
 * `subscription refresh -m <machine>` with no login: renet renews each installed blob that is due, the blob itself being the credential (the same renewal `renewWithoutToken` runs for an expired licence). One line per repo. A blob the server will not renew without an account (a paid licence) is reported as needing login, and a run that renewed nothing for that reason still fails with the login message.
 */
export async function executeTokenFreeMachineRefresh(
  context: SubscriptionCommandContext
): Promise<void> {
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
  // Not beside a failure: the failed error says a login does not change it, and the refused repos' own lines already name the login.
  if (tally.needsLogin > 0 && tally.failed === 0) {
    outputService.info(t('commands.subscription.refresh.noLogin.paidNote'));
  }
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
