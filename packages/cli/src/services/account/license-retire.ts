/**
 * Retiring a repository's license on the account server, and reading the names a GUID resolves to.
 *
 * Shared by `repo delete` (`settleRepoLicense`), `subscription retire` and the account view of
 * `subscription status`. The server stores GUIDs only; names come from the local config.
 */

import { type RepoNameEntry, repoNamesByGuid, shortGuid } from '@rediacc/shared/config-schema';
import { configService } from '../config/config-resources.js';
import { accountServerFetch } from './account-client.js';

/** The server's answer to a retire: the same shape from the token route and the portal twin. */
export interface RepoLicenseRetireResult {
  repositoryGuid: string;
  retired: true;
}

/**
 * Tell the account server this repository's license is retired. Retirement is sticky: a later
 * renewal does not bring the repository back. Throws what the server answered.
 */
export function retireRepoLicense(repositoryGuid: string): Promise<RepoLicenseRetireResult> {
  return accountServerFetch<RepoLicenseRetireResult>(
    `/account/api/v1/licenses/repos/${encodeURIComponent(repositoryGuid)}/retire`,
    { method: 'POST' }
  );
}

/** Every GUID the active config knows by name, live or deleted. An absent config knows none. */
export async function readRepoNames(): Promise<Map<string, RepoNameEntry>> {
  const config = await configService.getCurrent();
  return config ? repoNamesByGuid(config) : new Map();
}

/** `ref@machine`, `ref` when no machine is known, or the 8-character GUID when the config does not know it. */
export function licenceDisplayName(guid: string, names: Map<string, RepoNameEntry>): string {
  const entry = names.get(guid);
  if (!entry) return shortGuid(guid);
  return entry.machine ? `${entry.ref}@${entry.machine}` : entry.ref;
}

/** The i18n key naming each freshness state, shared by `subscription status` and `subscription retire`. */
export const LICENCE_STATE_KEYS = {
  valid: 'commands.subscription.licenceState.valid',
  refresh_recommended: 'commands.subscription.licenceState.refreshRecommended',
  hard_expired: 'commands.subscription.licenceState.hardExpired',
} as const;

/** One tracked licence of the account report, as the server sends it. */
export interface ReportedLicence {
  repositoryGuid: string;
  freshness: 'valid' | 'refresh_recommended' | 'hard_expired';
  kind?: string;
  refreshRecommendedAt?: string;
  hardExpiresAt?: string;
}

/** A licence joined to the local config: what `subscription status` prints and `-o json` carries. */
export interface LicenceRow {
  guid: string;
  /** `ref` from the config, or null when this config does not know the GUID. */
  name: string | null;
  machine: string | null;
  kind: string | null;
  freshness: ReportedLicence['freshness'];
  refreshRecommendedAt: string | null;
  hardExpiresAt: string | null;
  /** Live in this config, archived as deleted, or unknown to it. */
  presence: 'config' | 'deleted' | 'absent';
  /** The exact command that settles a non-valid licence, or null when no local command does. */
  fix: string | null;
}

/**
 * The command that settles one licence. A repository in the config is refreshed; one that is
 * archived as deleted, or that this config never held, can only be retired, and only once its
 * licence has hard-expired (a retired licence is gone for good, and a refresh-recommended one of a
 * repository this config does not hold is another config's to refresh).
 */
function licenceFix(licence: ReportedLicence, entry: RepoNameEntry | undefined): string | null {
  if (licence.freshness === 'valid') return null;
  if (entry && !entry.deleted) return `rdc subscription refresh --repo ${entry.ref}`;
  if (licence.freshness === 'hard_expired') {
    return `rdc subscription retire ${shortGuid(licence.repositoryGuid)}`;
  }
  return null;
}

function compareHardExpiry(a: LicenceRow, b: LicenceRow): number {
  if (a.hardExpiresAt === b.hardExpiresAt) return a.guid.localeCompare(b.guid);
  if (a.hardExpiresAt === null) return 1;
  if (b.hardExpiresAt === null) return -1;
  return a.hardExpiresAt.localeCompare(b.hardExpiresAt);
}

/** Every reported licence joined to the config, soonest hard expiry first (no expiry last). */
export function licenceRows(
  recent: ReportedLicence[],
  names: Map<string, RepoNameEntry>
): LicenceRow[] {
  const rows = recent.map((licence): LicenceRow => {
    const entry = names.get(licence.repositoryGuid);
    let presence: LicenceRow['presence'] = 'absent';
    if (entry) presence = entry.deleted ? 'deleted' : 'config';
    return {
      guid: licence.repositoryGuid,
      name: entry?.ref ?? null,
      machine: entry?.machine ?? null,
      kind: licence.kind ?? null,
      freshness: licence.freshness,
      refreshRecommendedAt: licence.refreshRecommendedAt ?? null,
      hardExpiresAt: licence.hardExpiresAt ?? null,
      presence,
      fix: licenceFix(licence, entry),
    };
  });
  return rows.sort(compareHardExpiry);
}
