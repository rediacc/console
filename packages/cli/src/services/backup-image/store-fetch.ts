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
  mintSession(lineage: string): Promise<RestoreSession>;
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
  signal?: AbortSignal;
}

export interface StoreFetchResult {
  snapshotId: string;
  dest: string;
  record: FetchImageRecord;
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

export async function runStoreFetch(
  req: StoreFetchRequest,
  deps: StoreFetchDeps
): Promise<StoreFetchResult> {
  const { lineage, snapshotId } = await resolveTarget(req, deps);

  let session: RestoreSession;
  try {
    session = await deps.mintSession(lineage);
  } catch (error) {
    throw describeSessionRefusal(error);
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

  const head = await deps.readHead(req.dest, LUKS_MAGIC.length);
  if (head.length < LUKS_MAGIC.length || !head.subarray(0, LUKS_MAGIC.length).equals(LUKS_MAGIC)) {
    throw new Error(t('errors.backupImage.storeNoLuksHeader', { image: req.dest }));
  }
  return { snapshotId, dest: req.dest, record };
}
