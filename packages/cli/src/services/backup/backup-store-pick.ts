/**
 * Which backup store a restore reads from, and when it moves to the next one.
 *
 * A lineage can hold a snapshot in several stores (one per destination). The account server ranks them, newest
 * snapshot whose last verify passed first (`GET /backups/stores/lineage/:lineageGuid`); the restore verbs take that order,
 * or the store `--from` names. A restore falls back to the next store only on a failure that is the STORE's: a 5xx, a
 * refused grant, an unreachable endpoint. A snapshot that is missing or fails its own verification is the same
 * snapshot everywhere it is asked for, so it is never retried elsewhere, and an explicit `--from` never falls back.
 */

import { t } from '../../i18n/index.js';
import { accountServerFetch } from '../account/account-client.js';
import { outputService } from '../core/output.js';

/** The store every subscription has from the first day; renet takes no `--store` for it. */
export const HOME_STORE = 'home';

/** One row of the account's per-lineage store listing. */
export interface LineageStore {
  storeId: string;
  newestSnapshotId: string | null;
  newestSnapshotAt: string | null;
  lastVerifyOk: boolean | null;
}

interface LineageStoresResponse {
  stores: LineageStore[];
}

export interface StorePick {
  stores: string[];
  /** `--from` named the store: no fallback follows it. */
  explicit: boolean;
}

/**
 * The stores to try for a lineage, in order. `from` names exactly one store and no fallback follows it. Without it the
 * account's ranking is taken as given, minus a store that holds no snapshot. An older account server (404) and an
 * empty ranking both answer `home` alone, silently: that is what every restore did before stores existed. Any other
 * failure to read the ranking answers `home` too, with a warning.
 */
export async function pickStores(lineage: string, from?: string): Promise<StorePick> {
  if (from !== undefined) return { stores: [from], explicit: true };
  let ranked: LineageStore[] | undefined;
  try {
    ranked = await fetchLineageStores(lineage);
  } catch (error) {
    // Restore is disaster recovery: a ranking that cannot be read must not stop it from reading the home store, as it did before stores existed. Said out loud, since it may not be the best store.
    outputService.warn(
      t('commands.backup.restore.storeRankingUnreadable', {
        reason: error instanceof Error ? error.message : String(error),
      })
    );
  }
  const holding = (ranked ?? []).filter((s) => s.newestSnapshotId !== null).map((s) => s.storeId);
  return { stores: holding.length > 0 ? holding : [HOME_STORE], explicit: false };
}

/** The account's ranked listing of a lineage's stores; undefined from an older account server (404), which has none. */
async function fetchLineageStores(lineage: string): Promise<LineageStore[] | undefined> {
  try {
    const response: LineageStoresResponse | undefined =
      await accountServerFetch<LineageStoresResponse>(
        `/account/api/v1/backups/stores/lineage/${encodeURIComponent(lineage)}`
      );
    return Array.isArray(response?.stores) ? response.stores : [];
  } catch (error) {
    if ((error as { status?: number } | null)?.status === 404) return undefined;
    throw error;
  }
}

/** The renet `--store` param for a store: absent for `home`, which a renet without the flag also accepts. */
export function storeParam(store: string): { store?: string } {
  return store === HOME_STORE ? {} : { store };
}

/** What a failed attempt left behind to classify. */
export interface AttemptFailure {
  exitCode?: number;
  error?: string;
  errorCode?: string;
  stdout?: string;
  stderr?: string;
}

/** The snapshot's own faults: the same answer from every store, so moving on cannot help. */
const SNAPSHOT_OWN =
  /snapshot[^\n]{0,40}(not found|missing|unknown|expired)|no such snapshot|manifest[^\n]{0,40}(not found|invalid|corrupt)|verif(y|ication) failed|digest mismatch|hash mismatch|BACKUP_RETENTION_EXPIRED|SNAPSHOT_NOT_FOUND/i;

/** The store's faults: a server error, a refused grant or session, an endpoint that does not answer. */
const STORE_SIDE =
  /\b5\d\d\b|bad gateway|service unavailable|gateway timeout|grant[^\n]{0,40}(refused|denied|forbidden|failed)|session[^\n]{0,40}(refused|denied|invalid|failed)|BACKUP_SESSION_INVALID|EGRESS_UNREACHABLE|ECONNREFUSED|ECONNRESET|ETIMEDOUT|ENOTFOUND|EHOSTUNREACH|unreachable|timed out|connection (refused|reset)|store[^\n]{0,30}suspended|STORE_SUSPENDED/i;

/**
 * Whether a failed attempt is the store's own fault. The snapshot's own faults win over a store word in the same
 * output, and anything unrecognised is NOT a store fault: an unknown failure is surfaced, never retried elsewhere.
 */
export function isStoreFailure(failure: AttemptFailure): boolean {
  const text = [failure.errorCode, failure.error, failure.stderr, failure.stdout]
    .filter((s): s is string => typeof s === 'string')
    .join('\n');
  if (SNAPSHOT_OWN.test(text)) return false;
  return STORE_SIDE.test(text);
}

export type Attempt<T> = { ok: true; value: T } | { ok: false; failure: AttemptFailure };

export type FallbackResult<T> =
  | { ok: true; store: string; value: T }
  | { ok: false; store: string; failure: AttemptFailure };

/**
 * Run `attempt` on each store in order until one succeeds. A failure moves on only when it is the store's and the pick
 * left another store to try (an explicit `--from` never does); `onFallback` says which store failed and which is
 * next. The result names the store that served, or the store of the failure that ended the run.
 */
