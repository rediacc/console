/**
 * `rdc backup download --store`: rebuild a repository's encrypted image on a local path straight
 * from the chunk store, with no machine (agent/plans/PLAN-backup-download-from-store.md, C1).
 *
 * The account mints a restore session for a lineage (API token with the `backup:restore` scope);
 * the session JSON goes to a local `renet backup fetch-image` on stdin, never on argv. renet hashes
 * every chunk; this module adds the LUKS header check on the finished file.
 */

import { t } from '../../i18n/index.js';
import { ValidationError } from '../../utils/errors.js';
import {
  type AttemptFailure,
  HOME_STORE,
  runWithFallback,
  type StorePick,
} from '../backup/backup-store-pick.js';
import { outputService } from '../core/output.js';

/** The account's restore-session response. */
export interface RestoreSession {
  token: string;
  expiresAt?: string;
  subscriptionId?: string;
  dataPlaneUrl?: string;
  grantKind?: string;
  lineageGuid: string;
}

/** What renet prints on its single JSON line (the fields this module reads). */
interface FetchImageRecord {
  status: string;
  reason?: string;
  snapshotId?: string;
  partial?: string;
  bytesFetched?: number;
  /** The engine's Merkle-root check: "verified" or "absent". */
  cellsRoot?: string;
  cellsRootValue?: string;
  chunksFetched?: number;
  chunksReused?: number;
  imageBytes?: number;
}

export interface RenetRun {
  code: number;
  stdout: string;
  stderr: string;
}

export interface StoreFetchDeps {
  resolveLineage(ref: string): Promise<string>;
  resolveSnapshot(lineage: string, at: string): Promise<string>;
  /** `store` is absent for `home`. */
  mintSession(lineage: string, store?: string): Promise<RestoreSession>;
  /** The stores to try, ranked by the account; absent means `home` alone. */
  pickStores?(lineage: string): Promise<StorePick>;
  /** `<account>/account/api/v1/backups`, the route group renet's read grant hangs off. */
  apiBase(): string;
  renetPath(): Promise<string>;
  /** Spawns renet with `stdin` piped in; the secret is only ever in `stdin`, never in `args`. */
  runRenet(renet: string, args: string[], stdin: string, signal?: AbortSignal): Promise<RenetRun>;
  /** The first `length` bytes of the file. */
  readHead(file: string, length: number): Promise<Buffer>;
  now(): Date;
}

export interface StoreFetchRequest {
  ref: string;
  /** Destination file (the resume file). */
  dest: string;
  at?: string;
  /** `--from <storeId>`: read this store alone, no fallback. */
  store?: string;
  signal?: AbortSignal;
}

export interface StoreFetchResult {
  snapshotId: string;
  dest: string;
  record: FetchImageRecord;
  /** The backup store that served the image. */
  store: string;
}

/** The JSON `rdc backup download --store` prints: the fetch result plus the engine's own root check. */
export function storeFetchJson(result: StoreFetchResult): Record<string, unknown> {
  const { record } = result;
  return {
    status: record.status,
    image: result.dest,
    snapshotId: result.snapshotId,
    bytesFetched: record.bytesFetched ?? 0,
    ...(record.cellsRoot ? { cellsRoot: record.cellsRoot } : {}),
    ...(record.cellsRootValue ? { cellsRootValue: record.cellsRootValue } : {}),
  };
}

/**
 * The text-mode root-check line, or undefined when none is due. "absent" means the snapshot's manifest predates the
 * root (renet's CellsRootAbsent), so nothing was compared, and printing that enum as "Snapshot root check: absent" reads
 * as a failed check. Every other outcome is printed, so one renet adds later is not silently dropped. The JSON output
 * keeps the raw outcome.
 */
export function storeCellsRootLine(record: { cellsRoot?: string }): string | undefined {
  return record.cellsRoot && record.cellsRoot !== 'absent'
    ? t('commands.backup.download.storeCellsRoot', { outcome: record.cellsRoot })
    : undefined;
}

/** "LUKS" followed by 0xBA 0xBE: the first six bytes of every LUKS1 and LUKS2 volume. */
export const LUKS_MAGIC = Buffer.from([0x4c, 0x55, 0x4b, 0x53, 0xba, 0xbe]);

interface StatusError {
  status?: number;
  code?: string;
}

/** Maps the restore-session refusals to a message that names the cure. */
function describeSessionRefusal(error: unknown): Error {
  const e = error as StatusError | null;
  const status = e?.status;
  const code = e?.code;
  if (status === 404) return new ValidationError(t('errors.backupImage.storeLineageNotFound'));
  if (status === 429) return new ValidationError(t('errors.backupImage.storeRateLimited'));
  if (status === 403) {
    if (code === 'BACKUP_RETENTION_EXPIRED') {
      return new ValidationError(t('errors.backupImage.storeRetentionExpired'));
    }
    if (code === 'TEAM_SCOPE_REQUIRED') {
      return new ValidationError(t('errors.backupImage.storeTeamScope'));
    }
    if (code === 'INSUFFICIENT_ORG_ROLE') {
      return new ValidationError(t('errors.backupImage.storeRole'));
    }
    return new ValidationError(t('errors.backupImage.storeNoScope'));
  }
  return error instanceof Error ? error : new Error(String(error));
}

