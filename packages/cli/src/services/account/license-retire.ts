/**
 * Retiring a repository's license on the account server, and reading the names a GUID resolves to.
 *
 * Shared by every path that deletes a repository image (`settleDeletedRepoLicense`: `repo delete`,
 * `repo admin orphan delete`, `machine prune`, the restore-test copy), `subscription retire` and the
 * account view of `subscription status`. The server stores GUIDs only; names come from the local config.
 */

import { type RepoNameEntry, repoNamesByGuid, shortGuid } from '@rediacc/shared/config-schema';
import { t } from '../../i18n/index.js';
import { configService } from '../config/config-resources.js';
import { outputService } from '../core/output.js';
import { accountServerFetch } from './account-client.js';
import { getSubscriptionTokenState } from './subscription-auth.js';

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
  const guid = encodeURIComponent(repositoryGuid);
  return accountServerFetch<RepoLicenseRetireResult>(
    `/account/api/v1/licenses/repos/${guid}/retire`,
    { method: 'POST' }
  );
}

/**
 * Retire the licence of a repository whose image was just deleted, so the account's licence summary
 * stops counting it (and `rdc doctor` stops failing on it once it hard-expires). Never fails the
 * delete: an unreachable or refusing server is said by name with the reason. A 404 means the server
 * holds no licence of this GUID for the token's scope, which leaves nothing to retire. No account
 * token means this config never issued a licence, so there is nothing to retire and nothing to say.
 */
