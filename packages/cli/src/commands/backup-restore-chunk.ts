import { t } from '../i18n/index.js';
import { accountServerFetch } from '../services/account/account-client.js';
import { assertHostedBackupAccount } from '../services/account/free-license.js';
import { outputService } from '../services/core/output.js';
import { setExitCode } from '../services/core/request-context.js';
import { getExecutor } from '../services/executor/executor-factory.js';
import {
  type CommandJobOutcome,
  pendingExitCode,
  runCommandJob,
} from '../services/jobs/command-job.js';
import { bindStepHandler, type PlannedStep, planStep } from '../services/jobs/steps.js';
import { deployRepoKeyIfNeeded } from '../services/repo/repo-key-deployment.js';
import { getOutputFormat, ValidationError } from '../utils/errors.js';
import { renderLocalExecutionFailure } from '../utils/local-execution-failures.js';
import { executeRepoFunction } from '../utils/repo-executor.js';
import type { RestoreOptions } from './backup.js';
import type { BackupManifestEntry } from './backup-storage.js';
import {
  parseRestoreStats,
  parseVerifyVerdict,
  type RestoreStats,
} from './backup-storage-parser.js';

/**
 * A snapshot id as `MintSnapshotID` writes it: RFC3339-basic UTC, a dash, and
 * 16 hex. Anything else in `--at` is a TIME, and resolving a time is the CLI's
 * job by explicit contract, the `backup_restore` FunctionDef says so in the
 * parameter description, because the machine has no manifest index to search.
 */
const SNAPSHOT_ID_RE = /^\d{8}T\d{6}Z-[0-9a-f]{16}$/;

const RESOLVE_ROUTE = '/account/api/v1/backups/snapshots/resolve';

/** The account answers 404 for "no row matches", which the callers turn into their own refusal. */
function isNotFound(error: unknown): boolean {
  return (error as { status?: unknown } | null)?.status === 404;
}

/** One GET /backups/snapshots/resolve: the row, or undefined for the route's 404. */
async function fetchResolved(
  lineage: string,
  query: Record<string, string | undefined>
): Promise<BackupManifestEntry | undefined> {
  const params = new URLSearchParams({ lineage });
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined) params.set(key, value);
  }
  try {
    return await accountServerFetch<BackupManifestEntry>(`${RESOLVE_ROUTE}?${params.toString()}`);
  } catch (error) {
    if (isNotFound(error)) return undefined;
    throw error;
  }
}

/** A span as an operator reads it: `2h 30m`, `3d 4h`, `45m`. */
function formatGap(ms: number): string {
  const minutes = Math.max(0, Math.round(ms / 60_000));
  if (minutes >= 24 * 60) {
    return `${Math.floor(minutes / (24 * 60))}d ${Math.floor((minutes % (24 * 60)) / 60)}h`;
  }
  if (minutes >= 60) return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
  return `${minutes}m`;
}

/** The instant `--at` names, refused before any call when it is no time or when a time has no stream to resolve in. */
function parseAtTime(at: string, scope: StreamScope): Date {
  const when = new Date(at);
  if (Number.isNaN(when.getTime())) {
    throw new ValidationError(t('commands.backup.restore.atUnparsable', { at }));
  }
  // A time without an anchor would land on any machine's stream.
  if (!scope.anyStream && !scope.anchorSnapshotId) {
    throw new ValidationError(t('commands.backup.restore.streamUnknown'));
  }
  return when;
}

/** How `resolveSnapshotAt` is asked for a snapshot a LISTING will be read from (browse, `restore --path`). */
export interface ResolveOptions {
  /** Prefer a snapshot with a stored listing: the nearest one at or before the time, with the gap stated. */
  indexed?: boolean;
}

/**
 * Turn `--at` into a snapshot id. A time selects the NEWEST snapshot at or before it, which is the
 * only reading that restores a point in time rather than the point after it. The account does the
 * search (GET /backups/snapshots/resolve, one indexed query), so it holds however long the history
 * is: the listing is capped at 500 rows a lineage page and a client-side filter loses everything
 * older.
 *
 * `createdAt` decides, not the timestamp parsed out of the snapshot id: the id is minted when the
 * run starts and the manifest commits when the upload finishes, so on a long upload the two differ
 * by the length of the transfer.
 */
