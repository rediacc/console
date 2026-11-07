import { t } from '../i18n/index.js';
import type { RuntimeRepoLicenseStatus } from '../services/account/license.js';
import { outputService } from '../services/core/output.js';
import { formatRuntimeRepoLicenseStatus } from './subscription-output.js';

/** The per-repo license table, from the `license-status` job's output (renet's runtime state on the machine). */
export function renderRepoLicenseTable(
  machineName: string,
  entries: RuntimeRepoLicenseStatus[]
): void {
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