export async function settleDeletedRepoLicense(
  name: string,
  repositoryGuid: string
): Promise<void> {
  if (getSubscriptionTokenState().kind !== 'ready') return;
  try {
    await retireRepoLicense(repositoryGuid);
  } catch (error) {
    if ((error as { status?: unknown } | null)?.status === 404) return;
    outputService.warn(
      t('commands.repo.delete.licenseRetireFailed', {
        repository: name,
        reason: error instanceof Error ? error.message : String(error),
      })
    );
  }
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
  /**
   * Live in this config, archived as deleted, or unknown to it. `gone` is a config entry whose image the
   * listing of its recorded place does not hold (deleted on the machine behind the config's back); only
   * `subscription retire --expired` sets it, after reading that listing (goneExpiredLicences).
   */
  presence: 'config' | 'deleted' | 'absent' | 'gone';
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

const URGENCY_RANK: Record<ReportedLicence['freshness'], number> = {
  hard_expired: 0,
  refresh_recommended: 1,
  valid: 2,
};

/** The table order of the live repositories: hard expired, refresh recommended, valid, then soonest hard expiry. */
function compareUrgency(a: LicenceRow, b: LicenceRow): number {
  return URGENCY_RANK[a.freshness] - URGENCY_RANK[b.freshness] || compareHardExpiry(a, b);
}

/** The licences of repositories the active config holds, most urgent first. */
export function liveLicences(rows: LicenceRow[]): LicenceRow[] {
  return rows.filter((row) => row.presence === 'config').sort(compareUrgency);
}

/** The licences of repositories deleted from the config, unknown to it or gone from their machine, most urgent first. */
export function otherLicences(rows: LicenceRow[]): LicenceRow[] {
  return rows.filter((row) => row.presence !== 'config').sort(compareUrgency);
}

/** One datastore a listing can be read from: a configured machine's default datastore, or a local named one. */
export interface RepoPlace {
  machine: string;
  /** The named datastore, or null for the machine's default datastore. */
  datastore: string | null;
}

/** The repository GUIDs (lowercase) one place holds. Throws when the listing cannot be read. */
export type PlaceLister = (place: RepoPlace) => Promise<Set<string>>;

/** What `subscription retire --expired` decided about the hard-expired licences. */
export interface GoneLicences {
  /** Provably gone: retire these, most urgent first. */
  targets: LicenceRow[];
  /** Hard-expired but not provably gone (an image a listing still shows, an unreadable or unlistable place): never retired. */
  kept: LicenceRow[];
  /** The places whose listing failed, with the reason. */
  unreachable: { place: RepoPlace; error: string }[];
}

type PlaceSource = {
  resources?: {
    machines?: Record<string, unknown>;
    datastores?: Record<string, { backend: { kind: string; machine?: string } }>;
  };
} | null;

/** Every place the config can list: each machine's default datastore, then each local named datastore. */
export function configuredRepoPlaces(config: PlaceSource): RepoPlace[] {
  const resources = config?.resources ?? {};
  const places: RepoPlace[] = Object.keys(resources.machines ?? {})
    .sort((a, b) => (a < b ? -1 : 1))
    .map((machine) => ({ machine, datastore: null }));
  const stores = Object.entries(resources.datastores ?? {}).sort(([a], [b]) => (a < b ? -1 : 1));
  for (const [datastore, store] of stores) {
    if (store.backend.kind === 'local' && store.backend.machine) {
      places.push({ machine: store.backend.machine, datastore });
    }
  }
  return places;
}

const placeKey = (place: RepoPlace): string => `${place.machine}/${place.datastore ?? ''}`;

/** Each place's listing read at most once; a failed read is remembered as null and reported once. */
class PlaceListings {
  private readonly listings = new Map<string, Set<string> | null>();
  readonly unreachable: GoneLicences['unreachable'] = [];

  constructor(private readonly list: PlaceLister) {}

  async read(place: RepoPlace): Promise<Set<string> | null> {
    const key = placeKey(place);
    if (!this.listings.has(key)) this.listings.set(key, await this.tryList(place));
    return this.listings.get(key) ?? null;
  }

  private async tryList(place: RepoPlace): Promise<Set<string> | null> {
    try {
      return await this.list(place);
    } catch (error) {
      this.unreachable.push({
        place,
        error: error instanceof Error ? error.message : String(error),
      });
      return null;
    }
  }

  /** Some listing read so far holds the GUID. */
  holds(guid: string): boolean {
    const wanted = guid.toLowerCase();
    return [...this.listings.values()].some((set) => set?.has(wanted) === true);
  }
}

/** A config-held repository is gone only when the listing of its recorded place was read and lacks its GUID. */
async function isGoneFromPlace(
  guid: string,
  entry: RepoNameEntry | undefined,
  listings: PlaceListings
): Promise<boolean> {
  if (!entry?.machine) return false;
  const listing = await listings.read({ machine: entry.machine, datastore: entry.datastore });
  return listing !== null && !listing.has(guid.toLowerCase());
}

/**
 * Which hard-expired licences `subscription retire --expired` may retire. Nothing here retires a licence whose
 * repository image a listing still shows:
 * - a deleted or unknown repository is retired unless some listed place still holds its GUID;
 * - a repository the config still holds is retired only when the listing of the place the config records for it
 *   was read and does not hold its GUID; an unreadable place, or a placement with no listable place (an RBD
 *   datastore), keeps it.
 * Each place is listed at most once, and none is listed when nothing is hard-expired.
 */
export async function goneExpiredLicences(
  rows: LicenceRow[],
  names: Map<string, RepoNameEntry>,
  places: RepoPlace[],
  list: PlaceLister
): Promise<GoneLicences> {
  const expired = rows.filter((row) => row.freshness === 'hard_expired');
  const listings = new PlaceListings(list);
  if (expired.some((row) => row.presence !== 'config')) {
    for (const place of places) await listings.read(place);
  }
  const targets: LicenceRow[] = [];
  const kept: LicenceRow[] = [];
  // Config-held rows first, so every listing they read is in place before an elsewhere row asks holds().
  for (const row of expired.filter((r) => r.presence === 'config')) {
    if (await isGoneFromPlace(row.guid, names.get(row.guid), listings)) {
      targets.push({ ...row, presence: 'gone' });
    } else {
      kept.push(row);
    }
  }
  for (const row of expired.filter((r) => r.presence !== 'config')) {
    (listings.holds(row.guid) ? kept : targets).push(row);
  }
  return { targets: otherLicences(targets), kept, unreachable: listings.unreachable };
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