export async function resolveSnapshotAt(
  lineage: string,
  at: string,
  // Omitted means every stream: read-only `backup browse --at` calls it this way (plan E4 scopes restore only). `restore --at` always passes a scope.
  scope: StreamScope = { anyStream: true },
  options: ResolveOptions = {}
): Promise<string> {
  if (SNAPSHOT_ID_RE.test(at)) return at;
  const when = parseAtTime(at, scope);

  // Resolving a time reads the hosted snapshot index, which a Free License (or no login) does not have.
  assertHostedBackupAccount();
  const stream = scope.anyStream
    ? { anyStream: '1' }
    : { anchorSnapshotId: scope.anchorSnapshotId };
  const whenIso = when.toISOString();
  const chosen = await fetchResolved(lineage, { ...stream, at: whenIso });
  if (!chosen) return refuseNoSnapshot(lineage, scope, stream, at);
  outputService.info(
    t('commands.backup.restore.atResolved', {
      at,
      snapshot: chosen.snapshotId,
      created: chosen.createdAt,
    })
  );
  if (options.indexed && !chosen.hasIndex) {
    return nearestIndexed(lineage, stream, whenIso, chosen);
  }
  return chosen.snapshotId;
}

/** One 404 covers two causes the operator must tell apart: no snapshot that early, or an anchor the index does not hold. */
async function refuseNoSnapshot(
  lineage: string,
  scope: StreamScope,
  stream: Record<string, string | undefined>,
  at: string
): Promise<never> {
  if (!scope.anyStream && !(await fetchResolved(lineage, stream))) {
    throw new ValidationError(t('commands.backup.restore.streamUnknown'));
  }
  throw new ValidationError(t('commands.backup.restore.atNoSnapshot', { at }));
}

/**
 * The newest snapshot with a stored listing at or before the time, when the exact one has none.
 * The gap is said, since a listing from hours earlier is not the state at the asked time. No
 * indexed snapshot at all keeps the exact one, so the verb reports "no listing" as before.
 */
async function nearestIndexed(
  lineage: string,
  stream: Record<string, string | undefined>,
  whenIso: string,
  exact: BackupManifestEntry
): Promise<string> {
  const indexed = await fetchResolved(lineage, { ...stream, at: whenIso, needIndex: '1' });
  if (!indexed) return exact.snapshotId;
  outputService.warn(
    t('commands.backup.restore.atIndexGap', {
      snapshot: exact.snapshotId,
      indexed: indexed.snapshotId,
      gap: formatGap(Date.parse(exact.createdAt) - Date.parse(indexed.createdAt)),
    })
  );
  return indexed.snapshotId;
}

/**
 * Which snapshots `--at` may pick from. The lineage is shared by every fork and
 * every machine that backs up a repo (that is what makes them dedup), so a time
 * alone can land on a snapshot some OTHER stream wrote, and the restore then
 * succeeds with the wrong machine's bytes. A stream is one (repo GUID, machine)
 * pair, minted by the server, so the default scope names it by the one snapshot
 * the source machine itself records as its anchor: that snapshot's stream is
 * this repo's stream on that machine. `--any-stream` widens it on purpose.
 */
export type StreamScope =
  | { anyStream: true }
  | { anyStream: false; anchorSnapshotId: string | undefined };

/**
 * The snapshot the SOURCE machine's journal anchors for this repo, read through
 * `backup_verify` (the verb already reports it). Undefined when the machine has
 * no committed snapshot, its verify fails, or the verdict cannot be read;
 * the streamUnknown refusal names both causes.
 */
export async function readSourceAnchor(
  source: { repoName: string; machine: string },
  debug?: boolean
): Promise<string | undefined> {
  const result = await executeRepoFunction(
    'backup_verify',
    source.repoName,
    source.machine,
    { level: 'spot' },
    // A probe: the anchor decides which snapshot `--at` restores, so `--background` must not hand back a ticket here.
    { debug, captureOutput: true, probe: true },
    {
      starting: t('commands.backup.verify.starting', { name: source.repoName, level: 'spot' }),
      completed: t('commands.backup.verify.completed', { name: source.repoName }),
      failed: t('commands.backup.verify.failed', { name: source.repoName }),
    }
  );
  if (!result.success) return undefined;
  const verdict = parseVerifyVerdict(result.stdout) as { snapshotId?: string } | undefined;
  return verdict?.snapshotId;
}