export async function runWithFallback<T>(
  pick: StorePick,
  attempt: (store: string) => Promise<Attempt<T>>,
  onFallback?: (failed: string, next: string, failure: AttemptFailure) => void
): Promise<FallbackResult<T>> {
  let last: { store: string; failure: AttemptFailure } = { store: HOME_STORE, failure: {} };
  for (const [index, store] of pick.stores.entries()) {
    const outcome = await attempt(store);
    if (outcome.ok) return { ok: true, store, value: outcome.value };
    last = { store, failure: outcome.failure };
    const next = pick.stores[index + 1];
    if (pick.explicit || next === undefined || !isStoreFailure(outcome.failure)) break;
    onFallback?.(store, next, outcome.failure);
  }
  return { ok: false, ...last };
}

/** What `backup status` says about one store, summed over the streams the machine's repositories write to it. */
export interface StoreStatus {
  lastRunAt: string | null;
  lastRunStatus: string | null;
  newestSnapshotAt: string | null;
  /** `failed` when any stream's last verify failed, `ok` when one passed and none failed, else `-`. */
  verify: 'ok' | 'failed' | '-';
  /** `enabled`, or the `disabled -- <reason>` the store carries. */
  cleanup: string;
}

/** The destinations of each strategy (store ids) and what each store reports. */
export interface StatusTargets {
  byStrategy: Record<string, string[]>;
  stores: Record<string, StoreStatus>;
}

/** One stream of `GET /backups/status`; a row without `storeId` is `home`. */
export interface StatusStream {
  storeId?: string;
  lineageGuid: string;
  lastRunAt: string | null;
  lastRunStatus: string | null;
  newestSnapshotAt: string | null;
  lastVerifyStatus: string | null;
}

/** `GET /backups/status`: one row per stream, and each store's clean-up state (absent means `enabled`). */
export interface StatusResponse {
  stores?: { storeId: string; cleanup?: string }[];
  streams: StatusStream[];
}

/** The verify verdict after one more stream: a failure sticks, a pass shows only over no verdict. */
function mergeVerify(
  known: StoreStatus['verify'],
  lastVerifyStatus: string | null
): StoreStatus['verify'] {
  if (lastVerifyStatus === null) return known;
  if (/fail|error|mismatch/i.test(lastVerifyStatus)) return 'failed';
  return known === '-' && /ok|verified|proven|pass/i.test(lastVerifyStatus) ? 'ok' : known;
}

/** The later of two ISO timestamps, either of which may be absent. */
function later(a: string | null, b: string | null): string | null {
  return (
    [a, b]
      .filter((at): at is string => at !== null)
      .sort((x, y) => x.localeCompare(y))
      .at(-1) ?? null
  );
}

/** One status per store id, from the streams of these lineages. Pure. */
export function summarizeStatus(
  response: StatusResponse,
  lineages: ReadonlySet<string>
): Record<string, StoreStatus> {
  const cleanup = new Map((response.stores ?? []).map((s) => [s.storeId, s.cleanup ?? 'enabled']));
  const out: Record<string, StoreStatus> = {};
  for (const stream of response.streams.filter((s) => lineages.has(s.lineageGuid))) {
    const id = stream.storeId ?? HOME_STORE;
    const known: StoreStatus = out[id] ?? {
      lastRunAt: null,
      lastRunStatus: null,
      newestSnapshotAt: null,
      verify: '-',
      cleanup: cleanup.get(id) ?? 'enabled',
    };
    const newerRun = later(known.lastRunAt, stream.lastRunAt) === stream.lastRunAt;
    out[id] = {
      lastRunAt: later(known.lastRunAt, stream.lastRunAt),
      lastRunStatus: newerRun ? stream.lastRunStatus : known.lastRunStatus,
      newestSnapshotAt: later(known.newestSnapshotAt, stream.newestSnapshotAt),
      verify: mergeVerify(known.verify, stream.lastVerifyStatus),
      cleanup: known.cleanup,
    };
  }
  return out;
}

/**
 * The stores' statuses for these lineages, from the account's status route. An unreadable route (an older account
 * server answers 404, any other failure too) adds nothing: status never fails on it, and its columns stay `-`.
 */
export async function readStoreStatuses(lineages: string[]): Promise<Record<string, StoreStatus>> {
  try {
    const response = await accountServerFetch<StatusResponse>('/account/api/v1/backups/status');
    return Array.isArray(response?.streams) ? summarizeStatus(response, new Set(lineages)) : {};
  } catch {
    return {};
  }
}

/**
 * One printed row per destination store of the row's strategy (`home` when it names none), carrying that store's
 * last run and outcome (the unit's own when the account has none), newest snapshot, last verify and clean-up state.
 */
export function expandStatusRows<R extends { strategy: string; unit: string }>(
  rows: R[],
  targets?: StatusTargets
): (Omit<R, 'strategy' | 'unit'> & {
  strategy: string;
  unit: string;
  store: string;
  newestSnapshot: string;
  verify: string;
  cleanup: string;
})[] {
  return rows.flatMap((row) => {
    const { strategy, unit, ...rest } = row;
    const stores = targets?.byStrategy[strategy];
    return (stores && stores.length > 0 ? stores : [HOME_STORE]).map((store) => {
      const known = targets?.stores[store];
      const run = known?.lastRunAt
        ? { lastRun: known.lastRunAt, result: known.lastRunStatus ?? '-' }
        : {};
      return {
        strategy,
        unit,
        store,
        ...rest,
        ...run,
        newestSnapshot: known?.newestSnapshotAt ?? '-',
        verify: known?.verify ?? '-',
        cleanup: known?.cleanup ?? 'enabled',
      };
    });
  });
}
