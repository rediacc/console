/**
 * License-status health checks over the machine listing, split from parsing-health.ts.
 */

import {
  getLicenseStatuses,
  type ListResult,
} from '../../renet-contract/data/list-types.generated.js';
import { type HealthCheckContext, issue } from './health-context.js';

/** The license counts one listing reduces to. */
export interface LicenseHealthDetails {
  total: number;
  valid: number;
  expired: number;
  machineMismatch: number;
  missing: number;
  invalidSignature: number;
}

/**
 * Whether a licence has entered its refresh window.
 *
 * An absent or unparseable timestamp means "no window published" and must not be
 * read as overdue — the server owns this hint, and inventing urgency from a
 * missing field would fire on every machine whose licences predate the field.
 */
function isPastRefreshWindow(refreshRecommendedAt: string | undefined): boolean {
  if (!refreshRecommendedAt) return false;
  const due = Date.parse(refreshRecommendedAt);
  if (Number.isNaN(due)) return false;
  return due <= Date.now();
}

/** Check license statuses */
export function checkLicenses(
  listResult: ListResult,
  ctx: HealthCheckContext
): LicenseHealthDetails {
  const statuses = getLicenseStatuses(listResult);
  const details = {
    total: statuses.length,
    valid: 0,
    expired: 0,
    machineMismatch: 0,
    missing: 0,
    invalidSignature: 0,
  };

  for (const s of statuses) {
    switch (s.status) {
      case 'valid':
        details.valid++;
        break;
      case 'expired':
        details.expired++;
        break;
      case 'machine_mismatch':
        details.machineMismatch++;
        break;
      case 'missing':
        details.missing++;
        break;
      case 'invalid_signature':
      case 'sequence_regression':
        details.invalidSignature++;
        break;
    }
  }

  // Licences carry a soft window (refreshRecommendedAt) before they hard-expire, so a lapse is predictable rather than sudden. Saying so while everything still works is the only warning that arrives in time to act on: once a licence actually expires, the backup has already started skipping that repo. Severity stays below expired — this is "action is due", not "something broke".
  const dueForRefresh = statuses.filter(
    (s) => s.runtimeValid && isPastRefreshWindow(s.refreshRecommendedAt)
  ).length;
  const license = { subject: 'licenses' };
  if (dueForRefresh > 0) {
    issue(ctx, 0, `${dueForRefresh} repo license(s) due for refresh`, {
      ...license,
      code: 'license.refresh-due',
    });
  }

  if (details.expired > 0) {
    issue(ctx, 1, `${details.expired} repo license(s) expired`, {
      ...license,
      code: 'license.expired',
    });
  }
  if (details.machineMismatch > 0) {
    issue(ctx, 1, `${details.machineMismatch} repo license(s) have machine ID mismatch`, {
      ...license,
      code: 'license.machine-mismatch',
    });
  }
  if (details.invalidSignature > 0) {
    issue(ctx, 2, `${details.invalidSignature} repo license(s) have invalid signatures`, {
      ...license,
      code: 'license.invalid-signature',
    });
  }
  if (details.total > 0 && details.missing === details.total) {
    issue(ctx, 2, 'All repo licenses are missing', { ...license, code: 'license.missing' });
  } else if (details.missing > 0) {
    // A repo without a license is silently dropped from backups (the sync skips unlicensed repos and still exits 0), so a partial outage is exactly the
    // case that needs saying out loud — previously only an all-missing estate
    // raised anything, and losing 3 of 11 licenses reported nothing at all.
    issue(ctx, 1, `${details.missing} repo license(s) missing`, {
      ...license,
      code: 'license.missing',
    });
  }

  return details;
}