/**
 * The stream scope `--at` resolves under, shared by the whole-image restore and `--path` so
 * the two cannot pick different snapshots for one time. An explicit snapshot id is a
 * deliberate choice and needs no scope; only a TIME does.
 */
export async function streamScopeFor(args: {
  at: string;
  anyStream: boolean;
  source: { repoName: string; machine: string };
  debug?: boolean;
}): Promise<StreamScope> {
  if (args.anyStream || SNAPSHOT_ID_RE.test(args.at)) return { anyStream: true };
  return {
    anyStream: false,
    anchorSnapshotId: await readSourceAnchor(args.source, args.debug),
  };
}

/**
 * Run `backup_restore` for a point-in-time restore from the chunk store, and
 * unwind the just-registered record on failure exactly as the pull path does,
 * so a retry is not blocked by target-exists.
 */
export async function runChunkRestore(args: {
  targetName: string;
  targetMachine: string;
  datastore: string | undefined;
  lineage: string;
  at: string;
  anyStream: boolean;
  noSeed: boolean;
  /** Place an image the repository passphrase did not open (renet keeps the staged copy otherwise). */
  allowUnopenable?: boolean;
  /** Continue past lost or corrupt chunks, leaving their cells as holes; only into a new name. */
  salvage?: boolean;
  source: { repoName: string; machine: string };
  debug?: boolean;
  after: PlannedStep[];
}): Promise<void> {
  const { targetName, targetMachine, datastore, lineage, at, anyStream, noSeed, source, debug } =
    args;
  const scope = await streamScopeFor({ at, anyStream, source, debug });
  const snapshotId = await resolveSnapshotAt(lineage, at, scope);

  outputService.info(
    t('commands.backup.restore.restoringSnapshot', { name: targetName, snapshot: snapshotId })
  );
  await deployRepoKeyIfNeeded(targetName, targetMachine);
  const outcome = await runCommandJob(
    'backup restore',
    {
      functionName: 'backup_restore',
      machineName: targetMachine,
      datastore,
      params: {
        repository: targetName,
        lineage,
        at: snapshotId,
        dry_run: false,
        no_seed: noSeed,
        ...(args.allowUnopenable ? { allow_unopenable: true } : {}),
        ...(args.salvage ? { salvage: true } : {}),
      },
      debug,
      // The record on stdout carries the restore's measurements; without capture they are dropped.
      captureOutput: true,
    },
    [
      planStep('recordBackupRun', { repo: targetName, kind: 'restore', status: 'ok', snapshotId }),
      planStep('recordBackupRunFailed', { repo: targetName, kind: 'restore', snapshotId }),
      ...args.after,
    ]
  );
  settleRestore(outcome, targetName, targetMachine);
}

/**
 * The restore summary (plan L6): what was fetched, reused from a local seed or anchor, and punched
 * out, so a restore that moved little reads as one. Structured formats print the whole record.
 */
async function reportRestoreStats(stats: RestoreStats | undefined): Promise<void> {
  if (!stats) return;
  const format = getOutputFormat();
  if (format !== 'table') {
    outputService.print(stats, format);
    return;
  }
  const { formatSizeBytes } = await import('@rediacc/shared/renet-contract');
  const bytes = (n: number | undefined) => formatSizeBytes(n ?? 0);
  outputService.info(
    t('commands.backup.restore.stats', {
      fetched: stats.chunksFetched ?? 0,
      reused: stats.chunksReused ?? 0,
      known: stats.cellsKnown ?? 0,
      punched: stats.cellsPunched ?? 0,
      bytes: bytes(stats.bytesFetched),
      cellBytes: bytes(stats.cellBytes),
    })
  );
  if (stats.seed) {
    outputService.info(
      t('commands.backup.restore.statsSeed', {
        seed: stats.seed,
        guid: stats.seedGuid ?? '-',
        probe: bytes(stats.seedProbeBytes),
      })
    );
  }
  for (const skipped of stats.seedsSkipped ?? []) {
    outputService.info(t('commands.backup.restore.statsSeedSkipped', { skipped }));
  }
}