/** The one JSON line renet prints, or null when stdout carries none. */
function parseFetchRecord(stdout: string): FetchImageRecord | null {
  const lines = stdout.split(/\r?\n/).filter((l) => l.trim() !== '');
  for (let i = lines.length - 1; i >= 0; i -= 1) {
    try {
      const parsed = JSON.parse(lines[i]) as FetchImageRecord;
      if (parsed && typeof parsed.status === 'string') return parsed;
    } catch {
      // not the record line
    }
  }
  return null;
}

/**
 * The lineage and snapshot to fetch. Both reads take backup:read, so a token
 * with only backup:restore is refused here first, and the refusal names both
 * scopes. No --at means the newest snapshot: a time of now resolves to it.
 */
async function resolveTarget(
  req: StoreFetchRequest,
  deps: StoreFetchDeps
): Promise<{ lineage: string; snapshotId: string }> {
  try {
    const lineage = await deps.resolveLineage(req.ref);
    const snapshotId = await deps.resolveSnapshot(lineage, req.at ?? deps.now().toISOString());
    return { lineage, snapshotId };
  } catch (error) {
    if ((error as StatusError | null)?.status === 403) throw describeSessionRefusal(error);
    throw error;
  }
}

/** Marks an error `fetchFromStore` rewrote from a refused session mint, and holds the original. */
const REFUSED_FROM = Symbol('sessionRefusalOf');

function isSessionRefusal(error: unknown): error is Error & { [REFUSED_FROM]: unknown } {
  return error instanceof Error && REFUSED_FROM in error;
}

/**
 * What a thrown mint or fetch error says to the store-fault classifier: its HTTP status counts as text, and a mint the
 * store refused with a 403 that names no account-level code (retention, team scope, role) is that store's refused grant.
 * A session refusal was rewritten into a message for the operator, so the original error rides marked under `REFUSED_FROM`; any other error is read as it is, whatever `cause` it carries.
 */
function failureOf(error: unknown): AttemptFailure {
  const original = isSessionRefusal(error) ? error[REFUSED_FROM] : error;
  const { status, code } = (original ?? {}) as StatusError;
  const message = original instanceof Error ? original.message : String(original);
  if (status === 403 && code === undefined) return { error: `grant refused (HTTP 403) ${message}` };
  return { error: status === undefined ? message : `HTTP ${status} ${message}`, errorCode: code };
}

/** One store's attempt: mint its session, run renet's fetch, return the record. Throws what went wrong. */
async function fetchFromStore(
  req: StoreFetchRequest,
  deps: StoreFetchDeps,
  lineage: string,
  snapshotId: string,
  store: string
): Promise<{ record: FetchImageRecord; run: RenetRun }> {
  let session: RestoreSession;
  try {
    session = await (store === HOME_STORE
      ? deps.mintSession(lineage)
      : deps.mintSession(lineage, store));
  } catch (error) {
    throw Object.assign(describeSessionRefusal(error), { [REFUSED_FROM]: error });
  }

  const stdin = JSON.stringify({ ...session, apiBase: deps.apiBase(), lineageGuid: lineage });
  const renet = await deps.renetPath();
  const run = await deps.runRenet(
    renet,
    ['backup', 'fetch-image', '--dest', req.dest, '--snapshot', snapshotId],
    stdin,
    req.signal
  );
  const record = parseFetchRecord(run.stdout);
  if (run.code !== 0 || record?.status !== 'fetched') {
    const reason = record?.reason ?? (run.stderr.trim() || `exit ${run.code}`);
    const partial = record?.partial
      ? ` ${t('errors.backupImage.storeResumeAt', { partial: record.partial })}`
      : '';
    throw new Error(`${t('errors.backupImage.storeFetchFailed', { reason })}${partial}`);
  }
  return { record, run };
}

export async function runStoreFetch(
  req: StoreFetchRequest,
  deps: StoreFetchDeps
): Promise<StoreFetchResult> {
  const { lineage, snapshotId } = await resolveTarget(req, deps);

  const pick: StorePick =
    req.store === undefined
      ? ((await deps.pickStores?.(lineage)) ?? { stores: [HOME_STORE], explicit: false })
      : { stores: [req.store], explicit: true };
  // The error a failed attempt raised, rethrown as is when no store served.
  let raised: Error | undefined;
  const served = await runWithFallback(
    pick,
    async (store) => {
      try {
        const record = await fetchFromStore(req, deps, lineage, snapshotId, store);
        return { ok: true as const, value: record };
      } catch (error) {
        raised = error instanceof Error ? error : new Error(String(error));
        return { ok: false as const, failure: failureOf(error) };
      }
    },
    (failed, next) => {
      outputService.warn(t('commands.backup.restore.storeFallback', { failed, next }));
    }
  );
  if (!served.ok) {
    throw raised ?? new Error(t('errors.backupImage.storeFetchFailed', { reason: 'unknown' }));
  }
  const { record } = served.value;
  const head = await deps.readHead(req.dest, LUKS_MAGIC.length);
  if (head.length < LUKS_MAGIC.length || !head.subarray(0, LUKS_MAGIC.length).equals(LUKS_MAGIC)) {
    throw new Error(t('errors.backupImage.storeNoLuksHeader', { image: req.dest }));
  }
  return { snapshotId, dest: req.dest, record, store: served.store };
}