/**
 * What the test-open of the placed image found, said plainly in every format (stderr for the
 * warnings, so a JSON document on stdout stays one document). An image nobody tried to open is the
 * case that must not read as success: it may not unlock until the right passphrase is found.
 */
function reportPassphraseCheck(stats: RestoreStats | undefined): void {
  if (!stats) return;
  switch (stats.passphraseCheck) {
    case 'opened':
      if (getOutputFormat() === 'table') {
        outputService.info(t('commands.backup.restore.passphraseOpened'));
      }
      return;
    case 'refused':
      outputService.warn(
        t('commands.backup.restore.passphraseRefusedPlaced', { reason: stats.reason ?? '-' })
      );
      return;
    default:
      outputService.warn(
        t('commands.backup.restore.passphraseNotChecked', { reason: stats.reason ?? '-' })
      );
  }
}

/** A `--salvage` restore that placed an image with holes: every hole by byte range, and the warning that the image may not open. */
function reportRestoreDamage(stats: RestoreStats | undefined): void {
  if (stats?.status !== 'restored-damaged') return;
  const format = getOutputFormat();
  if (format !== 'table') {
    outputService.print(stats, format);
  }
  const cells = stats.badCells ?? [];
  outputService.warn(t('commands.backup.restore.salvageDamaged', { count: cells.length }));
  if (format === 'table') {
    for (const cell of cells) {
      outputService.warn(
        t('commands.backup.restore.salvageHole', {
          offset: cell.offset,
          end: cell.offset + cell.length,
          reason: cell.reason ?? '-',
        })
      );
    }
  }
  if (cells.some((c) => c.inLuksHeader)) {
    outputService.warn(t('commands.backup.restore.salvageHeaderHit'));
  }
}

bindStepHandler('reportRestoreStats', async ({ output }) => {
  const stats = parseRestoreStats(output);
  await reportRestoreStats(stats);
  reportPassphraseCheck(stats);
});

// A salvage that placed a damaged image fails the job on purpose; this is the one place its holes are reported.
bindStepHandler('reportRestoreDamage', ({ output }) => {
  reportRestoreDamage(parseRestoreStats(output));
  return Promise.resolve();
});

// `--up`: the deploy runs as its own job once the restore job succeeded, from whichever observer sees it finish first.
bindStepHandler('restoreDeploy', async ({ machine, params }) => {
  const datastore = typeof params.datastore === 'string' ? params.datastore : undefined;
  await restoreDeploy(String(params.repo), machine, datastore, {
    ...(typeof params.healthWindow === 'string' ? { healthWindow: params.healthWindow } : {}),
    ...(typeof params.healthTimeout === 'string' ? { healthTimeout: params.healthTimeout } : {}),
    debug: params.debug === true,
  });
});

/** Render a restore job's outcome: the failure, the success line, or nothing for a ticket (the executor printed it). */
export function settleRestore(
  outcome: CommandJobOutcome,
  targetName: string,
  targetMachine: string
): void {
  if (outcome.kind === 'pending') {
    const code = pendingExitCode(outcome);
    if (code !== undefined) setExitCode(code);
    return;
  }
  if (!outcome.result.success) {
    renderLocalExecutionFailure(
      outcome.result,
      t('commands.backup.restore.failed', { name: targetName })
    );
    return;
  }
  outputService.success(
    t('commands.backup.restore.restored', { name: targetName, machine: targetMachine })
  );
}

/** Deploy a restored repo (`--up`), rendering the health-gate outcome. */
async function restoreDeploy(
  name: string,
  machine: string,
  datastore: string | undefined,
  options: RestoreOptions
): Promise<void> {
  outputService.info(t('commands.backup.restore.deploying', { name, machine }));
  const params: Record<string, unknown> = { repository: name, mount: true };
  if (options.healthWindow) params.health_window = Number(options.healthWindow);
  if (options.healthTimeout) params.health_timeout = Number(options.healthTimeout);
  const up = await getExecutor().execute({
    functionName: 'repository_up',
    machineName: machine,
    // The same mount the pull wrote into (#74).
    datastore,
    params,
    debug: options.debug,
  });
  if (up.success) {
    outputService.success(t('commands.backup.restore.deployed', { name, machine }));
  } else {
    renderLocalExecutionFailure(up, t('commands.backup.restore.deployFailed', { name }));
  }
}
